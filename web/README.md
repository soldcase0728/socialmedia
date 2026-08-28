# Homepage hero — Orchard Lake St. Mary’s

`hero.html` is the locked first screen. Self-contained: markup + inline CSS,
no build step, no external requests. Open it directly in a browser.

## The stack is locked

Nothing may jump ahead of this order:

1. Eyebrow pill
2. H1 — loudest type on the page
3. Triad — part of the title stack, one line, slightly letterspaced
4. Location line — quiet, under the triad, never above the H1
5. Deck — three short lines
6. Two bullets — two only
7. Quiet line
8. CTAs
9. Mass-day micro

**Never cut:** the triad, the three deck lines, the two bullets.

## Fitting above the fold

The cut order is enforced in CSS with viewport-height queries at the bottom of
the stylesheet, so it degrades in the mandated order without hand-editing:

| Desktop viewport height | What drops |
| ----------------------- | ---------- |
| ≤ 744px | optional “safe / hard” deck line |
| ≤ 704px | + quiet co-divisional line |
| ≤ 674px | + location line |

These are measured, not guessed — each is the height at which that
configuration stops clearing the fold by 16px at 1440 wide. Read upward, the
location line is the first thing restored as the screen grows, then the quiet
line, then the optional one. The full stack survives down to 745px.

Nothing is cut below 900px wide — mobile scrolls.

## Two things to swap in from the live site

1. **`--font-display`** (top of the stylesheet) — point it at the display serif
   already setting “The St. Mary’s Standard.” It is a one-line change.
2. **The `<aside class="card">` block** — replace it wholesale with the live
   lead form. Its fields and its “real member of admissions replies” line are
   not to be changed; the version here is a stand-in so the column composes.

The maroon and cream tokens (`--maroon`, `--cream`, …) are close but should be
retuned to the live brand values.

## Typographic rule: “St. Mary’s”

Period + one space + Mary’s, everywhere it appears. The space is a plain
U+0020 — there are no `&nbsp;` characters in the file.

- **H1** sits tight and even at `-.025em`, never letterspaced like the triad.
  If “St.” ever reads stranded from “Mary’s”, tighten the tracking; do not add
  space. `The St. Mary’s / Standard.` is the correct break.
- **`.keep`** (`white-space:nowrap`) holds “St. Mary’s” on one line without
  touching the gap. It is needed: with an unprotected space the H1 splits
  “St.” from “Mary’s” at 360–430px. Nothing is bound together and nothing is
  stretched apart — only the line break is prevented.
- **Triad** keeps its open tracking, but `word-spacing` is set to the negative
  of `--triad-track` so the tracking cannot widen the spaces. Every gap stays
  one normal word space and the name reads as a name. Change the tracking via
  `--triad-track` only — the two values must move together.

Verified 320–1600px: “St.” never separates from “Mary’s”, and the
`St.`→`Mary’s` gap matches the `The`→`St.` gap to within 0.01px.

## Constraints held

- No photo behind the H1. If art is added later it belongs in a band **below**
  this hero — there is a marked comment where it goes.
- “Not anonymous. Not excused.” is emphasized by weight only, not color.
- No championships, no “80+ universities”, no “we learn their names”, no
  “you’re already home”, no fourth or fifth bullet.
- American spelling throughout.
