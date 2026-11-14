"""Evaluation checkpoint, step 1: run the full loop on the pinned companies.

Saves one JSON per company to eval/runs/ and writes a BLIND label sheet
(eval/label_sheet.csv): claim text and links only, no verdict shown. A human fills
in `label` (true | false | unknowable), `labeller` and `labelled_at`. Never edit
labels after seeing the scores; any change is a logged, disclosed trial.

Run from receipts/:  .venv\\Scripts\\python.exe eval\\run.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
import config  # noqa: E402
from referee import UNVERIFIED  # noqa: E402

# Pinned before seeing any result. Changing this list is a disclosed trial.
COMPANIES = ["OpenAI", "Databricks", "Anthropic", "Mistral AI"]
MAX_CLAIMS = 8  # 4 companies x 8 = 32 claims for the human to label
RUNS = ROOT / "eval" / "runs"
SHEET = ROOT / "eval" / "label_sheet.csv"
FIELDS = ["key", "company", "claim_id", "claim", "system_source_url", "search_link", "label", "labeller", "labelled_at", "notes"]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    config.load_env()
    config.print_key_status()
    if not all(config.key_status().values()):
        print("Missing key: cannot run live.")
        return 2
    RUNS.mkdir(parents=True, exist_ok=True)
    rows = []
    for company in COMPANIES:
        print(f"\n=== {company} ===", flush=True)
        report = agent.run(company, max_claims=MAX_CLAIMS, max_calls=60, emit=_quiet)
        record = agent.report_record(report)
        (RUNS / f"{company.lower().replace(' ', '_')}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"{record['counts']}  calls={record['calls']}", flush=True)
        for c in record["claims"]:
            shown = c["source_url"] if c["verdict"] != UNVERIFIED else ""
            rows.append({
                "key": f"{company}|{c['id']}",
                "company": company,
                "claim_id": c["id"],
                "claim": c["text"],
                "system_source_url": shown,
                "search_link": "https://www.google.com/search?q=" + quote_plus(c["text"]),
                "label": "", "labeller": "", "labelled_at": "", "notes": "",
            })
    if SHEET.exists():
        print(f"\nREFUSING to overwrite {SHEET.name}: it may contain labels. Move it first.")
        return 3
    with open(SHEET, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {len(rows)} claims to {SHEET}")
    return 0


def _quiet(event: dict) -> None:
    if event["type"] == "info":
        print(" ", event["msg"], flush=True)


if __name__ == "__main__":
    sys.exit(main())
