"""The agent loop: extract claims, plan queries, search, judge, retry, decide.

The LLM proposes; referee.py decides every verdict. One run = one briefing.

Terminal use (from receipts/):
    .venv\\Scripts\\python.exe agent.py "Stripe"            # draft from memory, then check it
    .venv\\Scripts\\python.exe agent.py --file briefing.txt  # check a pasted briefing
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import re
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote_plus

import config
import llm
import referee
import rewrite as rewrite_mod
import search
from referee import (
    CONTRADICTED,
    FORWARD,
    SUPPORTED,
    UNVERIFIED,
    Budget,
    BudgetExceeded,
    Claim,
    Decision,
    Proposal,
    Result,
)

log = logging.getLogger("receipts.agent")

AUDIT_PATH = config.ROOT / "audit.jsonl"
SEARCH_WINDOW_DAYS = 90  # first search only looks at the last 90 days
RECENT_DAYS = 180  # "recent" freshness label
TOP_RESULTS = 5  # results shown to the judge and accepted by the referee

Emit = Callable[[dict], None]


# --------------------------------------------------------------- data types

@dataclass
class Attempt:
    query: str
    from_date: str | None
    depth: str
    n_results: int = 0
    cached: bool = False
    search_error: str | None = None
    proposal: dict = field(default_factory=dict)  # what the LLM proposed
    verdict: str = UNVERIFIED  # what the referee decided
    rules: list = field(default_factory=list)
    downgraded_from: str = ""


@dataclass
class ClaimResult:
    claim: Claim
    kind: str = "other"
    section: str = ""
    decision: Decision = None  # type: ignore[assignment]
    attempts: list[Attempt] = field(default_factory=list)
    source_name: str = ""
    published_at: str | None = None
    freshness: str = ""
    reason: str = ""
    trace: str = ""


@dataclass
class Report:
    run_id: str
    company: str
    briefing: str
    drafted: bool
    n_extracted: int
    results: list[ClaimResult]
    calls: dict
    stopped_early: str = ""
    rewrite: object = None  # rewrite.Rewrite, or None if not requested
    llm_cache: dict = field(default_factory=dict)  # model replies served from cache vs live

    @property
    def counts(self) -> dict:
        c = {SUPPORTED: 0, CONTRADICTED: 0, FORWARD: 0, UNVERIFIED: 0}
        for r in self.results:
            c[r.decision.verdict] += 1
        return c


class Meter:
    """Thread-safe call counter on top of referee.Budget. `reserve` keeps calls free
    for the rewrite step so claim checking cannot starve it."""

    def __init__(self, budget: Budget, reserve: int = 2):
        self.budget = budget
        self.reserve = reserve
        self.by_kind: dict[str, int] = {}
        self._lock = threading.Lock()

    def spend(self, what: str, reserve: bool = True) -> None:
        with self._lock:
            held = self.reserve if reserve else 0
            if self.budget.calls + 1 > self.budget.max_calls - held:
                raise BudgetExceeded(f"call budget of {self.budget.max_calls} reached ({what})")
            self.budget.spend(1, what)
            self.by_kind[what] = self.by_kind.get(what, 0) + 1


@dataclass
class Ctx:
    meter: Meter
    emit: Emit
    today: dt.date


# ------------------------------------------------------------------- helpers

def rank_claims(items: list[tuple[Claim, str, str]]) -> list[tuple[Claim, str, str]]:
    """Order claims by impact: numbers and dates first, people and entities second,
    the rest last; original order breaks ties. Items are (claim, kind, section)."""

    def score(item: tuple[Claim, str, str]) -> int:
        claim, kind, _ = item
        if referee.specifics(claim.text) or kind in ("number", "date"):
            return 3
        return 2 if kind in ("person", "entity") else 1

    indexed = list(enumerate(items))
    indexed.sort(key=lambda p: (-score(p[1]), p[0]))
    return [item for _, item in indexed]


_YEAR = re.compile(r"\b(19|20)\d{2}\b")


def search_window_start(claim_text: str, today: dt.date) -> dt.date | None:
    """First search only looks at the last 90 days, unless the claim is about a
    past year: then a recent-news filter would hide the very page that proves it
    (found at the first checkpoint: 'ChatGPT launched in November 2022')."""
    if any(int(m.group(0)) < today.year for m in _YEAR.finditer(claim_text)):
        return None
    return today - dt.timedelta(days=SEARCH_WINDOW_DAYS)


def freshness_label(published_at: str | None, today: dt.date) -> str:
    """A freshness check from the source's own published_at; never 'date verified'."""
    if not published_at:
        return "date unknown"
    try:
        published = dt.date.fromisoformat(str(published_at)[:10])
    except ValueError:
        return "date unknown"
    return "recent" if (today - published).days <= RECENT_DAYS else "older source, may be stale"


