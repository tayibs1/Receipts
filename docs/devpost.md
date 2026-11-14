# Devpost draft (paste after the final audit; every number from a results file)

**Name:** Receipts: no receipt, no claim

**Tagline:** AI briefings do not fail loudly; they fail confidently. Receipts keeps only the claims that can show a source and a quote.

## Problem

A sales rep has five minutes before a call and an AI-written briefing on a company. Some of it is stale or wrong, and nothing in the text says which part. Asking the same model to check itself is grading its own homework.

## What we built

Receipts takes an AI-written company briefing (pasted, or drafted from the model's memory with no web access) and checks it against the live web. It extracts the factual claims, researches each one with Linkup live search, and a plain-code referee decides which claims have a receipt: a source that was really returned and a quote that really appears in it, with the claim's numbers and dates present in the quote and no hedge or denial in the quote's clause. Supported claims go into a rewritten briefing with footnotes; contradicted claims are struck out with the source that disagrees; claims about plans are labelled as plans; anything without a receipt goes to a "Needs your check" list with a manual-search link. Attack mode checks any single claim you type.

## How it works

Claude Haiku 5.5 extracts claims and plans search queries. Linkup returns live results. Claude Sonnet 5.5 *proposes* a verdict, a source URL and a verbatim quote for each claim. `referee.py` decides: it can lower a verdict to "unverified", never raise it. A failed first pass gets one retry with a reworded query. The rewrite step writes the final briefing from receipted claims only, and code checks every number and date in every paragraph against the cited quotes. The call budget is capped per run. It is a pipeline with a visible agent loop and a code-enforced check, not an open-ended autonomous agent.

## APIs, models and data used

Anthropic Claude Haiku 5.5 and Sonnet 5.5; Linkup search API; FastAPI, uvicorn, pydantic (full pinned list in `requirements.txt`); Figma Make for design exploration. No datasets: evaluation uses what the live web returns.

## Honest limits

The referee is conservative and drops some true claims. It checks that a quote is in a source, not that the source is authoritative, and does not check that a contradicting source refers to the same time period. The rewrite check covers numbers and dates, not every statement. Accuracy has not been measured until the hand labels in `eval/label_sheet.csv` are scored: **fill in only numbers from `eval/results.json` here, with the file named.**

## Built during the hackathon

All code was written during the event weekend (14 Nov 2026) with Claude as a coding assistant; the public commit history shows when. Repo: https://github.com/tayibs1/Receipts
