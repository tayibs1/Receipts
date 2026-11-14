# Figma Make prompt for Receipts (paste the block below as is)

Keep after generating: the Figma file link, and 3 screenshots (the frames, the component list or auto-layout, one before/after of a change you made). They go in the presentation as evidence for the Figma prize.

After the first result, send follow-ups one at a time (see "Refinements" at the end).

---

Design a calm, high-trust desktop web app (1440 px wide, light theme) called **Receipts** with the tagline **"No receipt, no claim."** It checks an AI-written company briefing against live web sources and keeps only the claims that can show a receipt: a source and a quote that really appears in it. Make it feel like a careful editor's tool, not a flashy dashboard. Create these five screens as separate frames, using shared components.

**Design system**
- One sans-serif family (Inter). Three sizes only: 13 px small, 15 px body, 22 px heading. Generous spacing on an 8-point grid. Rounded corners 8 px. Thin 1 px borders, almost no shadows.
- Neutral greys for surfaces; one dark ink colour for text. Four status colours, each with an icon so colour is never the only signal, and each readable (text contrast at least 4.5:1 on its tinted background):
  - Supported: green, check icon.
  - Contradicted: red, cross icon.
  - Needs your check: amber, question-mark icon.
  - Plan (stated as a plan, not a fact): blue, clock icon.
- Components to build once and reuse: Claim card (status badge, claim text, source name, link, freshness label, matched quote with the matching words highlighted), Counts bar, Trace line, Evidence drawer, Badge (Live / Cached), Primary button, Text input.

**Frame 1: Input.** Header with the logo "Receipts", tagline, and a small Live badge. A large paste area labelled "Paste an AI-written briefing", a company name field as an alternative ("or enter a company and we'll draft one"), example company chips, a "Use sample briefing" link, and a primary button "Check it". A one-line note: "We search the live web and keep only what has a source."

**Frame 2: Running.** Two columns. Left column titled "What the AI says from memory": a briefing paragraph with each factual claim as a highlighted inline chip. Right column titled "What survives with receipts": claim cards appearing one by one in different states. Above them a progress strip ("Checking claim 4 of 9") and a small call-budget meter ("14 of 40 searches"). Below the columns a Trace panel: one readable line per decision, for example `Claim 5 "revenue $10B" → searched "annual revenue" → no source → tried again with new wording → source found → quote says $12B → Contradicted`.

**Frame 3: Result.** A Counts bar at the top: "9 of 14 claims checked, ranked by impact: 5 supported, 2 contradicted, 1 plan, 1 needs your check". Four groups of claim cards, one per status. Contradicted cards show the original claim struck through and the contradicting quote beside it. "Needs your check" cards show a "Search manually" link button and a "Mark as checked" checkbox. An Evidence drawer opens on the right when a card is clicked: full source quote, link, published date or "date unknown", and the list of rules that passed.

**Frame 4: Rewritten briefing.** The final briefing as clean paragraphs with small footnote numbers, a sources list underneath, and a toggle between "Verified briefing" and "What changed" (a draft-versus-verified diff with removed text struck through and new text highlighted). Buttons: "Copy as Markdown", "Download receipt pack". A note: "Every number in this briefing comes from a cited quote."

**Frame 5: Error and empty states.** "Search failed for 2 claims, shown as Needs your check, not guessed", a Cached badge with "Showing a saved run", and an empty first-run state.

Also add a small **Attack mode** box on the Result frame: "Type any claim to check it" with one input and a Check button.

Tone of all microcopy: plain words, honest, no hype. Never say "AI-powered".

---

## Refinements (send one at a time)

1. "Check the colour contrast of every status badge against WCAG AA and fix any that fail."
2. "Turn the claim card into a component with variants for the four statuses, with auto-layout."
3. "Make the Trace panel more scannable: bold the decision at the end of each line."
4. "Reduce visual noise: fewer borders, more whitespace between the two columns."
5. "Add a compact mobile version of the Result frame."
