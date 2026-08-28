# CLAIMS — every public figure on the homepage

A state-title error in a standards hero is fatal. The page argues that this
school holds a bar. A single loose number destroys that argument faster than
any competitor can. So nothing numeric or checkable ships without four things:
**owner, source, date, status.**

**No claim ships at status UNVERIFIED or PLACEHOLDER.** Clearing this register
is a launch blocker, not a copy task.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| `VERIFIED` | Owner has seen the source document, and it is dated. Safe to publish. |
| `UNVERIFIED` | On the page, nobody has yet checked it against a source. **Blocks launch.** |
| `PLACEHOLDER` | Invented to compose the layout. **Must not ship.** |
| `GATED` | Not on the page. May only appear if the stated condition is met. |
| `BANNED` | Must never appear on this page. |

## Register

| # | Claim as published | Where | Owner | Source | Date | Status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 98% of the Class of 2025 placed at four-year universities | Hero bullet 1 | Admissions | *needed — senior exit survey or counselor placement report* | *needed* | `UNVERIFIED` |
| 2 | All-school Mass is part of the week | Hero bullet 2 | Campus Ministry | *needed — published school schedule* | *needed* | `UNVERIFIED` |
| 3 | Theology is required all four years | Hero bullet 2 | Academic Dean | *needed — course catalog / graduation requirements* | *needed* | `UNVERIFIED` |
| 4 | 2 — Divisions. One standard. | Stat band | Head of School | *needed — must confirm both divisions sit under one academic standard, not merely that two divisions exist* | *needed* | `UNVERIFIED` |
| 5 | Classroom and church before the scoreboard. | Hero quiet line | Head of School | Positioning statement, not a metric | — | `UNVERIFIED` |
| 6 | Catholic college preparatory | Hero location line | Head of School | *needed — accreditation body and current term* | *needed* | `UNVERIFIED` |
| 7 | Orchard Lake, Michigan | Hero location line | — | Self-evident | — | `VERIFIED` |
| 8 | Open House — Sunday, October 19, 1:00 p.m. | Utility bar | Admissions | **None. I invented this date to compose the bar.** | — | `PLACEHOLDER` |
| 9 | Shadow Days — October 7, October 21, November 4 | Utility bar | Admissions | **None. I invented these dates to compose the bar.** | — | `PLACEHOLDER` |
| 10 | Shadow days "fill first" | Utility bar | Admissions | *needed — prior-year fill data, or cut the phrase* | *needed* | `UNVERIFIED` |
| 11 | A real member of admissions replies. | Form card | Admissions | Service promise — must be operationally true, including in August | — | `UNVERIFIED` |
| 12 | Visit on a Mass day … see the school as it actually runs. | Hero micro | Admissions | Implies visitors may attend Mass days. Confirm that is actually offered. | — | `UNVERIFIED` |
| 13 | Retention / return rate | *not on page* | Head of School | — | — | `GATED` |
| 14 | State titles, championships, athletic records | *not on page* | — | — | — | `BANNED` |
| 15 | "80+ universities" | *not on page* | — | — | — | `BANNED` |

## Gates and standing rules

**13 — Retention.** Publish only if the figure is **clean, current, and 90% or
higher**, measured after the growth years. Below 90% it will be read as *the
Standard drives people out* — it then belongs in an internal confidence plan,
not on the site. Even when it clears, it goes in the **stat band only, never
the hero**; the hero is full. The markup slot is already in `hero.html`,
commented out.

**14 — Athletics.** No championships, state titles, or records anywhere on this
page. This is the single most likely source of a fatal factual error and the
market already misfiles the school as a football program. The page's job is to
say the opposite.

**4 — Read this one carefully.** "2 — Divisions. One standard." is the only
structural claim a competitor cannot copy, which is exactly why it must be
literally true. Verify the *standard*, not the *count*. Two divisions is
trivially checkable; one standard across both is the actual assertion.

**8, 9 — Dates.** These are the most dangerous items here, because a wrong date
is both instantly visible and instantly disqualifying. They are fabrications
that exist only so the utility bar composes. Replace before any deploy.

## Before launch

- [ ] Every row above reads `VERIFIED`, `GATED`, or `BANNED`. No `UNVERIFIED`, no `PLACEHOLDER`.
- [ ] Each `VERIFIED` row names a real source document and the date it was checked.
- [ ] Rows 8 and 9 carry real dates from the admissions calendar.
- [ ] Row 1's 98% states its denominator — percent *of what*, and who counted.
- [ ] Re-check dated figures each admissions cycle; "Class of 2025" ages.
