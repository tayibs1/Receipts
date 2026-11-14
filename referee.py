"""Referee: plain code that decides whether a claim has a receipt.

The LLM only *proposes* a verdict, a source URL and a quote. Nothing here calls
the network or an LLM. A verdict of "supported" or "contradicted" survives only
if the quote is really present in a returned source and passes the rules below.
Every rule that fires is recorded so the UI can show it.

Rules
  R0 verdict must be one of supported / contradicted / unverified
  R1 source URL must be one of the returned results, and the quote must appear
     in that result's content (normalised), with a minimum length
  R2 every number and date in the claim must appear in the quote (supported only)
  R6 a failed search gives "unverified", never a guess
  R7 modality must match. For a claim stated as fact, speculative words in the
     quote's clause block supported and contradicted, and negation or denial words
     block supported. A claim that is itself about the future is judged against
     rumour words only, and ends up as "forward_looking", not "supported"
  R9 a rewritten paragraph must cite receipted claims, and its numbers and dates
     must come from the cited quotes
  R8 relevance: the claim's entity must appear in the source, and enough of the
     claim's key words must appear in the quote
  R4 budget: capped claims and external calls per run
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

SUPPORTED = "supported"
CONTRADICTED = "contradicted"
UNVERIFIED = "unverified"
# Decision-only state: the claim is about the future and the source says the same.
FORWARD = "forward_looking"
VERDICTS = {SUPPORTED, CONTRADICTED, UNVERIFIED}  # what the LLM may propose

MIN_QUOTE_CHARS = 20
OVERLAP_SUPPORTED = 0.5
OVERLAP_CONTRADICTED = 0.34


# ---------------------------------------------------------------- data types

@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    entity: str = ""


@dataclass(frozen=True)
class Proposal:
    verdict: str
    source_url: str = ""
    quote: str = ""


@dataclass(frozen=True)
class Result:
    name: str
    url: str
    content: str


@dataclass
class Decision:
    claim_id: str
    verdict: str
    source_url: str = ""
    quote: str = ""
    # (rule, detail) pairs. Includes passes noted as "ok" and downgrades.
    rules: list[tuple[str, str]] = field(default_factory=list)
    downgraded_from: str = ""


# -------------------------------------------------------------- normalisation

def norm(text: str) -> str:
    """Lowercase, unify unicode, reduce everything non-alphanumeric to one space."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[^0-9a-z]+", " ", text)
    return text.strip()


def norm_url(url: str) -> str:
    url = (url or "").strip().lower()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    return url.rstrip("/")


def _fragments(quote: str) -> list[str]:
    parts = re.split(r"\[?\.\.\.\]?|…", quote or "")
    return [f for f in (norm(p) for p in parts) if f]


def _contains(haystack_norm: str, needle_norm: str) -> bool:
    return f" {needle_norm} " in f" {haystack_norm} "


def quote_in_content(quote: str, content: str) -> bool:
    """True if every ellipsis-separated fragment of the quote is in the content."""
    frags = _fragments(quote)
    if not frags or sum(len(f) for f in frags) < MIN_QUOTE_CHARS:
        return False
    n = norm(content)
    return all(_contains(n, f) for f in frags)


# ------------------------------------------------------- numbers and dates

