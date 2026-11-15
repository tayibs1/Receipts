"""Model-reply cache and HTML-entity cleanup: no network."""

import llm
import search


class FakeMsg:
    def __init__(self, text):
        self.content = [type("B", (), {"type": "text", "text": text})()]
        self.stop_reason = "end_turn"


def setup_fake(monkeypatch, tmp_path, replies):
    monkeypatch.setattr(llm, "LLM_CACHE_DIR", tmp_path)
    calls = []

    class Msgs:
        def create(self, **kw):
            calls.append(kw)
            return FakeMsg(replies[min(len(calls) - 1, len(replies) - 1)])

    monkeypatch.setattr(llm, "_get_client", lambda: type("C", (), {"messages": Msgs()})())
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    return calls


def test_validated_reply_is_replayed_from_cache(monkeypatch, tmp_path):
    calls = setup_fake(monkeypatch, tmp_path, ['{"query": "acme funding 2024"}'])
    llm.set_cache(True)
    assert llm._json(llm.HAIKU, "s", "u", llm.QueryOut, 50).query == "acme funding 2024"
    assert llm._json(llm.HAIKU, "s", "u", llm.QueryOut, 50).query == "acme funding 2024"
    assert len(calls) == 1 and llm.cache_stats()["hits"] == 1


def test_fresh_mode_skips_the_cache(monkeypatch, tmp_path):
    calls = setup_fake(monkeypatch, tmp_path, ['{"query": "a b c"}'])
    llm.set_cache(True)
    llm._json(llm.HAIKU, "s", "u", llm.QueryOut, 50)
    llm.set_cache(False)
    llm._json(llm.HAIKU, "s", "u", llm.QueryOut, 50)
    assert len(calls) == 2
    llm.set_cache(True)


def test_invalid_reply_is_never_cached(monkeypatch, tmp_path):
    calls = setup_fake(monkeypatch, tmp_path, ["not json", '{"query": "ok query"}'])
    llm.set_cache(True)
    assert llm._json(llm.HAIKU, "s", "u", llm.QueryOut, 50).query == "ok query"
    assert all("not json" not in p.read_text(encoding="utf-8") for p in tmp_path.iterdir())


def test_html_entities_are_decoded_in_search_hits():
    h = search._clean(search.Hit("Rate Hits $65B &#8211; Unite.AI", "https://x", "Smith &amp; Co said", None))
    assert h.name == "Rate Hits $65B – Unite.AI" and h.content == "Smith & Co said"
