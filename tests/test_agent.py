"""Agent logic with mocked llm and search: no network, no keys."""

import datetime as dt
import json

import pytest

import agent
import llm
import referee
import search
from referee import Budget, BudgetExceeded, Claim

TODAY = dt.date(2026, 11, 14)
CONTENT = "Stripe reported total payment volume of $1.4 trillion in 2024, up 38 percent from 2023."
HIT = search.Hit("Example News", "https://example.com/a", CONTENT, "2026-10-01")
CLAIM = Claim("1", "Stripe reported payment volume of $1.4 trillion in 2024", "Stripe")
GOOD_QUOTE = "Stripe reported total payment volume of $1.4 trillion in 2024"


def make_ctx(max_calls=60, reserve=1):
    events = []
    meter = agent.Meter(Budget(max_calls=max_calls), reserve=reserve)
    return agent.Ctx(meter, events.append, TODAY), events


@pytest.fixture
def mocks(monkeypatch):
    state = {"search_calls": 0, "judge_calls": 0, "judge_out": None, "hits": [HIT], "error": None}

    def fake_search(query, *, depth="standard", from_date=None, spend=None, retries=1):
        state["search_calls"] += 1
        if spend:
            spend()
        if state["error"]:
            return search.SearchOutcome(error=state["error"])
        return search.SearchOutcome(list(state["hits"]))

    def fake_judge(claim_text, entity, today, hits):
        state["judge_calls"] += 1
        return state["judge_out"]

    monkeypatch.setattr(agent.search, "search", fake_search)
    monkeypatch.setattr(agent.llm, "judge", fake_judge)
    monkeypatch.setattr(agent.llm, "plan_query", lambda *a, **k: "stripe payment volume 2024")
    monkeypatch.setattr(agent.llm, "reword_query", lambda *a, **k: "stripe annual report volume")
    return state


def test_supported_is_kept_with_freshness(mocks):
    mocks["judge_out"] = llm.JudgeOut(verdict="supported", source_url=HIT.url, quote=GOOD_QUOTE, reason="ok")
    ctx, events = make_ctx()
    res = agent.check_claim(CLAIM, ctx)
    assert res.decision.verdict == referee.SUPPORTED
    assert res.freshness == "recent"
    assert res.source_name == "Example News"
    assert len(res.attempts) == 1  # no retry needed
    assert events[-1]["type"] == "decision"


def test_fabricated_quote_is_downgraded_and_retried_once(mocks):
    mocks["judge_out"] = llm.JudgeOut(
        verdict="supported", source_url=HIT.url, quote="Stripe processed 9 trillion dollars in 2024 overall"
    )
    ctx, _ = make_ctx()
    res = agent.check_claim(CLAIM, ctx)
    assert res.decision.verdict == referee.UNVERIFIED
    assert len(res.attempts) == 2  # first try plus exactly one retry
    assert mocks["search_calls"] == 2
    assert res.attempts[0].downgraded_from == "supported"
    assert res.attempts[0].rules[-1][0] == "R1"


def test_search_failure_is_unverified_without_judge_or_retry(mocks):
    mocks["error"] = "TimeoutError: boom"
    ctx, _ = make_ctx()
    res = agent.check_claim(CLAIM, ctx)
    assert res.decision.verdict == referee.UNVERIFIED
    assert res.decision.rules[-1][0] == "R6"
    assert mocks["judge_calls"] == 0
    assert mocks["search_calls"] == 1  # search errors are not retried at the claim level


def test_budget_exhaustion_is_visible_r4(mocks):
    mocks["judge_out"] = llm.JudgeOut(verdict="supported", source_url=HIT.url, quote=GOOD_QUOTE)
    ctx, events = make_ctx(max_calls=2, reserve=0)  # plan + search, then judge is refused
    res = agent.check_claim(CLAIM, ctx)
    assert res.decision.verdict == referee.UNVERIFIED
    assert res.decision.rules[-1][0] == "R4"
    assert "budget" in res.trace


def test_reserve_keeps_calls_free_for_rewrite():
    meter = agent.Meter(Budget(max_calls=3), reserve=1)
    meter.spend("a")
    meter.spend("b")
    with pytest.raises(BudgetExceeded):
        meter.spend("c")
    meter.spend("rewrite", reserve=False)  # the reserved call is still available


def test_freshness_labels():
    assert agent.freshness_label("2026-10-01", TODAY) == "recent"
    assert agent.freshness_label("2024-01-01", TODAY) == "older source, may be stale"
    assert agent.freshness_label(None, TODAY) == "date unknown"
    assert agent.freshness_label("not a date", TODAY) == "date unknown"


def test_rank_puts_numbers_and_dates_first():
    items = [
        (Claim("1", "Acme is a leader in widgets"), "other", ""),
        (Claim("2", "Acme CEO is Jane Doe"), "person", ""),
        (Claim("3", "Acme raised $50 million in March"), "number", ""),
    ]
    assert [c.id for c, _, _ in agent.rank_claims(items)] == ["3", "2", "1"]


def test_run_end_to_end_mocked(mocks, monkeypatch, tmp_path):
    mocks["judge_out"] = llm.JudgeOut(verdict="supported", source_url=HIT.url, quote=GOOD_QUOTE)
    monkeypatch.setattr(agent.llm, "draft_briefing", lambda company: "draft text")
    monkeypatch.setattr(
        agent.llm,
        "extract_claims",
        lambda text, max_claims=20: [llm.ClaimOut(text=CLAIM.text, entity="Stripe", kind="number")],
    )
    audit = tmp_path / "audit.jsonl"
    report = agent.run("Stripe", today=TODAY, audit_path=audit)
    assert report.counts[referee.SUPPORTED] == 1
    assert report.drafted
    record = json.loads(audit.read_text(encoding="utf-8").splitlines()[0])
    assert record["claims"][0]["verdict"] == "supported"
    assert "draft" in record["calls"] and "judge" in record["calls"]
    text = agent.render_text(report)
    assert GOOD_QUOTE in text and "[freshness check: recent]" in text
