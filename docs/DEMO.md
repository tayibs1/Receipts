# Demo script (about 2.5 minutes) and prepared answers

Run from a cold start: `.venv\Scripts\python.exe app.py`, open http://127.0.0.1:8765, confirm both header badges say **live** (or say "offline" out loud). Rehearse with companies already searched (the badge will say Cached or Mixed; say so). Record a backup screen capture before the presentation.

Every number you say must come from a results file (`eval/results.json`, `eval/results_fix1.json`, `eval/results_fix2.json`) or from the screen in front of you. Do not quote an accuracy rate until `eval/score.py` has produced one from hand labels.

| Time | Do | Say |
|---|---|---|
| 0:00 | Hands-up question | "Who has pasted an AI answer into something you sent without checking?" |
| 0:15 | Name the track, the Linkup bounty and the Figma prize | "Autonomous Agents. It uses Linkup live search, and the design started in Figma Make; the evidence is in the repo." |
| 0:30 | Click **Use sample briefing**, then **Check it** | "Sarah has five minutes before a call and an AI-written briefing. This one is a labelled sample with some facts deliberately out of date, so you can see the red state. The claims arrive one by one; this is the trace." |
| 1:00 | Open a red card, then its evidence drawer | "A source says otherwise. Here is the quote, the link, and the rules the referee applied. The model proposed; code decided." |
| 1:20 | Show an amber card, click **Search manually** | "No receipt, so it is not stated as fact. It goes to 'Needs your check', never a guess." |
| 1:40 | Scroll to the rewrite; toggle **What changed**; **Copy as Markdown** | "Every number and date in this briefing is checked against a cited quote by code." |
| 2:00 | Attack mode: type one claim | "Any claim, same pipeline." |
| 2:10 | One number from `eval/results.json` and one limit | "On 32 claims across four companies the judge proposed 'supported' 43 times and the referee kept 13 (`eval/results.json`). It is conservative: it drops some true claims. We have not measured accuracy yet." (update if labels exist) |
| 2:30 | Show `docs/figma/` | "Designed and iterated in Figma Make. One decision that changed: the contrast audit." Only say what actually happened (see `docs/figma/FIGMA-EVIDENCE.md`). |

## Honest framing (say it early)

It is a pipeline with a visible agent loop (plan, search, retry, decide, rewrite) and a code-enforced check, not an open-ended autonomous agent. It does not write or run code.

## Prepared hard questions

- **Why not just ask Claude with web search?** The model would grade its own work. Here the model only proposes a source and a quote; plain code checks the source was really returned, the quote really appears in it, and the numbers and dates match. A fabricated receipt is rejected (R1, R2).
- **Is this an agent?** It plans queries, retries with new wording, applies a policy and rewrites, inside a call budget. It is not open-ended, and we say so.
- **What does the referee get wrong?** It is conservative and drops some true claims (hedge words, numbers the quote does not repeat). Counts are in the README; accuracy is not measured until hand labels exist.
- **Can it be fooled by a bad source?** Yes: it checks that the quote is in the source, not that the source is authoritative. Contradictions are also not checked for the same time period.
- **Is the red state real?** In the sample, the outdated facts were planted and the label says so. With a live draft we show whatever happens.
- **How do you know every number is right?** Each figure in the README names its results file; the claims-to-code table points at file and line.
