# Triage and the Content Opportunity Score

The failure mode this exists to prevent: a folder with nine hundred forgotten
photographs in it.

## Every asset resolves

```
RAW -> REVIEWED -> CONTENT_OPPORTUNITY -> DRAFTED -> APPROVED -> SCHEDULED -> PUBLISHED -> MEASURED
                        |                                                                     |
                        +--> LIBRARY (evergreen)   +--> REJECTED (on purpose)  <---------------+
```

Transitions are enforced in `brandops/assets.py`; illegal jumps raise rather
than silently corrupt the pipeline. Every usable asset becomes one of three
things: a content opportunity, a library entry, or an intentional rejection.
`python -m brandops inbox` lists anything still unresolved.

## Automated triage

`python -m brandops triage` reads each asset and proposes, before a human has
looked at anything:

- primary and secondary pillar (keyword evidence, falling back to department)
- audiences, and whether the read is parent, student or both
- platforms (vertical video routes to short form; horizontal never reaches Reels)
- urgency: same-day, this week, or evergreen
- organic vs. paid candidacy
- a story angle and three opening hooks
- **what footage is still missing** -- the most valuable output on the list
- why a human must review it
- an opportunity score and a recommended next status

Paid candidacy requires confirmed consent, no sensitivity flag, and an
admissions value of at least 4 out of 5. The engine will not propose spending
money on footage it cannot stand behind.

## The score

Ten criteria, one to five each (`python -m brandops rubric`):

emotional strength · visual strength · authenticity · parent relevance ·
student relevance · pillar fit · differentiation · timeliness · admissions
value · shareability

| Total (of 50) | Verdict | Meaning |
| --- | --- | --- |
| 40+ | **LEAD** | build the day around it |
| 33-39 | **PUBLISH** | good enough to take a slot |
| 26-32 | **DEVELOP** | needs more footage or a better angle |
| 20-25 | **LIBRARY** | keep it, do not schedule it |
| below 20 | **REJECT** | decide against it now, on purpose |

Two criteria deserve the most honesty when a human overrides the automation:

- **Authenticity** starts at 4 and drops two points for anything posed. A group
  photo, a lineup, a check presentation and a ribbon cutting are not content;
  they are minutes of a meeting.
- **Differentiation** asks whether any other school could post this. If the
  answer is yes, it is filler no matter how well shot.

## An empty slot is not a reason to publish

`qualifies_for_slot()` gates on PUBLISH or better. A calendar with a hole in it
is a smaller problem than a feed full of mediocre posts, because the second one
teaches the market that our content is not worth stopping for.

When something scores below the bar, `score.fix_list()` says what would have to
change to lift it -- usually one more clip, one name, or one number.
