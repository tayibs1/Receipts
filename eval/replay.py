"""Replay the pinned claims through the CURRENT agent code (a disclosed trial).

Takes the exact claims saved in eval/runs/*.json (the baseline run) so the human
labels still apply, re-runs plan, search, judge and referee on each, and writes
the same record format to eval/runs_<tag>/. Score it with:
    .venv\\Scripts\\python.exe eval\\score.py --runs eval\\runs_<tag> --out eval\\results_<tag>.json

Run from receipts/:  .venv\\Scripts\\python.exe eval\\replay.py fix1
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
import config  # noqa: E402
import llm  # noqa: E402
from referee import Budget, Claim  # noqa: E402


def main(tag: str) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    config.load_env()
    config.print_key_status()
    if not all(config.key_status().values()):
        print("Missing key: cannot run live.")
        return 2
    llm.set_cache(False)  # a trial measures the models, not a replay of cached replies
    out_dir = ROOT / "eval" / f"runs_{tag}"
    out_dir.mkdir(exist_ok=True)
    for path in sorted((ROOT / "eval" / "runs").glob("*.json")):
        base = json.loads(path.read_text(encoding="utf-8"))
        meter = agent.Meter(Budget(max_calls=200), reserve=0)
        ctx = agent.Ctx(meter, lambda e: None, dt.date.today())
        items = [(Claim(c["id"], c["text"], c["entity"]), c["kind"], "") for c in base["claims"]]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda it: agent.check_claim(it[0], ctx, it[1], it[2]), items))
        report = agent.Report(
            run_id=f"{tag}-{base['run_id']}", company=base["company"], briefing=base["briefing"],
            drafted=base["briefing_drafted_by_model"], n_extracted=base["claims_extracted"],
            results=results, calls=dict(meter.by_kind),
        )
        rec = agent.report_record(report)
        (out_dir / path.name).write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{base['company']}: baseline {base['counts']} -> {tag} {rec['counts']}  calls={rec['calls']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "fix1"))
