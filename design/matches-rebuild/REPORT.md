# Matches Tab Rebuild — Report

## ⚠️ Source of truth

**No zip file arrived in this session.** I searched every upload location on this machine
(home directory, `~/uploads/`, the app's upload folders, scratchpad, `/tmp`) — no archive newer
than June 19 exists, and that one contains only old project scripts. The only file that matches
your description ("raw HTML source for the page") is **`JobBot.html`** (repo root) — the
624 KB bundled Claude-Design mockup that is already on record as the Matches source of truth,
and which the live app's Matches board was built from on 2026-07-04.

**This rebuild was made from `JobBot.html`.** If your zip contains something different, re-send
it (if you dragged it into the chat, it may not have transferred to this machine) and I'll redo
the comparison against the real payload.

`JobBot.html` is not a normal HTML page — it's a self-extracting bundle: a manifest of
gzip+base64 resources plus a JSON-encoded page template, rendered at runtime by a bundled JS
framework. I decompressed the bundle programmatically and rebuilt the Matches screen from the
decoded template + logic. The decoded originals are preserved in `reference/original-extracted/`.

## Deliverables

| File | Purpose |
|---|---|
| `index.html` | Static shell: sidebar, header, tab bar, panel container |
| `styles.css` | All styling, converted from ~19 KB of inline styles to clean classes + theme tokens |
| `script.js` | Vanilla-JS port of the mockup's state logic (no framework needed) |
| `assets/fonts/` | 10 woff2 files extracted from the bundle (Inter + Space Grotesk) |
| `reference/original-extracted/` | The decoded original template, styles and logic, for future diffing |

Open `index.html` in any browser — no server needed.

## Asset inventory

**Found in the bundle (11 resources — all decoded):**

| Asset | Status |
|---|---|
| Inter font, 7 subset files (latin, latin-ext, greek, greek-ext, cyrillic, cyrillic-ext, vietnamese) | ✅ **Used** — copied to `assets/fonts/inter-*.woff2`, `@font-face` paths rewritten from bundle GUIDs |
| Space Grotesk font, 3 subset files (latin, latin-ext, vietnamese) | ✅ **Used** — copied to `assets/fonts/space-grotesk-*.woff2` |
| Bundled x-dc runtime JS (58 KB) | ❌ **Not used** — it's the mockup framework, replaced by `script.js` |

**There are zero image files in the bundle.** Nothing was skipped:

- **Company logos** are loaded at runtime from `https://logo.clearbit.com/<domain>`
  (stripe.com, airbnb.com, notion.so, figma.com, datadoghq.com, plaid.com). These are
  **external and network-dependent — they were never in the source**. The rebuild keeps the
  same URLs and faithfully reimplements the original's fallback: if a logo fails to load,
  a colored mark (company gradient in light theme, solid tint in dark) with a white notch
  appears instead, so the page looks intentional even fully offline.
- **User avatar** — the original only shows an image after the user uploads one; default is
  the initial "J" on an orange disc. Reproduced as-is.
- **Every icon** in the Matches screen is a text glyph (⌂ ◳ ▤ ⚙ ☰ ★ ☆ × ↻ ⏰ 💰 📮 🗂️ ✨ ⬆) or
  the inline JobBot diamond SVG. All reproduced inline.

**Paths fixed:** the 10 font URLs referenced opaque bundle GUIDs
(e.g. `url("0e60ce12-38f7-…")`) — rewritten to `assets/fonts/<family>-<subset>.woff2`.
The original's 40 per-weight `@font-face` duplicates were collapsed to 10 weight-range
(`font-weight: 400 700`) declarations pointing at the same files.

## Functionality reimplemented (working, not just visual)

The original renders through a proprietary reactive template runtime. `script.js` reimplements
the same behavior in plain JavaScript with the same seed data, rules, copy and timings:

- **4 sub-tabs** — For you / ★ Saved / Applied / Refused, with live counts.
- **Ranking** — starred jobs +2000, applied +1000, then fit score; featured card = top ranked;
  queue ranks zero-padded from 02.
- **Fit pills** — score ≥85 "Excellent fit", ≥78 "Strong fit" (green), else "Good fit" (blue).
- **Save / dismiss / restore** — star toggling re-sorts the queue; × prepends to Refused
  (max 10 shown) with an undo path via ↩ Restore; toasts match the original copy.
- **Refresh scan simulation** — "Scanning 6 sources…" with per-source progressive rows,
  animated progress bar, 540 ms per source, success toast at the end — original timings.
- **Applied pipeline** — stage dropdown (Applied/Screening/Interview/Offer/Rejected), colored
  stage dot, per-stage reminder chip, filter chips with live counts, "💰 Offer insights →"
  appears only at Offer stage.
- **Empty states** for Saved / Applied / Refused, plus the first-run "Hi, I'm JobBot 👋"
  resume-upload state with working drag-&-drop and file-picker (reachable at `#firstrun`).
- **Flash toasts** — success/info variants, auto-dismiss after 3.6 s.
- **Time-of-day greeting** — Morning/Afternoon/Evening, Jordan 👋.
- **Logo fallback** on image error, per above.
- **Responsive** — below 760 px the sidebar collapses to a horizontal scroll bar (original rule).

## Deliberate deviations (all disclosed)

1. **Clean structure instead of inline styles** — the original template is one wall of inline
   styles; the rebuild uses semantic classes and CSS custom properties (that's the "rebuild
   properly" ask). Rendered values are the same.
2. **Dark theme is the default**, exactly like the mockup's initial state (`theme:'dark'`).
   The original's light palette is fully implemented too: set `<html data-theme="light">`.
   The theme switch itself lives on the out-of-scope Options screen, so no toggle UI was added.
3. **Out-of-scope destinations are stubbed** — clicking a job row ("open job detail"),
   ✨ Tailor & apply, or the Home/Resumes/Preferences/Options nav items shows an info toast
   instead of navigating. Only the Matches tab was rebuilt, per your scope.
4. **Hash deep-links added** (`#saved` `#applied` `#refused` `#firstrun` `#scan`) so every
   state can be opened/tested directly. Not in the original; harmless.
5. **Empty-queue edge case** — if you dismiss all six jobs, the original mockup would show an
   already-dismissed job as the featured pick (a mockup bug); the rebuild shows an honest
   empty-state card instead.
6. **First-run upload-zone title stays navy in dark theme** — the original's dark remap turns
   that title near-white while the zone behind it keeps its un-remapped light gradient,
   producing white-on-white illegible text (a mockup contrast bug). The rebuild keeps readable
   navy on the light zone in both themes.

## Verification

Checked in headless Chromium at 1440 px and 700 px: all four tabs, both For-You alternate
states (first-run upload, scanning), empty states, star/dismiss/restore/stage/filter flows,
and console-error-free load.

An 18-agent adversarial review then compared the rebuild element-by-element against the
decoded original (5 reviewers across For-You / lists / shell / behavior / functional
dimensions, each finding independently re-verified against both sources). It confirmed
11 findings — 1 major, all fixed:

- scan progress now patches the DOM in place, so the bar slides with its `.45s` transition,
  completed rows don't replay their entrance animation, and spinners rotate continuously
- the tab entrance animation no longer replays on every star/dismiss/filter click — only on
  real tab switches (matching the original's React mount behavior)
- featured card's logo-fallback mark keeps the company gradient in dark (only list rows tint)
- hovering the active Matches nav item dims it, as the original's `!important` hover rule does
- removed two mobile rules the original doesn't have; sidebar user-row gap 11px → 10px
- Saved-tab stars no longer inherit the queue-only hover glow
- stage dropdown light-theme text `#0f1730` → original `#1f2a44`
- greeting recomputes every render, so it rolls over correctly at noon / 6 pm
- deviation 6 above was flagged as undisclosed and is now documented
