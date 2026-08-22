# Approval, Calendars and Distribution

## The rule

Automate preparation aggressively. Do not automate institutional publishing.

The machine does about ninety percent of the work -- triage, drafting, hooks,
copy, scheduling proposals. A human makes the final judgment. This is not a
workflow preference; the content involves minors, faith, discipline and claims
the school has to stand behind.

## One queue, four actions

```bash
python -m brandops queue build "AP Chemistry lab"   # draft cards from an event
python -m brandops queue list                       # what is waiting
python -m brandops queue approve <card> --by "Director of Marketing"
```

Each card shows the media, the proposed caption, the platform, the scheduled
date, the strategic purpose, the score, and why a human is looking at it.
Actions: **APPROVE / EDIT / REJECT / HOLD**. No multi-level bureaucracy.

## Blockers cannot be approved past

Four conditions make a card un-approvable. The queue refuses the approval rather
than warning about it:

- photo release not confirmed for a student in frame
- copy still contains an unset link or handle
- an unverified statistic or admissions claim
- the contributor marked the asset as not yet publishable

A named human clears a blocker, and the clearance is recorded with their name.
`can_publish()` is the single gate every publishing path calls; it requires an
APPROVE decision **and** a named approver. There is no bypass.

## Routing

| Content | Approver |
| --- | --- |
| Default | Director of Marketing |
| Catholic identity | Campus Ministry + Director of Marketing |
| Statistics, admissions claims | Admissions Director |
| Sensitive, discipline, privacy | Head of School |
| Donor and advancement | Advancement Director |

## Calendars: 70 planned / 30 open

```bash
python -m brandops plan week   # 7-day execution calendar
python -m brandops plan 30     # four themed weeks
python -m brandops plan 90     # three campaign windows tied to the funnel
```

The week plan assigns a pillar and an audience to every planned slot *before*
anyone shoots anything, and rotates pillars proportional to target share, with
current deficits placed first. Roughly 30% of slots are deliberately held open:
an excellent unplanned moment must always outrank a scheduled mediocre one.

Platform and pillar are aligned automatically -- LinkedIn will not be handed
student-life content, TikTok will not be handed donor outcomes.

The liturgical calendar is computed and correct (Easter by computus; Ash
Wednesday, Palm Sunday, Divine Mercy, Pentecost derived from it; plus Our Lady
of Częstochowa, St. John Paul II, the Immaculate Conception and Polish
Constitution Day). **The school and admissions dates are a template keyed off
Labor Day and are marked `verified=False` until someone checks them against the
real calendar** -- unverified dates are labeled as such in every brief.

## Distribution sequence

One story, staged over 72 hours, as a different cut each time:

| Day | Surface |
| --- | --- |
| 0 | Story (raw, same day) -> Reel (afternoon) -> TikTok (evening) |
| 1 | Facebook (morning, with context) -> Instagram feed (midday) |
| 2 | YouTube Short (titled for search) -> LinkedIn (if it is an outcome) |

The first item out sets the read on everything after it. Never post the
identical file to five surfaces.
