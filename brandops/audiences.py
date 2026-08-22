"""Audience segments.

"Social media audience" is not an audience. A prospective parent and a
seventh grader are being asked to believe different things, on different
timelines, for different reasons. The engine never generates a piece of
content without naming which of these it is for.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .brand import Pillar


class Audience(str, Enum):
    PROSPECTIVE_PARENT = "prospective_parent"
    GRADE_6_7 = "grade_6_7"
    GRADE_8 = "grade_8"
    CURRENT_PARENT = "current_parent"
    ALUMNI = "alumni"
    DONOR = "donor"

    @property
    def spec(self) -> "AudienceSpec":
        return AUDIENCES[self]

    @property
    def label(self) -> str:
        return AUDIENCES[self].name


@dataclass(frozen=True)
class AudienceSpec:
    audience: Audience
    name: str
    objective: str
    """The psychological job this audience's content has to do."""
    funnel_stage: str
    believes_when: tuple[str, ...]
    """What actually moves this audience. Evidence, not assertions."""
    emphasize: tuple[str, ...]
    avoid: tuple[str, ...]
    platforms: tuple[str, ...]
    """Platform keys, in priority order. See brandops.platforms."""
    cta_policy: str
    target_share: float


AUDIENCES: dict[Audience, AudienceSpec] = {
    Audience.PROSPECTIVE_PARENT: AudienceSpec(
        audience=Audience.PROSPECTIVE_PARENT,
        name="Prospective Parents",
        objective=(
            "Answer the trust question before the tuition question: will adults "
            "here know my child, push him, and hand him back better?"
        ),
        funnel_stage="awareness -> inquiry -> visit -> application",
        believes_when=(
            "a specific adult is shown doing a specific thing for a student",
            "the academic work on screen is visibly hard",
            "an outcome carries a name, a number or a destination",
            "another parent says it instead of the school",
            "the footage looks like a Tuesday, not a photo shoot",
        ),
        emphasize=(
            "who will know my child", "how hard the work is", "formation and discipline",
            "Catholic life as lived practice", "the peer group", "what tuition returns",
        ),
        avoid=(
            "slogans without evidence", "statistics with no source",
            "athletics as the whole identity", "teen slang from adults",
        ),
        platforms=("facebook", "instagram_feed", "instagram_reel", "youtube", "linkedin"),
        cta_policy="Direct and low-friction: visit, tour, inquire. One CTA per piece.",
        target_share=0.30,
    ),
    Audience.GRADE_6_7: AudienceSpec(
        audience=Audience.GRADE_6_7,
        name="Sixth & Seventh Graders",
        objective=(
            "Familiarity and aspiration. They should see St. Mary's repeatedly and "
            "start imagining themselves here long before an application exists."
        ),
        funnel_stage="awareness",
        believes_when=(
            "the students on screen look like people they would want to sit with",
            "something looks genuinely fun or genuinely impressive",
            "the video does not feel like an advertisement",
        ),
        emphasize=(
            "traditions", "the student section", "clubs and competitions",
            "campus", "technology and equipment", "memorable moments", "school pride",
        ),
        avoid=("admissions deadlines", "tuition", "adult-voiced narration", "hard CTAs"),
        platforms=("tiktok", "instagram_reel", "youtube_shorts", "instagram_story"),
        cta_policy="No CTA. Familiarity is the goal; asking too early breaks it.",
        target_share=0.15,
    ),
    Audience.GRADE_8: AudienceSpec(
        audience=Audience.GRADE_8,
        name="Eighth Graders",
        objective="Move from awareness to preference, then to a scheduled action.",
        funnel_stage="preference -> visit/shadow -> application",
        believes_when=(
            "they can picture a specific day of freshman year",
            "a current freshman -- not an administrator -- describes it",
            "there is an easy, concrete next step",
        ),
        emphasize=(
            "what freshman year actually feels like", "belonging", "shadow days",
            "friendships across grades", "opportunities they can start day one",
            "traditions they would be part of",
        ),
        avoid=("abstractions about the future", "pressure", "over-produced polish"),
        platforms=("instagram_reel", "tiktok", "instagram_story", "youtube_shorts"),
        cta_policy="Soft, specific and social: shadow a student, come to the game, visit.",
        target_share=0.20,
    ),
    Audience.CURRENT_PARENT: AudienceSpec(
        audience=Audience.CURRENT_PARENT,
        name="Current Parents",
        objective="Reinforce the decision they already made, and make them repeat it out loud.",
        funnel_stage="retention -> advocacy",
        believes_when=(
            "they see their own child's world reflected accurately",
            "the school shows the ordinary day, not only the highlight",
            "faculty are visibly invested",
        ),
        emphasize=(
            "classroom life", "faculty", "student growth", "community",
            "gratitude and recognition", "what happened this week",
        ),
        avoid=("recruitment pitches aimed past them", "fundraising in every post"),
        platforms=("facebook", "instagram_feed", "instagram_story"),
        cta_policy="Share-forward: tag, share, tell a family you know.",
        target_share=0.20,
    ),
    Audience.ALUMNI: AudienceSpec(
        audience=Audience.ALUMNI,
        name="Alumni",
        objective="Reinforce identity and legacy; convert affection into referral and return.",
        funnel_stage="affinity",
        believes_when=(
            "something they remember is still happening",
            "a classmate or a former teacher appears",
            "the school treats its history as living",
        ),
        emphasize=("traditions", "campus and history", "Polish heritage", "faculty who stayed",
                   "alumni outcomes", "then-and-now"),
        avoid=("nostalgia with no present tense", "asking before reconnecting"),
        platforms=("facebook", "linkedin", "instagram_feed", "youtube"),
        cta_policy="Invite back: homecoming, Mass, a game, a class note.",
        target_share=0.10,
    ),
    Audience.DONOR: AudienceSpec(
        audience=Audience.DONOR,
        name="Donors",
        objective="Demonstrate mission, impact and stewardship -- in that order.",
        funnel_stage="stewardship",
        believes_when=(
            "a gift is traced to a specific student outcome",
            "the school reports back without being asked",
            "the mission is visibly Catholic and visibly working",
        ),
        emphasize=("impact of a specific gift", "scholarship recipients (with consent)",
                   "facilities in use", "mission", "accountability"),
        avoid=("vague need", "urgency theater", "impact claims without numbers"),
        platforms=("linkedin", "facebook", "youtube"),
        cta_policy="Stewardship first. Ask only when the report has already been delivered.",
        target_share=0.05,
    ),
}

