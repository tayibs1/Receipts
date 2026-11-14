"""Web app: validation, the sample, and the SSE stream, with the agent mocked."""

import json

import pytest
from fastapi.testclient import TestClient

import agent
import app as app_mod
import config
import referee
from referee import Claim, Decision

client = TestClient(app_mod.app)


@pytest.fixture(autouse=True)
def keys_present(monkeypatch):
    monkeypatch.setattr(config, "key_status", lambda: {"ANTHROPIC_API_KEY": True, "LINKUP_API_KEY": True})


def test_sample_is_labelled_as_a_sample():
    j = client.get("/api/sample").json()
    assert "Sample briefing" in j["label"] and "deliberately out of date" in j["label"]
    assert len(j["text"]) > 100


def test_empty_request_is_a_plain_400():
    r = client.post("/api/run", json={"company": " ", "briefing": ""})
    assert r.status_code == 400 and "company" in r.json()["error"].lower()


def test_missing_key_is_reported_not_hidden(monkeypatch):
    monkeypatch.setattr(config, "key_status", lambda: {"ANTHROPIC_API_KEY": True, "LINKUP_API_KEY": False})
    r = client.post("/api/run", json={"company": "Acme"})
    assert r.status_code == 503 and "key" in r.json()["error"].lower()


def test_run_streams_events_then_done(monkeypatch):
    def fake_run(company, briefing, *, max_claims, max_calls, emit):
        emit({"type": "info", "msg": "extracting factual claims"})
        res = agent.ClaimResult(claim=Claim("1", "Acme was founded in 2001", "Acme"),
                                decision=Decision("1", referee.UNVERIFIED, rules=[("R0", "proposal was unverified")]))
        emit({"type": "decision", "claim_id": "1", "verdict": "unverified", "trace": "t",
              "card": agent.claim_card(res), "calls": 3, "max_calls": max_calls})
        return agent.Report("abc", company, "draft", True, 1, [res], {"plan": 1}, "", None)

    monkeypatch.setattr(app_mod.agent, "run", fake_run)
    with client.stream("POST", "/api/run", json={"company": "Acme"}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert [e["type"] for e in events] == ["info", "decision", "done"]
    done = events[-1]
    assert done["counts"]["unverified"] == 1 and done["rewrite"] is None
    assert done["cards"][0]["source_url"] == "" and done["cards"][0]["quote"] == ""  # no receipt, no source shown


def test_errors_reach_the_stream_in_plain_words(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("search exploded")

    monkeypatch.setattr(app_mod.agent, "run", boom)
    with client.stream("POST", "/api/run", json={"company": "Acme"}) as r:
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    assert events[-1]["type"] == "error" and "search exploded" in events[-1]["message"]
    # the lock is released after a failure, so the next request is judged on its own merits
    assert client.post("/api/run", json={"company": ""}).status_code == 400


def test_attack_returns_a_card(monkeypatch):
    res = agent.ClaimResult(claim=Claim("A1", "Acme was founded in 2001", "Acme"),
                            decision=Decision("A1", referee.UNVERIFIED))
    monkeypatch.setattr(app_mod.agent, "attack", lambda claim, entity="": res)
    r = client.post("/api/attack", json={"claim": "Acme was founded in 2001"})
    assert r.status_code == 200 and r.json()["verdict"] == "unverified"
