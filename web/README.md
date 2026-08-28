# Homepage hero — Orchard Lake St. Mary’s

`hero.html` is the locked first screen plus the stat band beneath it.
Self-contained: markup + inline CSS, no build step, no external requests.
Open it directly in a browser.

Every public figure on this page is governed by [CLAIMS.md](./CLAIMS.md).
**Nothing ships while that register still reads `UNVERIFIED` or `PLACEHOLDER`.**

## The layering

Purpose sits above the bar, and the bar is the loudest type on the page.

| Slot | Copy | Role |
| --- | --- | --- |
| Eyebrow pill | God. Family. St. Mary’s. | The purpose. The market already grants it. |
| **H1** | **The St. Mary’s Standard.** | **The bar. They do not yet believe it, so it shouts.** |
| Location | Catholic college preparatory · Orchard Lake, Michigan | Quiet. |
| Deck | three lines (+ one optional) | |
| Bullets | two, never more | |
| Quiet line | Classroom and church before the scoreboard. | |
| CTAs | Book a Shadow Day / Read the Standard | |
| Micro | Visit on a Mass day… | |
| Stat band | 2 — Divisions. One standard. | Proof. Below the fold. |

### Rule of one

“God. Family. St. Mary’s.” runs **once**, in the eyebrow. It must never also
appear as a display line under the H1 — that is the same phrase twice in two
inches, and it pushes the page toward a motto-sized headline. The `.hero__triad`
element has been removed for exactly this reason; do not reintroduce it.

“Two divisions, one standard” likewise runs **once**, as the stat band figure.
The old quiet line began “Co-divisional classes.” — that half was cut so the
claim is not made twice. What remains, “Classroom and church before the
scoreboard,” is a separate claim and carries its own weight.

## Fitting above the fold

Cut order is enforced in CSS with viewport-height queries, so it degrades in
the mandated order without hand-editing:

| Desktop viewport height | What drops |
| --- | --- |
| ≤ 704px | optional “safe / hard” deck line |
| ≤ 664px | + quiet line |
| ≤ 629px | + location line |

Measured, not guessed: each threshold is the height at which that configuration
stops clearing the fold by 16px at 1440 wide, measured on the hero copy itself.
Read upward, the location line is the first thing restored as the screen grows.
The full stack survives down to 705px. Nothing is cut below 900px wide — mobile
scrolls.

Re-measure after any copy change. The form card (579px) becomes the binding
constraint below ~675px, so these numbers are about the hero copy, not the row.

## Typographic rule: “St. Mary’s”

Period + one space + Mary’s, everywhere it appears. The space is a plain
U+0020 — there are no `&nbsp;` characters in the file.

- **H1** sits tight and even at `-.025em`, never letterspaced. If “St.” reads
  stranded from “Mary’s”, tighten the tracking; do not add space.
  `The St. Mary’s / Standard.` is the correct break.
- **`.keep`** (`white-space:nowrap`) holds “St. Mary’s” together without
  touching the gap. It is needed: with an unprotected space the H1 splits
  “St.” from “Mary’s” at 360–430px.
- **Eyebrow** and **stat label** are letterspaced, so each sets `word-spacing`
  to the negative of its tracking token (`--eyebrow-track`, `--stat-track`).
  Without that, the tracking widens every space and the name comes apart into
  S T . M A R Y ’ S. Change tracking via the token only — the pair must move
  together.

Verified 320–1600px: “St.” never separates from “Mary’s”, and the
`St.`→`Mary’s` gap matches the `The`→`St.` gap to within 0.01px.

## Two things to swap in from the live site

1. **`--font-display`** — point it at the display serif already setting
   “The St. Mary’s Standard.” One-line change.
2. **The `<aside class="card">` block** — replace wholesale with the live lead
   form. Its fields and its “real member of admissions replies” line are not to
   be changed; the version here is a stand-in so the column composes.

The maroon and cream tokens are close but should be retuned to brand values.

## Constraints held

- No photo behind the H1. Art added later belongs in a band **below** the stat
  band — there is a marked comment where it goes.
- “Not anonymous. Not excused.” is emphasized by weight only, not color.
- The stat numeral is capped well under the H1. Do not raise it; the bar stays
  the loudest type.
- No championships, no state titles, no “80+ universities”, no “we learn their
  names”, no “you’re already home”, no third bullet.
- Retention is **not** on the page. It is gated in CLAIMS.md — stat band only,
  never the hero, and only at ≥90%. The markup slot is present but commented out.
- American spelling throughout.
