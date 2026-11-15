# Figma evidence (Best-Designed AI Product)

Made 2026-11-14 22:40 to 2026-11-15 00:20 in **Figma Make** (not Figma Design). Written from what was observed in the browser; nothing here is claimed beyond that.

**File:** https://www.figma.com/make/dHUoqohzcu2cfgArIGTi3G/Receipts-Claim-Verification-App
Version history in the file shows each prompt below. Check "Share" before presenting so judges can open it (view only).

## What was done, in order (each is a Make prompt)

1. **22:40 First build.** The Receipts brief (condensed to Make's 2,000-character limit) produced an interactive React app with Briefing, Checking and Results views, shared claim cards, counts bar, evidence drawer and trace.
2. **22:42 Rewrite and States views, Attack mode.** Verified briefing with footnotes, a draft-versus-verified diff, Copy as Markdown and Download receipt pack, a failed-search banner, a Cached badge, and an empty first-run state.
3. **22:44 Contrast audit.** Make audited badges, chips, quote highlights and body text against WCAG AA and fixed failures. Its own table listed a cached indicator at 3.52:1 and an empty-state icon at 4.14:1 (not re-checked by us; acceptable only if they count as graphics at 3:1, not text).
4. **23:19 Consistency fix.** One shared data object so the counts, rewrite and sources agree across views (the first draft said "9 verified claims" on one view and 5 supported on another).
5. **00:14 Sync to the built app** (`static/` in this repo): two provider badges "Anthropic: live/offline" and "Linkup: live/offline", a mode badge "Live: N searches", "Cached: N saved searches" or "Mixed", the budget text "N of 60 calls used", the labelled sample banner, and a sample on Anthropic with three contradicted claims, to match a real run of the app.
6. **00:16 New "Report citations" view.** Paste a report with citations; each card shows the claim, "Cited as" (the reference as written), "Closest real record", Title/Authors/Year match chips with icons, the quote, an "abstract only" label, and the evidence drawer with C1 reference found, C2 metadata matches, C3 metadata conflicts.
7. **00:20 Honesty pass.** The drawer's rule labels were rewritten to say what the checker really does (R1 source is a returned result and the quote appears in it; R2 numbers and dates; R7 no rumour, plan or denial wording; R8 the source mentions the company and shares the claim's key words), and the caption "A reliable source says otherwise" became "A source says otherwise. We do not judge how authoritative it is." The citation sample no longer marks a claim Contradicted on a weak quote.

8. **00:50 Landing page.** A first "Home" tab (hero with a torn-edge receipt, a press-reports band marked "not our findings", a "follow one claim through" timeline with the four-state legend) and a Results view with "What the AI said" beside the claim cards. This mirrors the redesigned live site in `static/`; screenshots of the real site are in `../site/`.

8. **15 Nov, built app restyled to the Figma design** (`static/style.css`, `index.html`, `app.js`). The Figma file is private, so the design was read from the exported screenshots in this folder, not from Make's code. Changed: outlined status badges, a dark logo tile with the tagline, an "Evidence-first company research" eyebrow, result groups with a rule and a caption, cards with a "Claim N" label, a source title and freshness chip, and an evidence drawer with Claim / Full quote / Source / Why we decided this / Checker rules (R-id, tick, text). No data wiring changed. Checked with 88 unit tests and the headless-Edge test; screenshots in `docs/shots/before/` and `docs/shots/after-view/` (desktop 1440 and phone 390, made by `tests/shots.mjs`). Not copied from Figma: the tabbed app shell (Briefing / Checking / Results / Rewrite tabs); the built app is one scrolling page.

**Before and after:** `v1-first-pass/` holds the first-pass screenshots (Acme sample, single Live badge, "14 of 40 searches"). The current screenshots are the numbered files in this folder.

## Screenshots (current)

| File | Shows |
|---|---|
| `01-briefing-input-v2.png` | Briefing input with the provider status badges |
| `02-report-citations-result.png` | Report citations: paste area, sample warning, counts (4 supported, 0 contradicted, 4 need your check), first card |
| `03-report-citations-cards.png` | Citation card with Cited as, Closest real record, match chips, quote and the needs-your-check explanation |
| `04-results-contradicted-evidence-drawer.png` | Results: three contradicted claims with sources, evidence drawer with the checker rules |
| `05-states-offline-cached.png` | Linkup offline badge, Cached badge, failed-search banner, empty first run |
| `06-home-landing.png` | Home: hero, torn-edge receipt, start of the press-reports band |

## Known gaps (do not hide)

- **It is a Make app, not Figma Design frames.** There is no component library with variants, no auto-layout work, and no mobile Result layout. Make showed an "Open in canvas" button; it was **not** tried. Say "designed and iterated in Figma Make".
- **Sample data is invented** (sources, URLs, quotes are marked "Sample quote"). The citation sample uses real papers (Noy and Zhang 2023, Brynjolfsson, Li and Raymond) plus invented references; no real firm is named.
- **Citation card inconsistency:** Citation 2 shows a crossed Year chip while its note says the year is within tolerance. The checker spec allows a one-year difference, so the chip should not be crossed.
- **The built app does not yet have the Report citations view.** It is specified in `knowledge/receipts-citation-mode-spec.md` (workspace, not the repo). Until it exists, do not present the citation screens as working product; show them as design.
- The unrun refinements planned for this screen (component variants, Trace readability, noise, mobile) are still not done.
- **Design and build differ in small ways.** The Make Home has small all-caps labels above headings ("EVIDENCE-FIRST AI CHECKING", "WHY RECEIPTS MATTER"); the live site deliberately has none. The live site also has the progress steps, the paced claim-by-claim reveal and the plain-English reasons, which are not in the design. The build is the more developed of the two.
- The design's report-citations view is design only; the live site does not have it.
- Viewport used for all screenshots is 1440 px wide, desktop only.
- Figma's Make code editor and the team plan were used; no connectors were added.

## For the presentation (30 seconds)

Show the file link, `04-results-contradicted-evidence-drawer.png` and `03-report-citations-cards.png`. Say what changed between the first draft and now: the contrast audit, the consistency fix, syncing the badges and budget to the real app, rewriting the rule labels so they match the code, and removing "reliable". Only mention changes that happened, and say which screens are design only.
