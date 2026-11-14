"""Linkup wrapper: timeout, one retry, disk cache, budget accounting.

Every successful search is cached on disk, keyed by (query, depth, from_date), so
repeat runs cost nothing and demos can run from cache. A cached answer never
spends budget. Failures are returned as `error`, never cached, never silent.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import config

log = logging.getLogger("receipts.search")

CACHE_DIR = config.ROOT / "cache"
TIMEOUT_SECONDS = {"standard": 30.0, "deep": 60.0}


@dataclass(frozen=True)
class Hit:
    name: str
    url: str
    content: str
    published_at: str | None = None


@dataclass
class SearchOutcome:
    hits: list[Hit] = field(default_factory=list)
    cached: bool = False
    error: str | None = None


_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            config.load_env()
            from linkup import LinkupClient

            _client = LinkupClient()  # reads LINKUP_API_KEY from the environment
        return _client


def _cache_path(query: str, depth: str, from_date: dt.date | None) -> Path:
    raw = json.dumps([query.strip().lower(), depth, str(from_date) if from_date else None])
    return CACHE_DIR / (hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24] + ".json")


def _read_cache(path: Path) -> list[Hit] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Hit(**h) for h in data["hits"]]
    except (OSError, ValueError, KeyError, TypeError) as e:
        log.warning("ignoring unreadable cache file %s: %s: %s", path.name, type(e).__name__, e)
        return None


def _write_cache(path: Path, query: str, depth: str, from_date: dt.date | None, hits: list[Hit]) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "query": query,
            "depth": depth,
            "from_date": str(from_date) if from_date else None,
            "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
            "hits": [asdict(h) for h in hits],
        }
        # unique temp name: two threads can search the same query at once
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        log.warning("could not write cache %s: %s: %s", path.name, type(e).__name__, e)


def search(
    query: str,
    *,
    depth: str = "standard",
    from_date: dt.date | None = None,
    spend: Callable[[], None] | None = None,
    retries: int = 1,
) -> SearchOutcome:
    """Search Linkup. `spend` is called once per live network attempt (not for cache
    hits) and may raise BudgetExceeded, which propagates to the caller."""
    path = _cache_path(query, depth, from_date)
    cached = _read_cache(path)
    if cached is not None:
        return SearchOutcome(cached, cached=True)

    last_error = "unknown error"
    for attempt in range(retries + 1):
        if spend:
            spend()
        try:
            resp = _get_client().search(
                query=query,
                depth=depth,
                output_type="searchResults",
                from_date=from_date,
                timeout=TIMEOUT_SECONDS.get(depth, 30.0),
            )
            hits = [
                Hit(
                    name=getattr(r, "name", "") or "",
                    url=getattr(r, "url", "") or "",
                    content=getattr(r, "content", "") or "",
                    published_at=str(r.published_at) if getattr(r, "published_at", None) else None,
                )
                for r in resp.results
            ]
            _write_cache(path, query, depth, from_date, hits)
            return SearchOutcome(hits)
        except Exception as e:  # real error is logged and returned, never swallowed
            last_error = f"{type(e).__name__}: {str(e)[:200]}"
            log.warning("linkup search failed (attempt %d): %s", attempt + 1, last_error)
            if attempt < retries:
                time.sleep(1.0)
    return SearchOutcome(error=last_error)
