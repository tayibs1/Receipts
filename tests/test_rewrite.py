"""Rewrite step: R9 is enforced on every paragraph; mocked LLM, no network."""

import agent
import llm
import referee
import rewrite
from referee import Claim, Decision

QUOTE = "Stripe reported total payment volume of $1.4 trillion in 2024"


def result(cid, text, verdict, quote=QUOTE, section="Financials", url="https://example.com/a"):
    return agent.ClaimResult(
        claim=Claim(cid, text, "Stripe"), section=section,
        decision=Decision(cid, verdict, url if verdict != "unverified" else "", quote if verdict != "unverified" else ""),
        source_name="Example News", freshness="recent",
    )


def para(text, ids, section="Financials"):
    return llm.ParagraphOut(section=section, text=text, claim_ids=ids)


def run_build(monkeypatch, replies, results):
    calls = []

    def fake(company, claims, feedback=""):
        calls.append(feedback)
        return llm.RewriteOut(paragraphs=replies[len(calls) - 1])

    monkeypatch.setattr(rewrite.llm, "rewrite", fake)
    spent = []
    rw = rewrite.build("Stripe", "Stripe made 9 trillion.", results, spent.append)
    return rw, calls, spent


def test_good_paragraph_is_kept_with_footnote(monkeypatch):
    rs = [result("1", "Stripe reported payment volume of $1.4 trillion in 2024", "supported")]
    rw, calls, spent = run_build(monkeypatch, [[para("Stripe processed $1.4 trillion in 2024.", ["1"])]], rs)
    assert len(rw.paragraphs) == 1 and not rw.rejected and not rw.fallback
    assert "Stripe processed $1.4 trillion in 2024. [1]" in rw.markdown
    assert "[1] Example News" in rw.markdown and len(calls) == 1 and spent == ["rewrite"]


def test_invented_number_is_refused_regenerated_then_listed_as_checked(monkeypatch):
    rs = [result("1", "Stripe reported payment volume of $1.4 trillion in 2024", "supported")]
    bad = para("Stripe processed $9 trillion in 2024.", ["1"])
    rw, calls, spent = run_build(monkeypatch, [[bad], [bad]], rs)
    assert not rw.paragraphs and len(rw.rejected) == 1
    assert rw.fallback == ["1"] and len(calls) == 2 and "rejected by the checker" not in calls[0]
    assert "Stripe processed $9 trillion" in calls[1]  # the retry is told which paragraph failed
    assert "$9 trillion" not in rw.markdown  # the invented figure never reaches the output
    assert "Verified facts (checked, not rewritten)" in rw.markdown


def test_regeneration_can_repair_a_paragraph(monkeypatch):
    rs = [result("1", "Stripe reported payment volume of $1.4 trillion in 2024", "supported")]
    rw, calls, _ = run_build(
        monkeypatch,
        [[para("Stripe processed $9 trillion in 2024.", ["1"])], [para("Stripe processed $1.4 trillion in 2024.", ["1"])]],
        rs,
    )
    assert len(rw.paragraphs) == 1 and not rw.rejected and not rw.fallback


def test_paragraph_citing_an_unreceipted_claim_is_refused(monkeypatch):
    rs = [
        result("1", "Stripe reported payment volume of $1.4 trillion in 2024", "supported"),
        result("2", "Stripe is based in Mars", "unverified"),
    ]
    p = para("Stripe is based in Mars.", ["2"])
    rw, _, _ = run_build(monkeypatch, [[p], [p]], rs)
    assert rw.rejected and "no receipt" in rw.rejected[0]["reason"]


def test_sections_without_receipts_are_dropped_and_said_so(monkeypatch):
    rs = [
        result("1", "Stripe reported payment volume of $1.4 trillion in 2024", "supported", section="Financials"),
        result("2", "Stripe has an office on Mars", "unverified", section="Offices"),
    ]
    rw, _, _ = run_build(monkeypatch, [[para("Stripe processed $1.4 trillion in 2024.", ["1"])]], rs)
    assert rw.dropped_sections == ["Offices"] and "Offices" in rw.markdown
    assert "Needs your check" in rw.markdown and "search manually" in rw.markdown


def test_contradicted_claims_are_struck_out_not_stated(monkeypatch):
    rs = [
        result("1", "Stripe reported payment volume of $1.4 trillion in 2024", "supported"),
        result("2", "Stripe processed $9 trillion", "contradicted"),
    ]
    rw, _, _ = run_build(monkeypatch, [[para("Stripe processed $1.4 trillion in 2024.", ["1"])]], rs)
    assert "~~Stripe processed $9 trillion~~" in rw.markdown


def test_no_receipted_claims_means_no_rewrite_call(monkeypatch):
    rs = [result("1", "Stripe is based in Mars", "unverified")]
    rw, calls, spent = run_build(monkeypatch, [], rs)
    assert calls == [] and spent == [] and "Needs your check" in rw.markdown


def test_diff_marks_removed_and_added_words():
    d = rewrite.diff_words("Stripe made 9 trillion in sales", "Stripe made 1.4 trillion in sales")
    assert {"op": "removed", "text": "9"} in d and {"op": "added", "text": "1.4"} in d
