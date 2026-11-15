"""Web app: FastAPI + Server-Sent Events. Run from receipts/:

    .venv\\Scripts\\python.exe app.py        # then open http://127.0.0.1:8765

POST /api/run streams the agent's progress; GET /api/health says whether each API
answered a real call (never a guess); POST /api/attack checks one typed claim.
The server binds exclusively to 127.0.0.1:8765, so a stale second copy cannot
quietly share the port.
"""

from __future__ import annotations

import json
import logging
import queue
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import agent
import config
import llm
import referee

log = logging.getLogger("receipts.app")
PORT = 8765
STATIC = config.ROOT / "static"
SAMPLE = STATIC / "sample_briefing.txt"

app = FastAPI(title="Receipts")
_run_lock = threading.Lock()  # one run at a time: the call budget is per run


class RunRequest(BaseModel):
    company: str = Field("", max_length=80)
    briefing: str = Field("", max_length=8000)
    max_claims: int = Field(8, ge=1, le=10)
    sample: bool = False  # the briefing is the labelled sample, not a real draft
    fresh: bool = False  # ask the models again instead of replaying cached replies


class AttackRequest(BaseModel):
    claim: str = Field(..., min_length=8, max_length=400)
    entity: str = Field("", max_length=80)


# ------------------------------------------------------------------- health

_health: dict = {"at": 0.0, "value": None}
HEALTH_TTL = 600  # seconds; a real call costs a little, so it is cached


def _check_apis() -> dict:
    status = {"anthropic": "offline", "linkup": "offline", "detail": {}}
    keys = config.key_status()
    if keys["ANTHROPIC_API_KEY"]:
        try:
            llm._text(llm.HAIKU, "Reply with the single word: ok", "ok", 10)
            status["anthropic"] = "live"
        except Exception as e:  # report the real error, not a silent fallback
            status["detail"]["anthropic"] = f"{type(e).__name__}: {str(e)[:120]}"
    else:
        status["detail"]["anthropic"] = "no key found"
    if keys["LINKUP_API_KEY"]:
        try:
            import search

            search._get_client().search(
                query="Linkup health check", depth="standard", output_type="searchResults", timeout=20
            )
            status["linkup"] = "live"
        except Exception as e:
            status["detail"]["linkup"] = f"{type(e).__name__}: {str(e)[:120]}"
    else:
        status["detail"]["linkup"] = "no key found"
    return status


@app.get("/api/health")
def health(refresh: bool = False):
    if refresh or _health["value"] is None or time.time() - _health["at"] > HEALTH_TTL:
        _health["value"], _health["at"] = _check_apis(), time.time()
    return _health["value"]


# ------------------------------------------------------------------- labels
# A small page (static/label.html) for the human to hand-label the pinned claims.
# It shows no verdicts. A label, once set, can only be changed with change=true and
# every change is logged to eval/label_changes.log (a disclosed trial, never silent).

LABELS = config.ROOT / "eval" / "label_sheet.csv"
LABEL_LOG = config.ROOT / "eval" / "label_changes.log"
LABEL_FIELDS = ["key", "company", "claim_id", "claim", "system_source_url", "search_link",
                "label", "labeller", "labelled_at", "notes"]
_label_lock = threading.Lock()


class LabelRequest(BaseModel):
    key: str = Field(..., max_length=120)
    label: str = Field(..., pattern="^(true|false|unknowable)$")
    labeller: str = Field(..., min_length=1, max_length=40)
    notes: str = Field("", max_length=300)
    change: bool = False


def _read_labels() -> list[dict]:
    import csv

    with open(LABELS, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@app.get("/api/labels")
def get_labels():
    if not LABELS.exists():
        return JSONResponse({"error": "eval/label_sheet.csv does not exist. Run eval/run.py first."}, status_code=404)
    with _label_lock:
        return _read_labels()


@app.post("/api/label")
def set_label(req: LabelRequest):
    import csv
    import datetime as dt

    with _label_lock:
        rows = _read_labels()
        row = next((r for r in rows if r["key"] == req.key), None)
        if row is None:
            return JSONResponse({"error": "Unknown claim key."}, status_code=404)
        old = (row["label"] or "").strip()
        if old and old != req.label and not req.change:
            return JSONResponse({"error": f'Already labelled "{old}". Changing a label is a disclosed trial: confirm it.'},
                                status_code=409)
        now = dt.datetime.now().isoformat(timespec="seconds")
        if old and old != req.label:
            with open(LABEL_LOG, "a", encoding="utf-8") as log_file:
                log_file.write(f"{now}\t{req.key}\t{old} -> {req.label}\tby {req.labeller}\n")
        row.update(label=req.label, labeller=req.labeller.strip(), labelled_at=now, notes=req.notes.strip())
        tmp = LABELS.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=LABEL_FIELDS)
            w.writeheader()
            w.writerows(rows)
        tmp.replace(LABELS)
        return {"saved": True, "labelled": sum(1 for r in rows if (r["label"] or "").strip()), "of": len(rows)}


