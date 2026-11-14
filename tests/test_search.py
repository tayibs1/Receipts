"""Search wrapper: cache behaviour and budget accounting, with a fake Linkup client."""

import datetime as dt
from types import SimpleNamespace

import pytest

import search


class FakeClient:
    def __init__(self, fail=0):
        self.calls = 0
        self.fail = fail

    def search(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail:
            raise TimeoutError("slow")
        r = SimpleNamespace(name="N", url="https://x.com/1", content="body text", published_at=None)
        return SimpleNamespace(results=[r])


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(search, "CACHE_DIR", tmp_path)
    client = FakeClient()
    monkeypatch.setattr(search, "_get_client", lambda: client)
    monkeypatch.setattr(search.time, "sleep", lambda s: None)
    return client


def test_cache_hit_spends_nothing(fake):
    spent = []
    first = search.search("q", spend=lambda: spent.append(1))
    second = search.search("q", spend=lambda: spent.append(1))
    assert not first.cached and second.cached
    assert fake.calls == 1 and len(spent) == 1
    assert second.hits[0].url == "https://x.com/1" and second.hits[0].published_at is None


def test_cache_key_includes_depth_and_date(fake):
    search.search("q")
    search.search("q", from_date=dt.date(2026, 8, 1))
    search.search("q", depth="deep")
    assert fake.calls == 3


def test_failure_is_returned_not_cached_and_retry_spends(fake):
    fake.fail = 5
    spent = []
    out = search.search("q", spend=lambda: spent.append(1))
    assert out.error and "TimeoutError" in out.error
    assert fake.calls == 2 and len(spent) == 2  # one retry, each network attempt counted
    fake.fail = 0
    assert not search.search("q").cached  # the failure left nothing in the cache
