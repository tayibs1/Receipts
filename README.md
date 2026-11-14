# Receipts: no receipt, no claim

Receipts checks an AI-written company briefing against the live web and keeps only the claims that can show a receipt: a source, and a quote that really appears in it. It is built for the Imperial AI Hackathon (14-15 Nov 2026), Autonomous Agents track.

> AI briefings do not fail loudly; they fail confidently.

## The problem

A sales rep has five minutes before a call and a briefing written by an AI model. Some of it is stale or wrong, and nothing in the text says which part. Asking the same model to check itself does not help: it grades its own homework.

## What it does

1. **Input:** paste a briefing, or give a company name and the model drafts one from its own memory (no web access, on purpose).
2. **Extract:** up to 20 atomic factual claims, ranked by impact (numbers and dates first, then people and entities). The top N (default 8 in the web app) are checked.
3. **Research each claim** with [Linkup](https://www.linkup.so) live search: plan a query, search, ask the model to *propose* a verdict with a source URL and a verbatim quote.
4. **Referee (plain code, `referee.py`) decides.** The model can only propose. The referee can lower a verdict to "unverified", never raise it. A claim is kept only if the source is one of the returned results, the quote really appears in it, the claim's numbers and dates appear in the quote, and the quote is not a rumour, plan or denial.
5. **One retry** with a reworded query if the first pass finds no receipt.
6. **Policy:** supported claims go in the final briefing with footnotes; contradicted claims are struck out with the contradicting source; claims about plans are labelled "stated as a plan, not a fact"; everything else goes to "Needs your check" with a manual-search link.
7. **Rewrite:** the model writes the final briefing from receipted claims only; code checks every number and date in every paragraph against the cited quotes (R9) and regenerates or lists the claims plainly if a paragraph fails.
8. **Attack mode:** type any single claim and run steps 3 to 4 on it.

**Honest framing:** this is a pipeline with a visible agent loop (plan, search, retry, decide, rewrite) and a code-enforced check, not an open-ended autonomous agent. It does not write or run code. "The AI proposes, code decides."

## How to run

Requires Python 3.11 and two API keys (never commit them).

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
# create .env (git-ignored) with:
#   ANTHROPIC_API_KEY=...
#   LINKUP_API_KEY=...
.venv\Scripts\python.exe app.py                  # web app on http://127.0.0.1:8765
.venv\Scripts\python.exe agent.py "Databricks"   # same loop in the terminal
.venv\Scripts\python.exe -m pytest -q            # tests (no network, no keys)
```

The app prints "key found" or "MISSING" for each key at startup, shows a live/offline badge for each API in the header (from a real call, not a guess), and shows a live/cached badge after each run. It binds `127.0.0.1:8765` exclusively. Every Linkup search is cached on disk in `cache/`, so repeat runs cost no search credits.

## APIs, models and datasets used

| What | Use |
|---|---|
| Anthropic Claude Haiku 5.5 (`claude-haiku-5-5`) | extract claims, plan and reword search queries |
| Anthropic Claude Sonnet 5.5 (`claude-sonnet-5-5`) | memory-only draft, judge (proposes verdict, source and quote), rewrite |
| Linkup search API (`linkup-sdk` 0.24.1) | live web search, `searchResults` output |
| FastAPI 0.162.7, uvicorn 0.54.0, starlette 1.10.0, pydantic 2.14.3, anthropic 2.8.0, httpx 0.28.1, pytest 9.2.0 | app, validation, SDKs, tests (all pinned in `requirements.txt`) |
| Figma Make | UI design exploration; evidence in `docs/figma/` |
| Datasets | none. Evaluation uses whatever the live web returns for each query. |

## Evidence (every number is copied from a results file)

First real-data checkpoint, `eval/results.json`: 4 companies (OpenAI, Databricks, Anthropic, Mistral AI), 8 claims each, 32 claims.

| Result | Value | Source file |
|---|---|---|
| Claims checked | 32 | `eval/results.json` |
| Supported / contradicted / plans / needs your check | 13 / 0 / 0 / 19 | `eval/results.json` |
| Times the judge proposed "supported" | 43 | `eval/results.json` |
| Kept by the referee / lowered by the referee | 13 / 30 (R8: 18, R2: 7, R7: 4, R1: 1) | `eval/results.json` |

Two later trials on the same 32 claims after referee fixes (`eval/results_fix1.json`, `eval/results_fix2.json`): supported 19 and 14. The spread comes from the models, not from rule changes (the SDK exposes no temperature setting), so **any single number here is noisy**. These counts measure what the referee kept, **not accuracy**: the 32 claims have not yet been hand-labelled, so false-positive and false-negative rates are not measured and no accuracy is claimed. Labels go in `eval/label_sheet.csv`; `eval/score.py` computes the rates once they exist.

## Honest limits

- The referee is conservative. It drops some true claims: hedge words in the quote's clause (`reportedly`, `likely`, `will`), numbers the quote does not repeat, and quotes that do not share enough words with the claim. Measured so far only as the kept/lowered counts above.
- A quote can still hide a hedge outside its clause. R2 does not check units beyond scale suffixes (million, billion, %).
- "Contradicted" means a source says something different; the referee does not check that both statements refer to the same time period. A contradiction from an older source is labelled "older source, may be stale".
- The referee does not judge how authoritative a source is. Some receipts come from low-quality sites.
- Linkup only returns what it finds. `published_at` is missing on about half of results, so the freshness label is "recent", "older source, may be stale" or "date unknown". It is a freshness check, not date verification.
- The rewrite check (R9) blocks invented numbers and dates. It does not prove the prose adds no non-numeric statement.
- The audit log (`audit.jsonl`, git-ignored) is a plain log. It is not tamper-proof.
- The "sample briefing" is written for the demo with some facts deliberately out of date. It is labelled as a sample everywhere it is shown and is not a real AI draft.

## Claims traced to code

Line numbers are as of the commit that added this file.

| Claim | Where |
|---|---|
| The model cannot invent a source: the URL must be a returned result and the quote must appear in it (R1) | `referee.py:284`, `referee.py:286`, `quote_in_content` at `referee.py:108` |
| The referee can only lower a verdict, never raise one | `decide` at `referee.py:256` (every failure path returns "unverified") |
| Numbers and dates in a supported claim must appear in the quote (R2) | `referee.py:308-311`, `_missing_specifics` at `referee.py:221` |
| Hedged or denied quotes do not support a fact; claims about plans are labelled (R7) | `referee.py:319`, `referee.py:323`, `referee.py:326` |
| A failed search becomes "unverified", never a guess (R6) | `referee.py:274` |
| Claim relevance is checked (R8) | `referee.py:290`, `referee.py:304` |
| Every number and date in a rewritten paragraph comes from a cited quote (R9) | `check_paragraph` at `referee.py:340`, called for every paragraph at `rewrite.py:52` |
| Call budget enforced and visible | `Budget` at `referee.py:369`, `Meter` at `agent.py:104`, R4 at `agent.py:246` |
| Search results are treated as data, not instructions | `llm.py:235` |
| Searches are cached; a cache hit costs no budget | `search.py:103` |
| Freshness label from the source's own `published_at` | `agent.py:159` |
| Every run is appended to `audit.jsonl` | `_write_audit` at `agent.py:427` |
| One server on the port; a stale second copy cannot share it | `app.py:225` |
| Live/offline status comes from a real API call | `health` at `app.py:87` |

## What was built during the hackathon

Everything in this repository was written during the hackathon weekend (14 Nov 2026) with Claude as a coding assistant; the commit history shows when. No code from earlier projects was reused. The design was explored in Figma Make (`docs/figma/FIGMA-EVIDENCE.md` says exactly what was and was not done).

## Layout

```
app.py       FastAPI app, server-sent events, health and attack endpoints
agent.py     the loop: rank, plan, search, judge, referee, retry, freshness, audit log
referee.py   plain-code rules R0-R9 and the call budget
rewrite.py   rewrite step, footnotes, draft-versus-verified diff
llm.py       Anthropic wrappers (Haiku 5.5, Sonnet 5.5)
search.py    Linkup wrapper with disk cache
static/      plain HTML, CSS and JS (no build step)
eval/        checkpoint runs, label sheet, scoring, disclosed trials
docs/figma/  design evidence
tests/       tests (no network)
```