def _short(text: str, n: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _rules_text(rules: list, kept: bool = False) -> str:
    """Readable rule summary: the rules that passed if the verdict stood, otherwise
    the rule that stopped it."""
    if not rules:
        return "no rule fired"
    if kept:
        return "rules passed: " + ", ".join(r for r, _ in rules)
    rule, detail = rules[-1]
    if rule == "R0" and detail == "proposal was unverified":
        return "judge found no receipt"
    return f"{rule}: {detail}"


# -------------------------------------------------------------- claim check

def _attempt(claim: Claim, query: str, from_date: dt.date | None, ctx: Ctx):
    """One search + judge + referee pass. Returns (Attempt, Decision, hits)."""
    outcome = search.search(
        query, depth="standard", from_date=from_date, spend=lambda: ctx.meter.spend("search")
    )
    hits = outcome.hits[:TOP_RESULTS]
    att = Attempt(
        query=query,
        from_date=str(from_date) if from_date else None,
        depth="standard",
        n_results=len(hits),
        cached=outcome.cached,
        search_error=outcome.error,
    )
    if outcome.error:
        dec = referee.decide(claim, Proposal(UNVERIFIED), [], search_error=outcome.error)
    elif not hits:
        dec = Decision(claim.id, UNVERIFIED, rules=[("R0", "search returned no results")])
    else:
        ctx.meter.spend("judge")
        j = llm.judge(claim.text, claim.entity, str(ctx.today), hits)
        att.proposal = {"verdict": j.verdict, "source_url": j.source_url, "quote": j.quote, "reason": j.reason}
        dec = referee.decide(
            claim,
            Proposal(j.verdict, j.source_url, j.quote),
            [Result(h.name, h.url, h.content) for h in hits],
        )
    att.verdict, att.rules, att.downgraded_from = dec.verdict, list(dec.rules), dec.downgraded_from
    return att, dec, hits


def check_claim(claim: Claim, ctx: Ctx, kind: str = "other", section: str = "") -> ClaimResult:
    """Steps 3a-3e for one claim: plan, search, judge, referee, one retry, freshness."""
    res = ClaimResult(claim=claim, kind=kind, section=section)
    parts = [f'claim {claim.id} "{_short(claim.text)}"']
    dec: Decision | None = None
    hits: list = []
    try:
        ctx.meter.spend("plan")
        q1 = llm.plan_query(claim.text, claim.entity, str(ctx.today))
        parts.append(f'query "{q1}"')
        att, dec, hits = _attempt(claim, q1, search_window_start(claim.text, ctx.today), ctx)
        res.attempts.append(att)
        parts.append(_describe(att, dec))

        searched_ok = not att.search_error
        if dec.verdict == UNVERIFIED and searched_ok:
            ctx.meter.spend("plan")
            q2 = llm.reword_query(claim.text, claim.entity, q1, ctx.today.isoformat())
            parts.append(f'-> retry with new wording "{q2}" (no date filter)')
            att2, dec2, hits2 = _attempt(claim, q2, None, ctx)
            res.attempts.append(att2)
            parts.append(_describe(att2, dec2))
            dec, hits = dec2, hits2
    except BudgetExceeded as e:
        base = list(dec.rules) if dec else []
        dec = Decision(claim.id, UNVERIFIED, rules=base + [("R4", str(e))])
        parts.append(f"-> stopped: {e} -> unverified (R4)")
    except llm.LLMError as e:
        log.error("claim %s: LLM failed: %s", claim.id, e)
        dec = Decision(claim.id, UNVERIFIED, rules=[("ERR", str(e))])
        parts.append(f"-> model error: {e} -> unverified")

    res.decision = dec
    if dec.verdict in (SUPPORTED, CONTRADICTED, FORWARD):
        want = referee.norm_url(dec.source_url)
        src = next((h for h in hits if referee.norm_url(h.url) == want), None)
        if src:
            res.source_name, res.published_at = src.name, src.published_at
            res.freshness = freshness_label(src.published_at, ctx.today)
        if res.attempts and res.attempts[-1].proposal:
            res.reason = res.attempts[-1].proposal.get("reason", "")
        parts.append(f"[freshness check: {res.freshness}]")
    res.trace = " ".join(parts)
    ctx.emit({"type": "decision", "claim_id": claim.id, "verdict": dec.verdict, "trace": res.trace,
              "card": claim_card(res), "calls": sum(ctx.meter.by_kind.values()),
              "max_calls": ctx.meter.budget.max_calls})
    return res


def claim_card(res: ClaimResult) -> dict:
    """Everything the UI needs to draw one claim card and its evidence drawer."""
    d = res.decision
    return {
        "id": res.claim.id, "text": res.claim.text, "entity": res.claim.entity,
        "kind": res.kind, "section": res.section, "verdict": d.verdict,
        "source_name": res.source_name, "source_url": d.source_url if d.verdict != UNVERIFIED else "",
        "quote": d.quote if d.verdict != UNVERIFIED else "",
        "freshness": res.freshness, "published_at": res.published_at, "reason": res.reason,
        "rules": [list(r) for r in d.rules], "downgraded_from": d.downgraded_from,
        "attempts": [
            {"query": a.query, "from_date": a.from_date, "cached": a.cached, "n_results": a.n_results,
             "error": a.search_error, "judge": a.proposal.get("verdict", ""), "referee": a.verdict}
            for a in res.attempts
        ],
        "trace": res.trace,
        "search_link": "https://www.google.com/search?q=" + quote_plus(res.claim.text),
    }


def attack(text: str, entity: str = "", *, today: dt.date | None = None, emit: Emit | None = None,
           max_calls: int = 12) -> ClaimResult:
    """Attack mode: check one claim typed by the user (plan, search, judge, referee, one retry)."""
    llm.set_cache(True)
    meter = Meter(Budget(max_calls=max_calls), reserve=0)
    ctx = Ctx(meter, emit or (lambda e: None), today or dt.date.today())
    return check_claim(Claim("A1", text.strip(), entity.strip()), ctx)


def _describe(att: Attempt, dec: Decision) -> str:
    if att.search_error:
        return f"-> search failed ({att.search_error}) -> unverified (R6)"
    src = "cached" if att.cached else "live"
    if att.n_results == 0:
        return f"-> {src} search, no results -> unverified"
    prop = att.proposal.get("verdict", "?")
    text = f"-> {att.n_results} results ({src}) -> judge proposed {prop}"
    if dec.verdict == prop and prop != UNVERIFIED:
        return text + f" -> referee kept {dec.verdict} ({_rules_text(dec.rules, kept=True)})"
    return text + f" -> referee decided {dec.verdict} ({_rules_text(dec.rules)})"


# ------------------------------------------------------------------ the run

def run(
    company: str = "",
    briefing: str = "",
    *,
    max_claims: int = 10,
    max_calls: int = 60,
    workers: int = 4,
    emit: Emit | None = None,
    today: dt.date | None = None,
    audit_path=None,
    do_rewrite: bool = True,
    fresh: bool = False,
) -> Report:
    """fresh=True skips the model-reply cache (searches are still cached)."""
    if not company and not briefing:
        raise ValueError("give a company name or a briefing")
    llm.set_cache(not fresh)
    emit = emit or (lambda e: None)
    today = today or dt.date.today()
    run_id = uuid.uuid4().hex[:8]
    meter = Meter(Budget(max_claims=max_claims, max_calls=max_calls))
    ctx = Ctx(meter, emit, today)
    stopped = ""

    drafted = not briefing
    if drafted:
        emit({"type": "info", "msg": f"drafting a briefing on {company} from the model's memory (no web)"})
        meter.spend("draft", reserve=False)
        briefing = llm.draft_briefing(company)

    emit({"type": "info", "msg": "extracting factual claims"})
    meter.spend("extract", reserve=False)
    extracted = llm.extract_claims(briefing, max_claims=20)
    items = [
        (Claim(str(i), c.text.strip(), c.entity.strip()), c.kind, c.section)
        for i, c in enumerate(extracted, 1)
    ]
    chosen = rank_claims(items)[: meter.budget.max_claims]
    emit({
        "type": "info",
        "msg": f"{len(chosen)} of {len(items)} claims checked, ranked by impact "
               f"(numbers and dates first, then people and entities)",
    })

    emit({
        "type": "claims", "briefing": briefing, "drafted": drafted, "extracted": len(items),
        "claims": [{"id": c.id, "text": c.text, "kind": k, "section": s} for c, k, s in chosen],
    })

    def work(item: tuple[Claim, str, str]) -> ClaimResult:
        claim, kind, section = item
        try:
            return check_claim(claim, ctx, kind, section)
        except Exception as e:  # one broken claim must not sink the run; shown, never hidden
            log.exception("claim %s failed", claim.id)
            res = ClaimResult(claim=claim, kind=kind, section=section,
                              decision=Decision(claim.id, UNVERIFIED, rules=[("ERR", f"{type(e).__name__}: {e}")]))
            res.trace = f'claim {claim.id} "{_short(claim.text)}" -> error: {type(e).__name__}: {e} -> unverified'
            emit({"type": "decision", "claim_id": claim.id, "verdict": UNVERIFIED, "trace": res.trace,
                  "card": claim_card(res), "calls": sum(meter.by_kind.values()), "max_calls": max_calls})
            return res

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(work, chosen))
    results.sort(key=lambda r: int(r.claim.id))
    if any(("R4" in [x for x, _ in r.decision.rules]) for r in results):
        stopped = f"call budget of {max_calls} reached: some claims were left unchecked (R4)"
        emit({"type": "info", "msg": stopped})

    rw = None
    if do_rewrite:
        rw = rewrite_mod.build(company, briefing, results, lambda what: meter.spend(what, reserve=False), emit)
        if rw.error:
            emit({"type": "info", "msg": rw.error})
    report = Report(run_id, company, briefing, drafted, len(items), results, dict(meter.by_kind), stopped, rw,
                    llm.cache_stats())
    _write_audit(report, audit_path or AUDIT_PATH)
    return report