assert abs(sum(a.target_share for a in AUDIENCES.values()) - 1.0) < 1e-9

STUDENT_AUDIENCES = (Audience.GRADE_6_7, Audience.GRADE_8)
PARENT_AUDIENCES = (Audience.PROSPECTIVE_PARENT, Audience.CURRENT_PARENT)


def audience_read(audiences: tuple[Audience, ...] | list[Audience]) -> str:
    """Summarize a target set as 'parent', 'student', or 'both'."""
    has_parent = any(a in PARENT_AUDIENCES for a in audiences)
    has_student = any(a in STUDENT_AUDIENCES for a in audiences)
    if has_parent and has_student:
        return "both"
    if has_parent:
        return "parent"
    if has_student:
        return "student"
    return "community"


# Which audiences a pillar naturally serves, strongest first. Every planner in
# the package resolves audience from pillar through this one map.
PILLAR_AUDIENCES: dict[Pillar, tuple[Audience, ...]] = {
    Pillar.KNOWN: (Audience.PROSPECTIVE_PARENT, Audience.CURRENT_PARENT),
    Pillar.CHALLENGED: (Audience.PROSPECTIVE_PARENT, Audience.GRADE_8, Audience.CURRENT_PARENT),
    Pillar.FORMATION: (Audience.PROSPECTIVE_PARENT, Audience.CURRENT_PARENT, Audience.DONOR),
    Pillar.CATHOLIC: (Audience.PROSPECTIVE_PARENT, Audience.CURRENT_PARENT, Audience.ALUMNI),
    Pillar.BELONGING: (Audience.GRADE_8, Audience.GRADE_6_7, Audience.CURRENT_PARENT),
    Pillar.OUTCOMES: (Audience.PROSPECTIVE_PARENT, Audience.ALUMNI, Audience.DONOR),
}