_SCALE = {
    "billion": 1e9, "bn": 1e9, "b": 1e9,
    "million": 1e6, "mn": 1e6, "m": 1e6,
    "thousand": 1e3, "k": 1e3,
}
_NUM_RE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?"
    r"\s*(billion|million|thousand|bn|mn|%|per cent|percent|(?<=\d)[bmk](?![a-z]))?",
    re.I,
)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_PAT = (
    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_MD1 = re.compile(rf"\b{_MONTH_PAT}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)
_MD2 = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MONTH_PAT}\b", re.I)


def specifics(text: str) -> set[tuple]:
    """Canonical numbers, percentages and month-day dates found in text."""
    out: set[tuple] = set()
    text = text or ""
    for m in _NUM_RE.finditer(text):
        whole = m.group(1).replace(",", "")
        value = float(whole + (m.group(2) or ""))
        unit = (m.group(3) or "").lower()
        if unit in ("%", "percent", "per cent"):
            out.add(("pct", round(value, 6)))
        else:
            value *= _SCALE.get(unit, 1.0)
            out.add(("num", round(value, 6)))
    for m in _MD1.finditer(text):
        out.add(("date", _MONTHS[m.group(1)[:3].lower()], int(m.group(2))))
    for m in _MD2.finditer(text):
        out.add(("date", _MONTHS[m.group(2)[:3].lower()], int(m.group(1))))
    return out


# --------------------------------------------------------- hedges, relevance

_RUMOUR_PAT = (
    r"rumou?rs?|rumou?red|reportedly|allegedly|alleged|unconfirmed|speculat\w*|"
    r"in talks|considering"
)
_MODAL_PAT = (
    r"plans? to|planning to|planned to|expected to|expects? to|set to|"
    r"could|may|might|would|will|likely"
)
_RUMOUR = re.compile(rf"\b({_RUMOUR_PAT})\b")
_SPECULATIVE = re.compile(rf"\b({_RUMOUR_PAT}|{_MODAL_PAT})\b")
# A claim that is itself about the future is judged on whether the source says
# the same thing, not dropped for sounding like a plan.
_FORWARD_CLAIM = re.compile(
    r"\b(will|plans? to|planning to|planned to|expected to|expects? to|set to|"
    r"aims? to|intends? to|going to|scheduled to|due to)\b"
)
_NEGATION = re.compile(
    r"\b(not|never|no longer|none|neither|nor|cannot|denied|denies|deny|refuted|"
    r"rejected|false|fake|hoax|retracted|disputed|cancelled|canceled|scrapped|"
    r"postponed|delayed|abandoned|shelved|"
    r"didn t|doesn t|don t|isn t|wasn t|weren t|hasn t|hadn t|haven t|won t|"
    r"wouldn t|couldn t|can t)\b"
)
# "May 2025", "5 May", "in May": the month, not the modal verb (found on real data).
_MAY_MONTH = re.compile(
    r"\bmay (?=\d)|(?<=\d) may\b|\b(?:in|of|by|since|until|during|early|late|mid|last|next|this) may\b"
)
_STOP = {
    "that", "this", "with", "from", "have", "were", "been", "they", "their",
    "which", "also", "into", "than", "then", "about", "over", "more", "most",
    "company", "said", "year", "years",
}
_SCALE_WORDS = {"billion", "million", "thousand", "percent", "cent"}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z]{4,}", norm(text))
    return {w for w in words if w not in _STOP and w not in _SCALE_WORDS}


def _overlap(claim_text: str, quote: str) -> float:
    ct = _tokens(claim_text)
    if not ct:
        return 1.0
    return len(ct & _tokens(quote)) / len(ct)


def _context_sentences(content: str, quote: str) -> list[str]:
    """The clauses of the source that contain the quote. Narrowed to a clause so a
    hedge elsewhere in a long sentence does not sink a true claim, but wide
    enough that a quote cannot hide the hedge around it."""
    frags = _fragments(quote)
    sents = re.split(r"(?<=[.!?])\s+", content or "")
    out: list[str] = []
    for s in sents:
        if not any(_contains(norm(s), f) for f in frags):
            continue
        clauses = re.split(r"[;:]|,\s+(?:but|while|although|though|whereas)\b", s)
        hit = [c for c in clauses if any(_contains(norm(c), f) for f in frags)]
        out.extend(hit or [s])
    return out or [quote]


# ------------------------------------------------------------------ referee