# ------------------------------------------------------------- audit + output

def report_record(report: Report) -> dict:
    """Plain-data record of a run: the audit log line and the evaluation input."""
    return {
        "run_id": report.run_id,
        "briefing": report.briefing,
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "company": report.company,
        "briefing_drafted_by_model": report.drafted,
        "claims_extracted": report.n_extracted,
        "claims_checked": len(report.results),
        "counts": report.counts,
        "calls": report.calls,
        "stopped_early": report.stopped_early,
        "llm_cache": report.llm_cache,
        "rewrite": _rewrite_record(report.rewrite),
        "claims": [
            {
                "id": r.claim.id,
                "text": r.claim.text,
                "entity": r.claim.entity,
                "kind": r.kind,
                "verdict": r.decision.verdict,
                "rules": r.decision.rules,
                "source_url": r.decision.source_url,
                "quote": r.decision.quote,
                "freshness": r.freshness,
                "attempts": [vars(a) for a in r.attempts],
            }
            for r in report.results
        ],
    }


def _rewrite_record(rw) -> dict | None:
    if rw is None:
        return None
    return {
        "paragraphs": [{"section": p.section, "text": p.text, "claim_ids": p.claim_ids, "check": p.check}
                       for p in rw.paragraphs],
        "rejected_by_R9": rw.rejected,
        "listed_not_rewritten": rw.fallback,
        "dropped_sections": rw.dropped_sections,
        "error": rw.error,
    }