# ------------------------------------------------------------------ samples

@app.get("/api/sample")
def sample():
    return {
        "text": SAMPLE.read_text(encoding="utf-8").strip(),
        "label": "Sample briefing: written for this demo with some facts deliberately out of date. "
                 "It is not a real AI draft.",
    }


# --------------------------------------------------------------------- runs

def _summary(report: agent.Report, sample_flag: bool, max_calls: int) -> dict:
    live = cached = 0
    for r in report.results:
        for a in r.attempts:
            if a.search_error:
                continue
            cached += a.cached
            live += not a.cached
    rw = report.rewrite
    return {
        "type": "done",
        "run_id": report.run_id,
        "company": report.company,
        "sample": sample_flag,
        "drafted": report.drafted,
        "briefing": report.briefing,
        "extracted": report.n_extracted,
        "checked": len(report.results),
        "counts": report.counts,
        "calls": report.calls,
        "calls_total": sum(report.calls.values()),
        "max_calls": max_calls,
        "searches": {"live": live, "cached": cached},
        "llm_cache": report.llm_cache,
        "stopped_early": report.stopped_early,
        "cards": [agent.claim_card(r) for r in report.results],
        "rewrite": None if rw is None else {
            "markdown": rw.markdown,
            "paragraphs": [
                {"section": p.section, "text": p.text, "claim_ids": p.claim_ids, "notes": p.notes}
                for p in rw.paragraphs
            ],
            "footnotes": rw.footnotes,
            "rejected": rw.rejected,
            "listed_not_rewritten": rw.fallback,
            "dropped_sections": rw.dropped_sections,
            "diff": rw.diff,
            "error": rw.error,
        },
    }


def _plain_error(e: Exception) -> str:
    if isinstance(e, llm.LLMError):
        return f"The model call failed: {e}"
    if isinstance(e, referee.BudgetExceeded):
        return str(e)
    return f"{type(e).__name__}: {str(e)[:300]}"


@app.post("/api/run")
def run_endpoint(req: RunRequest):
    company, briefing = req.company.strip(), req.briefing.strip()
    if not company and not briefing:
        return JSONResponse({"error": "Enter a company name or paste a briefing."}, status_code=400)
    if not all(config.key_status().values()):
        return JSONResponse({"error": "An API key is missing, so a live check cannot run. See the status badges."},
                            status_code=503)
    if not _run_lock.acquire(blocking=False):
        return JSONResponse({"error": "A check is already running. Wait for it to finish."}, status_code=409)

    events: queue.Queue = queue.Queue()
    max_calls = 60

    def worker() -> None:
        try:
            report = agent.run(company, briefing, max_claims=req.max_claims, max_calls=max_calls,
                               emit=events.put, fresh=req.fresh)
            events.put(_summary(report, req.sample, max_calls))
        except Exception as e:
            log.exception("run failed")
            events.put({"type": "error", "message": _plain_error(e)})
        finally:
            events.put(None)
            _run_lock.release()

    threading.Thread(target=worker, daemon=True).start()

    def stream():
        while True:
            try:
                event = events.get(timeout=15)
            except queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if event is None:
                return
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/attack")
def attack_endpoint(req: AttackRequest):
    if not all(config.key_status().values()):
        return JSONResponse({"error": "An API key is missing, so a live check cannot run."}, status_code=503)
    if not _run_lock.acquire(blocking=False):
        return JSONResponse({"error": "A check is already running. Wait for it to finish."}, status_code=409)
    try:
        res = agent.attack(req.claim, req.entity)
    except Exception as e:
        log.exception("attack failed")
        return JSONResponse({"error": _plain_error(e)}, status_code=500)
    finally:
        _run_lock.release()
    return agent.claim_card(res)


class _NoStore(StaticFiles):
    """Static files are never cached, so a restart can never show a stale UI."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


app.mount("/", _NoStore(directory=STATIC, html=True), name="static")


# --------------------------------------------------------------------- main

def _exclusive_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: no silent second listener
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(100)
    sock.set_inheritable(True)
    return sock


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    config.load_env()
    config.print_key_status()
    try:
        sock = _exclusive_socket(PORT)
    except OSError as e:
        print(f"Port {PORT} is already in use ({e}). Stop the other copy first: "
              f"Get-NetTCPConnection -LocalPort {PORT}")
        return 1
    print(f"Receipts on http://127.0.0.1:{PORT}")
    uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])
    return 0


if __name__ == "__main__":
    sys.exit(main())