def decide(
    claim: Claim,
    proposal: Proposal,
    results: list[Result],
    search_error: str | None = None,
) -> Decision:
    """Return the final decision for one claim. The proposal can only be
    downgraded to "unverified", never upgraded."""
    d = Decision(claim.id, UNVERIFIED, proposal.source_url, proposal.quote)

    def fail(rule: str, detail: str) -> Decision:
        d.rules.append((rule, detail))
        if proposal.verdict in (SUPPORTED, CONTRADICTED):
            d.downgraded_from = proposal.verdict
        d.verdict = UNVERIFIED
        return d

    if search_error:
        return fail("R6", f"search failed: {search_error}")
    if proposal.verdict not in VERDICTS:
        return fail("R0", f"unknown verdict {proposal.verdict!r}")
    if proposal.verdict == UNVERIFIED:
        d.rules.append(("R0", "proposal was unverified"))
        return d

    want = norm_url(proposal.source_url)
    source = next((r for r in results if norm_url(r.url) == want), None)
    if source is None:
        return fail("R1", "source URL is not among the returned results")
    if not quote_in_content(proposal.quote, source.content):
        return fail("R1", "quote not found in the source, or too short")
    d.rules.append(("R1", "quote found in source"))

    if claim.entity and not _contains(norm(source.content), norm(claim.entity)):
        return fail("R8", f"source never mentions {claim.entity!r}")
    need = OVERLAP_SUPPORTED if proposal.verdict == SUPPORTED else OVERLAP_CONTRADICTED
    got = _overlap(claim.text, proposal.quote)
    if got < need:
        return fail("R8", f"quote covers {got:.0%} of the claim's key words, need {need:.0%}")
    d.rules.append(("R8", "relevance ok"))

    if proposal.verdict == SUPPORTED:
        missing = specifics(claim.text) - specifics(proposal.quote)
        if missing:
            return fail("R2", f"numbers or dates in the claim not in the quote: {sorted(missing)}")
        d.rules.append(("R2", "numbers and dates match"))

    forward = bool(_FORWARD_CLAIM.search(norm(claim.text)))
    blockers = _RUMOUR if forward else _SPECULATIVE
    for sent in _context_sentences(source.content, proposal.quote):
        n = _MAY_MONTH.sub(" ", norm(sent))  # the month "May" is not the word "may"
        spec = blockers.search(n)
        if spec:
            return fail("R7", f"speculative wording: {spec.group(0)!r}")
        if proposal.verdict == SUPPORTED:
            neg = _NEGATION.search(n)
            if neg:
                return fail("R7", f"negation or denial wording: {neg.group(0)!r}")

    if forward and proposal.verdict == SUPPORTED:
        d.rules.append(("R7", "source states it as a plan, not a fact"))
        d.verdict = FORWARD
        return d
    d.rules.append(("R7", "no hedge or negation"))

    d.verdict = proposal.verdict
    return d


# ---------------------------------------------------------- rewrite (R9)

_FOOTNOTE = re.compile(r"\[\d+\]|\^\d+|\[[a-z]\d+\]", re.I)


def check_paragraph(
    text: str, cited_ids: list[str], decisions: dict[str, Decision]
) -> tuple[bool, str]:
    """A rewritten paragraph is allowed only if it cites at least one claim, every
    cited claim is supported or forward-looking, and every number or date in the
    paragraph appears in the cited claims' quotes. This does not prove the prose
    adds no non-numeric assertion; it blocks invented figures and dates."""
    if not cited_ids:
        return False, "paragraph cites no claim"
    for cid in cited_ids:
        dec = decisions.get(cid)
        if dec is None or dec.verdict not in (SUPPORTED, FORWARD):
            return False, f"cites {cid}, which has no receipt"
    allowed: set[tuple] = set()
    for cid in cited_ids:
        allowed |= specifics(decisions[cid].quote)
    extra = specifics(_FOOTNOTE.sub(" ", text)) - allowed
    if extra:
        return False, f"numbers or dates not in the cited quotes: {sorted(extra)}"
    return True, "ok"


# ------------------------------------------------------------------- budget

class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    max_claims: int = 10
    max_calls: int = 40
    calls: int = 0

    def cap_claims(self, claims: list[Claim]) -> list[Claim]:
        return claims[: self.max_claims]

    def spend(self, n: int = 1, what: str = "") -> None:
        if self.calls + n > self.max_calls:
            raise BudgetExceeded(
                f"call budget of {self.max_calls} reached" + (f" ({what})" if what else "")
            )
        self.calls += n