def _write_audit(report: Report, path) -> None:
    record = report_record(report)
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        log.error("could not write audit log: %s: %s", type(e).__name__, e)


def render_text(report: Report) -> str:
    """Plain-text receipted result: the policy applied to each claim, no LLM involved."""
    by = {SUPPORTED: [], FORWARD: [], CONTRADICTED: [], UNVERIFIED: []}
    for r in report.results:
        by[r.decision.verdict].append(r)
    c = report.counts
    lines = [
        f"RECEIPTS: {report.company or 'pasted briefing'} (run {report.run_id})",
        f"{len(report.results)} claims checked of {report.n_extracted} extracted, ranked by impact: "
        f"{c[SUPPORTED]} supported, {c[CONTRADICTED]} contradicted, {c[FORWARD]} plans, "
        f"{c[UNVERIFIED]} need your check",
        "",
    ]
    n = 0
    lines.append("SUPPORTED (a source and a quote that appears in it)")
    for r in by[SUPPORTED]:
        n += 1
        lines.append(f"  [{n}] {r.claim.text}")
        lines.append(_receipt_line(r))
    if not by[SUPPORTED]:
        lines.append("  none")
    lines += ["", "PLANS AND PROJECTIONS (stated as a plan, not a fact)"]
    for r in by[FORWARD]:
        n += 1
        lines.append(f"  [{n}] {r.claim.text}")
        lines.append(_receipt_line(r))
    if not by[FORWARD]:
        lines.append("  none")
    lines += ["", "CONTRADICTED (struck out)"]
    for r in by[CONTRADICTED]:
        n += 1
        lines.append(f"  [{n}] ~~{r.claim.text}~~")
        lines.append(_receipt_line(r))
    if not by[CONTRADICTED]:
        lines.append("  none")
    lines += ["", "NEEDS YOUR CHECK (no receipt)"]
    for r in by[UNVERIFIED]:
        lines.append(f"  - {r.claim.text}")
        lines.append(f"      why: {_rules_text(r.decision.rules)}")
        lines.append(f"      search manually: https://www.google.com/search?q={quote_plus(r.claim.text)}")
    if not by[UNVERIFIED]:
        lines.append("  none")
    calls = report.calls
    lines += ["", f"calls: {sum(calls.values())} total {calls}"]
    if report.stopped_early:
        lines.append(f"NOTE: {report.stopped_early}")
    return "\n".join(lines)


