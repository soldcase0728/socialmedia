"""The Content Opportunity Score.

Ten criteria, one to five each. The score exists to answer one question that
calendars are bad at answering: is this actually worth publishing, or are we
about to fill a slot with something mediocre because the slot is empty?
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum
from typing import Iterable

MIN, MAX = 1, 5


class Verdict(str, Enum):
    LEAD = "LEAD"          # build the day around it
    PUBLISH = "PUBLISH"    # good enough to take a slot
    DEVELOP = "DEVELOP"    # needs more footage or a better angle
    LIBRARY = "LIBRARY"    # keep it, do not schedule it
    REJECT = "REJECT"      # decide against it now, on purpose


@dataclass(frozen=True)
class CriterionSpec:
    key: str
    question: str
    low: str
    high: str
    weight: float = 1.0


CRITERIA: tuple[CriterionSpec, ...] = (
    CriterionSpec(
        "emotional_strength",
        "Does anyone feel anything?",
        "informational, no human stake",
        "a parent's throat tightens",
    ),
    CriterionSpec(
        "visual_strength",
        "Does the frame hold up with the sound off?",
        "dim, cluttered, backs of heads",
        "one clear subject, real light, obvious action",
    ),
    CriterionSpec(
        "authenticity",
        "Does this look like a Tuesday or like a photo shoot?",
        "posed, arranged, everyone aware of the camera",
        "unstaged, caught, nobody performing",
    ),
    CriterionSpec(
        "parent_relevance",
        "Does this speak to the trust question?",
        "means nothing to a family deciding",
        "directly answers 'will my child be known and pushed'",
    ),
    CriterionSpec(
        "student_relevance",
        "Could a 13-year-old picture himself in it?",
        "adults talking about students",
        "students being students, and it looks good to be one",
    ),
    CriterionSpec(
        "pillar_fit",
        "Does it prove a pillar rather than assert one?",
        "generic school content",
        "unmistakable evidence for one specific pillar",
    ),
    CriterionSpec(
        "differentiation",
        "Could any other school post this?",
        "interchangeable with every private school in the county",
        "only St. Mary's could produce this frame",
    ),
    CriterionSpec(
        "timeliness",
        "Does it need to run now?",
        "evergreen, no clock on it",
        "perishable -- today or it is gone",
    ),
    CriterionSpec(
        "admissions_value",
        "Does it move someone toward a visit or an application?",
        "no path to an admissions behavior",
        "a family would act on this",
    ),
    CriterionSpec(
        "shareability",
        "Will a parent or student send it to someone?",
        "nobody forwards this",
        "a parent tags their kid; a student sends it to a friend",
    ),
)

CRITERION_KEYS = tuple(c.key for c in CRITERIA)
_SPEC_BY_KEY = {c.key: c for c in CRITERIA}

MAX_TOTAL = MAX * len(CRITERIA)

# Verdict floors, evaluated top down against the unweighted total.
THRESHOLDS: tuple[tuple[int, Verdict], ...] = (
    (40, Verdict.LEAD),
    (33, Verdict.PUBLISH),
    (26, Verdict.DEVELOP),
    (20, Verdict.LIBRARY),
)


class ScoreError(ValueError):
    pass


@dataclass(frozen=True)
class OpportunityScore:
    emotional_strength: int
    visual_strength: int
    authenticity: int
    parent_relevance: int
    student_relevance: int
    pillar_fit: int
    differentiation: int
    timeliness: int
    admissions_value: int
    shareability: int

    def __post_init__(self) -> None:
        for f in fields(self):
            value = getattr(self, f.name)
            if not isinstance(value, int) or not MIN <= value <= MAX:
                raise ScoreError(f"{f.name} must be an int in {MIN}..{MAX}, got {value!r}")

    @property
    def values(self) -> dict[str, int]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @property
    def total(self) -> int:
        return sum(self.values.values())

    def weighted_total(self, weights: dict[str, float] | None = None) -> float:
        weights = weights or {}
        return sum(
            value * weights.get(key, _SPEC_BY_KEY[key].weight)
            for key, value in self.values.items()
        )

    @property
    def verdict(self) -> Verdict:
        for floor, verdict in THRESHOLDS:
            if self.total >= floor:
                return verdict
        return Verdict.REJECT

    @property
    def strengths(self) -> list[str]:
        return [k for k, v in self.values.items() if v >= 4]

    @property
    def weaknesses(self) -> list[str]:
        return [k for k, v in self.values.items() if v <= 2]

    def explain(self) -> str:
        parts = [f"{self.total}/{MAX_TOTAL} -> {self.verdict.value}"]
        if self.strengths:
            parts.append("strong: " + ", ".join(self.strengths))
        if self.weaknesses:
            parts.append("weak: " + ", ".join(self.weaknesses))
        return " | ".join(parts)

    def fix_list(self) -> list[str]:
        """What would have to change for this to become publishable."""
        return [
            f"{key}: get from {getattr(self, key)} toward '{_SPEC_BY_KEY[key].high}'"
            for key in self.weaknesses
        ]

    def to_dict(self) -> dict[str, int]:
        return dict(self.values)

    @classmethod
    def from_dict(cls, data: dict[str, int]) -> "OpportunityScore":
        return cls(**{k: int(data[k]) for k in CRITERION_KEYS})


def qualifies_for_slot(score: OpportunityScore) -> bool:
    """A calendar slot is not a reason to publish. This is the gate."""
    return score.verdict in (Verdict.LEAD, Verdict.PUBLISH)


def rank(scored: Iterable[tuple[object, OpportunityScore]]) -> list[tuple[object, OpportunityScore]]:
    """Strongest opportunities first; ties broken by admissions value."""
    return sorted(
        scored,
        key=lambda pair: (-pair[1].total, -pair[1].admissions_value, -pair[1].differentiation),
    )


def rubric() -> str:
    """The one-page rubric a human reviewer scores against."""
    lines = ["Content Opportunity Score -- 1 to 5 on each criterion", ""]
    for spec in CRITERIA:
        lines.append(f"{spec.key}  ({spec.question})")
        lines.append(f"    1 = {spec.low}")
        lines.append(f"    5 = {spec.high}")
    lines.append("")
    lines.append(f"Total out of {MAX_TOTAL}:  40+ LEAD | 33+ PUBLISH | 26+ DEVELOP | 20+ LIBRARY | else REJECT")
    return "\n".join(lines)
