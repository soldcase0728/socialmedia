"""Opening hooks for short-form video.

The first one to three seconds decide whether anything else gets seen. Every
short-form cut leaves this module with at least three options, and none of
them are allowed to overclaim -- credibility is the asset being built.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .audiences import Audience
from .brand import Pillar, scan_copy


class HookStructure(str, Enum):
    UNEXPECTED_STATEMENT = "unexpected_statement"
    PARENT_CONCERN = "parent_concern"
    STUDENT_QUESTION = "student_question"
    TRANSFORMATION = "transformation"
    CURIOSITY = "curiosity"
    CONTRADICTION = "contradiction"
    SURPRISING_STAT = "surprising_stat"
    BEHIND_THE_SCENES = "behind_the_scenes"
    EMOTIONAL_MOMENT = "emotional_moment"
    WHAT_IT_LOOKS_LIKE = "what_it_looks_like"


@dataclass(frozen=True)
class HookTemplate:
    structure: HookStructure
    pattern: str
    requires: tuple[str, ...]
    """Fields that must be supplied or the structure is skipped."""
    note: str


TEMPLATES: tuple[HookTemplate, ...] = (
    HookTemplate(
        HookStructure.WHAT_IT_LOOKS_LIKE,
        "What {topic} actually looks like here.",
        (),
        "Safest structure. Promises exactly what the footage delivers.",
    ),
    HookTemplate(
        HookStructure.BEHIND_THE_SCENES,
        "The part of {topic} nobody films.",
        (),
        "Access framing. Only use it when the footage really is the unseen part.",
    ),
    HookTemplate(
        HookStructure.PARENT_CONCERN,
        "Every parent asks the same thing: {concern}",
        ("concern",),
        "Names the objection out loud, then answers it with the footage.",
    ),
    HookTemplate(
        HookStructure.STUDENT_QUESTION,
        "Ask a freshman what {topic} is like. This is what he says.",
        (),
        "Hands the answer to a student. Strongest with 8th graders.",
    ),
    HookTemplate(
        HookStructure.TRANSFORMATION,
        "In September, {subject} could not {before}.",
        ("subject", "before"),
        "Requires a real before-state. Never invent one.",
    ),
    HookTemplate(
        HookStructure.EMOTIONAL_MOMENT,
        "Watch {subject} at the four-second mark.",
        ("subject",),
        "Only when the moment is genuinely in the frame.",
    ),
    HookTemplate(
        HookStructure.CURIOSITY,
        "There is a reason {topic} takes {detail}.",
        ("detail",),
        "Curiosity gap that the video then closes. Close it, or cut the hook.",
    ),
    HookTemplate(
        HookStructure.CONTRADICTION,
        "{topic} is supposed to be {expectation}.",
        ("expectation",),
        "Sets an expectation the footage immediately breaks.",
    ),
    HookTemplate(
        HookStructure.SURPRISING_STAT,
        "{stat}",
        ("stat",),
        "Must be a verified, sourced number. Statistics require human approval.",
    ),
    HookTemplate(
        HookStructure.UNEXPECTED_STATEMENT,
        "{claim}",
        ("claim",),
        "A true sentence nobody expects a school to say.",
    ),
)

_BY_STRUCTURE = {t.structure: t for t in TEMPLATES}

# Which structures carry which pillar best.
PILLAR_AFFINITY: dict[Pillar, tuple[HookStructure, ...]] = {
    Pillar.KNOWN: (HookStructure.PARENT_CONCERN, HookStructure.WHAT_IT_LOOKS_LIKE,
                   HookStructure.EMOTIONAL_MOMENT, HookStructure.BEHIND_THE_SCENES),
    Pillar.CHALLENGED: (HookStructure.CONTRADICTION, HookStructure.WHAT_IT_LOOKS_LIKE,
                        HookStructure.CURIOSITY, HookStructure.TRANSFORMATION),
    Pillar.FORMATION: (HookStructure.TRANSFORMATION, HookStructure.BEHIND_THE_SCENES,
                       HookStructure.UNEXPECTED_STATEMENT, HookStructure.WHAT_IT_LOOKS_LIKE),
    Pillar.CATHOLIC: (HookStructure.WHAT_IT_LOOKS_LIKE, HookStructure.BEHIND_THE_SCENES,
                      HookStructure.STUDENT_QUESTION, HookStructure.EMOTIONAL_MOMENT),
    Pillar.BELONGING: (HookStructure.STUDENT_QUESTION, HookStructure.WHAT_IT_LOOKS_LIKE,
                       HookStructure.EMOTIONAL_MOMENT, HookStructure.BEHIND_THE_SCENES),
    Pillar.OUTCOMES: (HookStructure.SURPRISING_STAT, HookStructure.TRANSFORMATION,
                      HookStructure.UNEXPECTED_STATEMENT, HookStructure.PARENT_CONCERN),
}

AUDIENCE_AFFINITY: dict[Audience, tuple[HookStructure, ...]] = {
    Audience.PROSPECTIVE_PARENT: (HookStructure.PARENT_CONCERN, HookStructure.SURPRISING_STAT,
                                  HookStructure.WHAT_IT_LOOKS_LIKE),
    Audience.GRADE_6_7: (HookStructure.BEHIND_THE_SCENES, HookStructure.STUDENT_QUESTION,
                         HookStructure.EMOTIONAL_MOMENT),
    Audience.GRADE_8: (HookStructure.STUDENT_QUESTION, HookStructure.WHAT_IT_LOOKS_LIKE,
                       HookStructure.TRANSFORMATION),
    Audience.CURRENT_PARENT: (HookStructure.EMOTIONAL_MOMENT, HookStructure.WHAT_IT_LOOKS_LIKE,
                              HookStructure.BEHIND_THE_SCENES),
    Audience.ALUMNI: (HookStructure.WHAT_IT_LOOKS_LIKE, HookStructure.CONTRADICTION,
                      HookStructure.EMOTIONAL_MOMENT),
    Audience.DONOR: (HookStructure.SURPRISING_STAT, HookStructure.TRANSFORMATION,
                     HookStructure.UNEXPECTED_STATEMENT),
}


@dataclass(frozen=True)
class Hook:
    text: str
    structure: HookStructure
    placement: str
    rationale: str
    on_screen: bool = True
    requires_verification: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "structure": self.structure.value,
            "placement": self.placement,
            "rationale": self.rationale,
            "on_screen": self.on_screen,
            "requires_verification": self.requires_verification,
        }


def _fill(pattern: str, values: dict[str, str]) -> str | None:
    try:
        text = pattern.format(**values)
    except KeyError:
        return None
    if re.search(r"\{[a-z_]+\}", text):
        return None
    return text[0].upper() + text[1:] if text else text


def generate_hooks(
    topic: str,
    *,
    pillar: Pillar,
    audience: Audience,
    values: dict[str, str] | None = None,
    count: int = 3,
) -> list[Hook]:
    """Return at least `count` opening options, best-fit structures first.

    `values` supplies the facts a structure needs -- a subject's name, a
    verified statistic, the objection being answered. Structures whose facts
    are missing are skipped rather than filled with invention.
    """
    supplied = {"topic": topic.strip().rstrip(".")}
    supplied.update({k: v for k, v in (values or {}).items() if v})

    ordered: list[HookStructure] = []
    for structure in AUDIENCE_AFFINITY[audience] + PILLAR_AFFINITY[pillar]:
        if structure not in ordered:
            ordered.append(structure)
    for template in TEMPLATES:
        if template.structure not in ordered:
            ordered.append(template.structure)

    hooks: list[Hook] = []
    for structure in ordered:
        template = _BY_STRUCTURE[structure]
        if any(field not in supplied for field in template.requires):
            continue
        text = _fill(template.pattern, supplied)
        if text is None or scan_copy(text):
            continue
        hooks.append(
            Hook(
                text=text,
                structure=structure,
                placement="0.0-2.5s, on-screen text over the first frame",
                rationale=template.note,
                requires_verification=structure is HookStructure.SURPRISING_STAT,
            )
        )
        if len(hooks) >= max(count, 3):
            break
    return hooks


def missing_facts(pillar: Pillar, values: dict[str, str] | None = None) -> list[str]:
    """Facts that would unlock stronger hook structures for this pillar."""
    supplied = set((values or {}).keys())
    wanted: list[str] = []
    for structure in PILLAR_AFFINITY[pillar]:
        for field in _BY_STRUCTURE[structure].requires:
            if field not in supplied and field not in wanted:
                wanted.append(field)
    return wanted