def _receipt_line(r: ClaimResult) -> str:
    d = r.decision
    return (
        f"      source: {r.source_name or d.source_url} <{d.source_url}> [freshness check: {r.freshness}]\n"
        f'      quote: "{d.quote}"'
    )


# ---------------------------------------------------------------------- CLI

def _make_printer() -> Emit:
    lock = threading.Lock()

    def emit(event: dict) -> None:
        if event["type"] not in ("info", "decision"):
            return
        with lock:
            print(event.get("msg") or event.get("trace"), flush=True)

    return emit


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check an AI-written company briefing against live sources.")
    ap.add_argument("company", nargs="?", default="", help="company name: the model drafts a briefing from memory")
    ap.add_argument("--file", help="path to a briefing text file to check instead")
    ap.add_argument("--max-claims", type=int, default=10)
    ap.add_argument("--max-calls", type=int, default=60)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--fresh", action="store_true", help="ask the models again instead of replaying cached replies")
    args = ap.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    config.load_env()
    config.print_key_status()
    status = config.key_status()
    if not all(status.values()):
        print("Missing key: cannot run live. Fix .env (never paste keys into chat).")
        return 2

    briefing = ""
    if args.file:
        with open(args.file, encoding="utf-8") as f:
            briefing = f.read()
    if not args.company and not briefing:
        ap.error("give a company name or --file")

    t0 = time.time()
    report = run(
        args.company,
        briefing,
        max_claims=args.max_claims,
        max_calls=args.max_calls,
        workers=args.workers,
        emit=_make_printer(),
        fresh=args.fresh,
    )
    if report.drafted:
        print("\n--- DRAFT (from model memory, no web) ---\n" + report.briefing + "\n--- END DRAFT ---\n")
    print("\n" + render_text(report))
    if report.rewrite is not None:
        print("\n--- VERIFIED BRIEFING (rewritten; R9 checked every number and date) ---\n" + report.rewrite.markdown)
        for bad in report.rewrite.rejected:
            print(f"R9 refused a paragraph: {bad['reason']}")
    print(f"\n({time.time() - t0:.0f}s; audit appended to {AUDIT_PATH.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
