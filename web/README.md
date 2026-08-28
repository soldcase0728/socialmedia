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

## Constraints held

- No photo behind the H1. If art is added later it belongs in a band **below**
  this hero — there is a marked comment where it goes.
- “Not anonymous. Not excused.” is emphasized by weight only, not color.
- No championships, no “80+ universities”, no “we learn their names”, no
  “you’re already home”, no fourth or fifth bullet.
- American spelling throughout.
