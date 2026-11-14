"""Evaluation checkpoint, step 2: score the runs against the human labels.

Reads eval/runs/*.json and eval/label_sheet.csv, writes eval/results.json and
eval/claims.jsonl (claims merged with labels, the pinned hand-labelled set).
Label-free numbers are always computed; label-based numbers appear only for
claims a human has labelled (true | false | unknowable).

Run from receipts/:  .venv\\Scripts\\python.exe eval\\score.py
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "eval" / "runs"
SHEET = ROOT / "eval" / "label_sheet.csv"
RESULTS = ROOT / "eval" / "results.json"
CLAIMS = ROOT / "eval" / "claims.jsonl"
GOOD = ("supported", "forward_looking")  # verdicts that carry a receipt


def load_runs(runs_dir: Path = RUNS) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(runs_dir.glob("*.json"))]


def load_labels(path: Path = SHEET) -> dict[str, dict]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("label") or "").strip().lower() in ("true", "false", "unknowable")]
    return {r["key"]: r for r in rows}


def score(runs: list[dict], labels: dict[str, dict]) -> dict:
    counts = {"supported": 0, "contradicted": 0, "forward_looking": 0, "unverified": 0}
    proposed_supported = kept = 0
    downgraded_by_rule: dict[str, int] = {}
    calls_total = 0
    merged = []
    for run in runs:
        calls_total += sum(run["calls"].values())
        for c in run["claims"]:
            counts[c["verdict"]] += 1
            for a in c["attempts"]:
                if a.get("proposal", {}).get("verdict") == "supported":
                    proposed_supported += 1
                    if a["verdict"] in GOOD:
                        kept += 1
                    else:
                        rule = a["rules"][-1][0] if a["rules"] else "?"
                        downgraded_by_rule[rule] = downgraded_by_rule.get(rule, 0) + 1
            key = f"{run['company']}|{c['id']}"
            lab = labels.get(key)
            merged.append({
                "key": key, "claim": c["text"], "verdict": c["verdict"],
                "rules": c["rules"], "source_url": c["source_url"], "quote": c["quote"],
                "label": lab["label"].strip().lower() if lab else None,
                "labeller": lab["labeller"] if lab else None,
                "labelled_at": lab["labelled_at"] if lab else None,
                "notes": lab["notes"] if lab else None,
            })

    labelled = [m for m in merged if m["label"]]
    fp = [m for m in labelled if m["verdict"] in GOOD and m["label"] == "false"]
    supported_on_unknowable = [m for m in labelled if m["verdict"] in GOOD and m["label"] == "unknowable"]
    wrong_contradiction = [m for m in labelled if m["verdict"] == "contradicted" and m["label"] == "true"]
    true_claims = [m for m in labelled if m["label"] == "true"]
    dropped_true = [m for m in true_claims if m["verdict"] == "unverified"]
    kept_true = [m for m in true_claims if m["verdict"] in GOOD]
    caught_false = [m for m in labelled if m["label"] == "false" and m["verdict"] == "contradicted"]

    def brief(ms):
        return [{k: m[k] for k in ("key", "claim", "verdict", "rules", "label", "notes")} for m in ms]

    n_claims = sum(counts.values())
    return {
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "companies": [r["company"] for r in runs],
        "runs": len(runs),
        "claims_checked": n_claims,
        "verdict_counts": counts,
        "llm_proposed_supported": {
            "attempts": proposed_supported,
            "kept_by_referee": kept,
            "downgraded_by_referee": proposed_supported - kept,
            "downgraded_by_rule": downgraded_by_rule,
        },
        "average_calls_per_run": round(calls_total / len(runs), 1) if runs else None,
        "hand_labels": {
            "labelled_claims": len(labelled),
            "of_total": n_claims,
            "label_counts": {k: sum(1 for m in labelled if m["label"] == k) for k in ("true", "false", "unknowable")},
            "false_positives_supported_but_false": brief(fp),
            "supported_but_unknowable": brief(supported_on_unknowable),
            "wrong_contradictions_contradicted_but_true": brief(wrong_contradiction),
            "true_claims": len(true_claims),
            "true_claims_with_receipt": len(kept_true),
            "false_negatives_true_but_unverified": brief(dropped_true),
            "false_claims_caught_as_contradicted": len(caught_false),
        } if labelled else "pending: no hand labels yet",
    }, merged


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    runs = load_runs()
    if not runs:
        print("No runs in eval/runs/. Run eval/run.py first.")
        return 2
    results, merged = score(runs, load_labels())
    RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    CLAIMS.write_text("\n".join(json.dumps(m, ensure_ascii=False) for m in merged) + "\n", encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
