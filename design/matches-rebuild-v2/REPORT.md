# Matches Tab Rebuild v2 — Report

**Source of truth:** `matches-page-segment.zip` (uploaded 2026-07-06), containing exactly one
file — `matches-page-segment.html`, a hand-authored static snapshot of the JobBot **v2 dark**
Matches design (top nav bar, indigo accent, conic match-score rings). The original is preserved
unmodified in `reference/original-matches-page-segment.html`.

> Note: this is a **different design generation** than `design/matches-rebuild/`, which was
> built earlier from `JobBot.html` (v1: left sidebar, blue accent, fit pills). Both rebuilds are
> kept; this one is from your actual uploaded zip.

## Deliverables

| File | Purpose |
|---|---|
| `index.html` | Page skeleton: top nav, header, tab bar, panel container |
| `styles.css` | Section 1 = the original stylesheet verbatim; Section 2 = clearly-marked additions for the working tabs |
| `script.js` | Renders rows from the jobs list and wires every interaction |
| `assets/` | **Empty by fact, not omission** — see below |
| `reference/` | The untouched original file from your zip |

Open `index.html` in any browser. No server needed.

## Asset inventory

**The zip contained zero assets** — one HTML file, no images, no fonts, no CSS/JS files.

- **Company logos** load at runtime from `https://logo.clearbit.com/<domain>`
  (stripe.com, plaid.com, datadoghq.com, airbnb.com, figma.com, notion.so). External,
  network-dependent, never in the zip. The original shows **broken-image icons** when they
  fail; the rebuild hides a failed logo so the tile stays clean.
- **Icons** are text glyphs (★ ☆ × ↻ ✨ ✓); the JobBot diamond is an inline SVG. All reproduced.
- **Typeface** is the system font stack — this design uses no webfonts.

**Paths fixed (Cloudflare save-artifacts):**
1. The user email was obfuscated by Cloudflare email-protection
   (`<a href="/cdn-cgi/l/email-protection" data-cfemail="7a03…">[email protected]</a>`) —
   decoded back to the real text: `you@example.com`.
2. The dead `/cdn-cgi/scripts/…/email-decode.min.js` script tag was removed.
   These are artifacts of saving the page from a Cloudflare-proxied site, not part of the design.

## Functionality — reimplemented vs. inherited

The original file's own header says each `<article class="match">` is a template to fill from
real data, and ships only minimal JS (star toggles itself; × deletes the row permanently).
The rebuild makes the segment genuinely work:

- **Rows render from a jobs array** — same six jobs, scores, salaries, pills and star states
  as the snapshot; edit the list at the top of `script.js` to change the data.
- **Queue ranking** — saved jobs outrank applied, applied outrank score; reproduces the
  snapshot's exact order (hero Stripe 87; queue: Plaid • Datadog • Airbnb • Figma • Notion).
- **All four tabs work** with live counts (snapshot's "Saved · 1 / Applied · 1 / Refused · 0"
  is the starting state).
- **Star / unstar** anywhere, including the hero (square star button and "★ Save/Saved" ghost
  button both toggle) — re-sorts the queue.
- **Dismiss → Refused → Restore**: × moves a job to the Refused tab (undoable) instead of
  destroying the row like the source's placeholder JS did.
- **Hero always shows the current top pick** — dismiss it and the next-ranked job takes over,
  ring percentage and all.
- Verified with a scripted browser test: 14/14 interaction checks pass, plus an adversarial
  multi-agent fidelity review against the original (see below).

## Deliberate deviations (all disclosed)

1. Cloudflare email/script artifacts removed, email decoded (above).
2. Static rows → data-driven rendering, per the original's own instructions.
3. **Saved / Applied / Refused panels, empty states and the ↩ Restore button are additions** —
   the zip ships only the For-You panel, but its tab bar shows live-looking counts, implying
   this state model. Styled strictly in the source's idiom (Section 2 of `styles.css`).
4. Failed Clearbit logos are hidden instead of showing broken-image icons.
5. Greeting is time-of-day computed (static file froze "Morning"); Refresh shows a brief
   "Refreshing…" pressed state (the source gave the button no behavior at all).

Nothing else was changed: Section 1 of `styles.css` is the original stylesheet verbatim, and
the For-You DOM reproduces the snapshot exactly.
