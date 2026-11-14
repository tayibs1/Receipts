"""Smoke test: are the keys live, and what does Linkup actually return?

Loads .env itself, never prints key values. Costs a handful of API calls.
Run:  .venv\\Scripts\\python.exe smoke_test.py
"""

import datetime as dt
import os
import sys
from pathlib import Path


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


load_env(Path(__file__).with_name(".env"))
for name in ("ANTHROPIC_API_KEY", "LINKUP_API_KEY"):
    print(f"{name}: {'key found' if os.environ.get(name) else 'MISSING'}")

# ---- Anthropic -------------------------------------------------------------
if os.environ.get("ANTHROPIC_API_KEY"):
    import anthropic

    client = anthropic.Anthropic()
    for model in ("claude-haiku-5-5", "claude-sonnet-5-5"):
        try:
            r = client.messages.create(
                model=model,
                max_tokens=20,
                messages=[{"role": "user", "content": "Reply with the single word: ready"}],
            )
            print(f"anthropic {model}: OK -> {r.content[0].text.strip()!r}")
        except Exception as e:  # report the real error, not a silent fallback
            print(f"anthropic {model}: FAILED {type(e).__name__}: {str(e)[:160]}")

# ---- Linkup ----------------------------------------------------------------
if os.environ.get("LINKUP_API_KEY"):
    from linkup import LinkupClient

    lc = LinkupClient()
    query = "Anthropic latest funding round valuation"
    since = dt.date.today() - dt.timedelta(days=90)
    seen = {}
    for label, kwargs in (("no date filter", {}), (f"from_date={since}", {"from_date": since})):
        try:
            resp = lc.search(query=query, depth="standard", output_type="searchResults", **kwargs)
            items = list(resp.results)
            print(f"\nlinkup [{label}]: {len(items)} results")
            seen[label] = [getattr(i, "url", "") for i in items]
            for i in items[:5]:
                d = i.model_dump() if hasattr(i, "model_dump") else dict(vars(i))
                content = d.get("content") or ""
                print(f"  fields={sorted(d.keys())} len(content)={len(content)}")
                print(f"  {d.get('name', '')[:70]} | {d.get('url', '')[:80]}")
                print(f"  {content[:140]!r}")
        except Exception as e:
            print(f"linkup [{label}]: FAILED {type(e).__name__}: {str(e)[:200]}")
    labels = list(seen)
    if len(labels) == 2:
        same = seen[labels[0]] == seen[labels[1]]
        print(f"\ndate filter changed the results: {not same}")

sys.exit(0)
