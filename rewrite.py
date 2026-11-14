"""The rewrite step: a final briefing in which every sentence has a receipt.

Sonnet writes paragraphs from the receipted claims only. Code then runs
referee.check_paragraph (R9) on every paragraph: it must cite claims that have
receipts, and every number and date in it must appear in the cited quotes. A
paragraph that fails is regenerated once; if it still fails it is replaced by
its own referee-approved claims, listed as they were checked. This blocks invented
figures and dates. It does not prove the prose adds no non-numeric statement.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import quote_plus

import llm
import referee
from referee import CONTRADICTED, FORWARD, SUPPORTED, UNVERIFIED, BudgetExceeded


@dataclass
class Paragraph:
    section: str
    text: str
    claim_ids: list[str]
    check: str = "ok"  # the R9 result for this paragraph
    notes: list[int] = field(default_factory=list)  # footnote numbers, set when assembled


@dataclass
class Rewrite:
    paragraphs: list[Paragraph] = field(default_factory=list)
    fallback: list[str] = field(default_factory=list)  # claim ids listed as checked, not rewritten
    rejected: list[dict] = field(default_factory=list)  # paragraphs R9 refused: text and reason
    dropped_sections: list[str] = field(default_factory=list)
    footnotes: list[dict] = field(default_factory=list)
    markdown: str = ""
    diff: list[dict] = field(default_factory=list)
    error: str = ""


def _decisions(results) -> dict[str, referee.Decision]:
    return {r.claim.id: r.decision for r in results}


def _check_all(paragraphs, decisions) -> tuple[list[Paragraph], list[tuple[Paragraph, str]]]:
    good, bad = [], []
    for p in paragraphs:
        ok, why = referee.check_paragraph(p.text, p.claim_ids, decisions)
        p.check = why
        (good if ok else bad).append(p if ok else (p, why))
    return good, bad


def build(company: str, draft: str, results, spend: Callable[[str], None], emit=lambda e: None) -> Rewrite:
    """`results`: ClaimResult-like objects (.claim, .decision, .section, .source_name, .freshness).
    `spend(what)` charges one call and may raise BudgetExceeded."""
    rw = Rewrite()
    by_id = {r.claim.id: r for r in results}
    decisions = _decisions(results)
    receipted = [r for r in results if r.decision.verdict == SUPPORTED]

    if receipted:
        payload = [
            {"id": r.claim.id, "text": r.claim.text, "quote": r.decision.quote, "section": r.section}
            for r in receipted
        ]
        try:
            emit({"type": "info", "msg": f"rewriting the briefing from {len(payload)} receipted claims"})
            spend("rewrite")
            first = llm.rewrite(company, payload)
            good, bad = _check_all([Paragraph(p.section, p.text, p.claim_ids) for p in first.paragraphs], decisions)
            if bad:
                feedback = "; ".join(f'"{p.text[:80]}": {why}' for p, why in bad)
                emit({"type": "info", "msg": f"{len(bad)} paragraph(s) failed the number check (R9); regenerating once"})
                ids = sorted({i for p, _ in bad for i in p.claim_ids if i in by_id and decisions[i].verdict == SUPPORTED})
                retry_payload = [x for x in payload if x["id"] in ids] or payload
                spend("rewrite")
                second = llm.rewrite(company, retry_payload, feedback=feedback)
                good2, bad2 = _check_all(
                    [Paragraph(p.section, p.text, p.claim_ids) for p in second.paragraphs], decisions
                )
                good += good2
                bad = bad2
            for p, why in bad:
                rw.rejected.append({"text": p.text, "reason": why})
            rw.paragraphs = good
        except BudgetExceeded as e:
            rw.error = f"rewrite skipped: {e}"
        except llm.LLMError as e:
            rw.error = f"rewrite failed: {e}"

    covered = {i for p in rw.paragraphs for i in p.claim_ids}
    rw.fallback = [r.claim.id for r in receipted if r.claim.id not in covered]
    kept_sections = {r.section for r in results if r.decision.verdict in (SUPPORTED, FORWARD) and r.section}
    all_sections = {r.section for r in results if r.section}
    rw.dropped_sections = sorted(all_sections - kept_sections)
    _assemble(rw, company, results, by_id)
    rw.diff = diff_words(draft, " ".join(p.text for p in rw.paragraphs) or "")
    return rw


def _assemble(rw: Rewrite, company: str, results, by_id) -> None:
    """Number the footnotes in order of first use and write the Markdown."""
    notes: dict[str, int] = {}

    def note(claim_id: str) -> int:
        if claim_id not in notes:
            notes[claim_id] = len(notes) + 1
        return notes[claim_id]

    def marks(ids) -> str:
        return " " + "".join(f"[{note(i)}]" for i in dict.fromkeys(ids))

    lines = [f"# {company or 'Company'} briefing: verified", ""]
    lines.append("_Every number and date below appears in a cited quote. Claims without a receipt are listed at the end, not stated as fact._")
    current = None
    for p in rw.paragraphs:
        if p.section != current:
            current = p.section
            lines += ["", f"## {current or 'Briefing'}"]
        lines += ["", p.text.strip() + marks(p.claim_ids)]
        p.notes = [note(i) for i in dict.fromkeys(p.claim_ids)]
    if rw.fallback:
        lines += ["", "## Verified facts (checked, not rewritten)"]
        for i in rw.fallback:
            lines.append(f"- {by_id[i].claim.text}{marks([i])}")
    plans = [r for r in results if r.decision.verdict == FORWARD]
    if plans:
        lines += ["", "## Plans and projections (stated as a plan, not a fact)"]
        lines += [f"- {r.claim.text}{marks([r.claim.id])}" for r in plans]
    wrong = [r for r in results if r.decision.verdict == CONTRADICTED]
    if wrong:
        lines += ["", "## Corrections (the draft said this; a source says otherwise)"]
        lines += [f"- ~~{r.claim.text}~~{marks([r.claim.id])}" for r in wrong]
    check = [r for r in results if r.decision.verdict == UNVERIFIED]
    if check:
        lines += ["", "## Needs your check (no receipt found)"]
        lines += [
            f"- {r.claim.text} ([search manually](https://www.google.com/search?q={quote_plus(r.claim.text)}))"
            for r in check
        ]
    if rw.dropped_sections:
        lines += ["", f"_Sections of the draft with no receipted claim were left out: {', '.join(rw.dropped_sections)}._"]
    if notes:
        lines += ["", "## Sources"]
        for cid, n in sorted(notes.items(), key=lambda kv: kv[1]):
            r, d = by_id[cid], by_id[cid].decision
            quote = " ".join(d.quote.split())  # one line per footnote
            rw.footnotes.append({"n": n, "claim_id": cid, "source": r.source_name or d.source_url,
                                 "url": d.source_url, "quote": quote, "freshness": r.freshness})
            lines.append(f'[{n}] {r.source_name or d.source_url}, <{d.source_url}>, freshness check: {r.freshness or "n/a"}. "{quote}"')
    rw.markdown = "\n".join(lines) + "\n"


def diff_words(draft: str, verified: str) -> list[dict]:
    """Word-level draft-versus-verified diff: [{op: equal|removed|added, text}]."""
    a = re.findall(r"\S+", re.sub(r"[-*•#]+\s*", " ", draft or ""))
    b = re.findall(r"\S+", verified or "")
    out: list[dict] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"op": "equal", "text": " ".join(a[i1:i2])})
        else:
            if i2 > i1:
                out.append({"op": "removed", "text": " ".join(a[i1:i2])})
            if j2 > j1:
                out.append({"op": "added", "text": " ".join(b[j1:j2])})
    return out
