# Audiences

Defined in `brandops/audiences.py`. "Our social media audience" is not an
audience. Six segments, each being asked to believe a different thing on a
different timeline.

## Prospective parents (30% of volume)

**Objective:** answer the trust question before the tuition question.

They believe it when a specific adult does a specific thing for a specific
student; when the academic work on screen is visibly hard; when an outcome
carries a name, a number or a destination; when another parent says it instead
of the school; and when the footage looks like a Tuesday rather than a shoot.

Platforms: Facebook, Instagram feed and reels, YouTube, LinkedIn.
CTA: direct and low-friction -- visit, tour, inquire. One per piece.

## Sixth and seventh graders (15%)

**Objective:** familiarity and aspiration, long before an application exists.

They should see St. Mary's repeatedly and start imagining themselves here.
Emphasize traditions, the student section, clubs, competition, campus,
equipment, memorable moments.

Platforms: TikTok, Reels, YouTube Shorts, Stories.
**CTA: none.** Asking a sixth grader to apply breaks the strategy. The engine
enforces this -- `CTA_BY_AUDIENCE[Audience.GRADE_6_7]` is deliberately empty.

## Eighth graders (20%)

**Objective:** move from awareness to preference to a scheduled action.

They need to picture a specific day of freshman year, hear it from a current
freshman rather than an administrator, and be handed one easy next step.

Platforms: Reels, TikTok, Stories, Shorts.
CTA: soft, specific, social -- shadow a student, come to the game, visit.

## Current parents (20%)

**Objective:** reinforce the decision they already made, and make them repeat it
out loud. They are the most credible sales force the school has.

CTA: share-forward. "Know a family who is deciding? Send them this."

## Alumni (10%)

**Objective:** reinforce identity and legacy; convert affection into referral and
return. Show them something they remember still happening, and a teacher who
stayed.

## Donors (5%)

**Objective:** mission, impact, stewardship -- in that order. Trace a gift to a
specific student outcome. Report back before asking again.

## The parent/student split

`audience_read()` classifies any target set as parent, student, both or
community. Every daily brief states it explicitly, because content that tries to
be both without deciding usually reaches neither.
