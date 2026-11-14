# Figma evidence (Best-Designed AI Product)

Made 2026-11-14, about 22:40-22:50, in **Figma Make** (not Figma Design). Written from what was observed in the browser; nothing here is claimed beyond that.

**File:** https://www.figma.com/make/dHUoqohzcu2cfgArIGTi3G/Receipts-Claim-Verification-App
(Owner: the user's Figma account. Open it logged in; share settings were not changed. Check "Share" before the presentation so judges can open it.)

## What was done, in order

1. Pasted the Receipts brief from `figma-make-prompt.md` into Figma Make. Make's prompt box allows 2,000 characters, so the brief was condensed to fit (design system, components, frames 1-3). Result: an interactive React app with Briefing, Checking and Results views.
2. Follow-up prompt: Rewrite view (verified briefing, "What changed" diff, Copy as Markdown, Download receipt pack), States view (failed-search banner, Cached badge, empty first-run state), Attack mode box on Results, and a header nav.
3. Refinement 1 (contrast): asked Make to audit every badge, chip, quote highlight and body text against WCAG AA and fix failures. Make reported it fixed low-contrast metadata, placeholders, trace arrows, separators and borders, and re-ran `pnpm build` successfully. Its own table (seen only in part) lists supported chip 6.47:1, contradicted chip 6.24:1, empty-state icon 4.14:1 and cached indicator 3.52:1. **Not independently re-checked**; the last two are below 4.5:1 and are only acceptable if they are graphical objects (3:1), not text. Verify before claiming AA.
4. Stopped there: the free Figma team ran out of daily AI credits ("Upgrade plan"). No payment was made. Refinements 2-5 in `figma-make-prompt.md` (variants/auto-layout, Trace scannability, less noise, mobile Result) were **not run**.

## Screenshots (this folder)

| File | Shows |
|---|---|
| `01-input.png` | Input: paste area, company field, example chips, sample link, Check it |
| `02-checking.png` | Running: claim chips on the left, receipt cards on the right, "Checking claim 4 of 9", "14 of 40 searches" |
| `03-results-evidence-drawer.png` | Results: counts bar, Attack mode, claim cards, evidence drawer with struck-through claim, full quote, rules passed |
| `04-rewrite-verified.png` | Rewritten briefing with footnotes and sources |
| `05-rewrite-what-changed.png` | Draft-versus-verified diff (removed struck through, new highlighted) |
| `06-states-error-empty.png` | Failed-search banner, Cached badge, Needs your check actions, empty first-run state |

## Known gaps in the design (fix in the build, do not hide)

- **Live badge is always "Live"**, including on the saved-run screen. In the real app it must show Live or Cached from real state (lessons: never show a false live signal).
- **Numbers are inconsistent between views** (Rewrite says "9 verified claims"; Results says 5 supported). Mock data. The built UI must show numbers from `results.json` / the run only.
- **Sample content is invented** (Acme, example.com style URLs). Label it "sample" in the demo; never present it as a real check.
- Make did not produce separate Figma Design frames, a component library with variants, or a mobile layout. Say "designed and iterated in Figma Make", not "a full Figma Design system".
- Small eyebrow labels above headings appear on every view (a pattern the UI playbook calls a default AI tell); remove most of them in the build.
- Viewport used for the screenshots is 1440 px wide, desktop only.

## For the presentation (30 seconds)

Show the file link, `03-results-evidence-drawer.png`, and `05-rewrite-what-changed.png`. Say what changed between the first draft and now: the contrast audit, and (once done) the badge/number fixes above. Only mention changes that actually happened.
