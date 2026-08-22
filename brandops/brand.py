"""Brand system for Orchard Lake St. Mary's.

Every downstream module -- triage, scoring, ideation, copywriting, measurement
-- resolves back to the definitions here. Change the brand in this file and the
whole engine changes with it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

SCHOOL = "Orchard Lake St. Mary's"
SHORT_NAME = "St. Mary's"

# The two central questions. They are related. They are not the same question,
# and one message will not answer both.
PARENT_QUESTION = (
    "Why should a family entrust an important period of their child's formation "
    "to St. Mary's?"
)
STUDENT_QUESTION = (
    "Why would I want to spend the next four years of my life here?"
)

WHITE_SPACE = (
    "Known personally, challenged seriously, formed intentionally, grounded in "
    "Catholicism, surrounded by community, prepared for meaningful outcomes."
)

OPERATING_PRINCIPLE = (
    "The goal is not to make St. Mary's look like it has a great marketing "
    "department. The goal is to let people see enough authentic evidence that "
    "they reach the conclusion themselves: something different is happening at "
    "St. Mary's."
)


class Pillar(str, Enum):
    """The six interconnected pillars of the brand position."""

    KNOWN = "known_and_safe"
    CHALLENGED = "challenged_to_grow"
    FORMATION = "formation_and_character"
    CATHOLIC = "catholic_identity"
    BELONGING = "belonging_and_community"
    OUTCOMES = "outcomes"

    @property
    def spec(self) -> "PillarSpec":
        return PILLARS[self]

    @property
    def label(self) -> str:
        return PILLARS[self].name


@dataclass(frozen=True)
class PillarSpec:
    """What a pillar promises, what proves it, and how much of the mix it owns."""

    pillar: Pillar
    name: str
    parent_promise: str
    student_promise: str
    proof: tuple[str, ...]
    """What has to be visible on camera. Not adjectives -- observable behavior."""
    evidence_test: str
    """The question an editor asks of an asset before claiming this pillar."""
    target_share: float
    """Share of published volume this pillar should hold over a rolling window."""
    keywords: tuple[str, ...]
    """Triage signals found in event names, descriptions and captions."""


PILLARS: dict[Pillar, PillarSpec] = {
    Pillar.KNOWN: PillarSpec(
        pillar=Pillar.KNOWN,
        name="Known & Safe",
        parent_promise="My child will be known here. He will not disappear.",
        student_promise="Adults here will learn my name and notice me.",
        proof=(
            "a teacher using a student's name",
            "an adult present in a hallway, not just a classroom",
            "a one-on-one conversation at a desk or a doorway",
            "a coach or moderator correcting and then encouraging",
            "an adult noticing a student who is struggling",
            "an adult telling a student he can do more than he thinks",
            "small-group instruction where every face is reachable",
        ),
        evidence_test="Can a parent see an adult paying attention to one specific student?",
        target_share=0.15,
        keywords=(
            "advisor", "advisory", "mentor", "office hours", "one-on-one",
            "check-in", "counselor", "conference", "hallway", "homeroom",
            "small group", "tutoring", "principal", "dean", "moderator",
        ),
    ),
    Pillar.CHALLENGED: PillarSpec(
        pillar=Pillar.CHALLENGED,
        name="Challenged to Grow",
        parent_promise="The work here is real and my child will be pushed.",
        student_promise="I will be better at something than I am now.",
        proof=(
            "a whiteboard with actual problems on it",
            "lab equipment in student hands",
            "a student defending an answer out loud",
            "a teacher asking a harder follow-up question",
            "AP, honors and dual-enrollment work in progress",
            "revision -- a draft with marks on it",
            "a competition scoreboard, bracket or judging table",
        ),
        evidence_test="Would a skeptical parent call this academically serious without a caption?",
        target_share=0.20,
        keywords=(
            "ap ", "advanced placement", "honors", "lab", "laboratory", "exam",
            "debate", "robotics", "calculus", "chemistry", "physics", "biology",
            "dual enrollment", "presentation", "competition", "research",
            "quiz bowl", "olympiad", "thesis", "seminar", "coding", "engineering",
        ),
    ),
    Pillar.FORMATION: PillarSpec(
        pillar=Pillar.FORMATION,
        name="Formation & Character",
        parent_promise="Not simply preparing them for what comes next. Forming them for it.",
        student_promise="I will leave here more capable than I arrived.",
        proof=(
            "a student carrying a responsibility no adult is holding for him",
            "an older student teaching a younger one",
            "someone doing the unglamorous part of the job",
            "a student who failed at something and went back",
            "service where the student is working, not posing",
            "a captain, section leader or prefect making a decision",
            "a student apologizing, correcting, or owning an outcome",
        ),
        evidence_test="Does this show a young person becoming capable, not merely busy?",
        target_share=0.15,
        keywords=(
            "leadership", "service", "discipline", "responsibility", "captain",
            "volunteer", "resilience", "work ethic", "accountability", "prefect",
            "mentorship", "ambassador", "council", "retreat", "eagle scout",
        ),
    ),
    Pillar.CATHOLIC: PillarSpec(
        pillar=Pillar.CATHOLIC,
        name="Catholic Identity",
        parent_promise="The faith is lived here, not decorated with.",
        student_promise="Faith here is normal, not awkward.",
        proof=(
            "students participating, not spectating",
            "a priest in an ordinary setting -- lunch, sideline, hallway",
            "prayer before something that matters",
            "confession and adoration lines with real students in them",
            "a classroom conversation where faith and intellect meet",
            "service that connects back to why",
            "Polish and Catholic heritage carried by students, not plaques",
        ),
        evidence_test="Is faith being lived in this frame, or merely present in it?",
        target_share=0.15,
        keywords=(
            "mass", "chapel", "prayer", "rosary", "confession", "adoration",
            "priest", "father ", "liturgy", "feast", "advent", "lent", "easter",
            "vocation", "blessing", "sacrament", "gospel", "saint", "polish",
            "heritage", "seminary", "ash wednesday",
        ),
    ),
    Pillar.BELONGING: PillarSpec(
        pillar=Pillar.BELONGING,
        name="Belonging & Community",
        parent_promise="My child will have people here.",
        student_promise="Those could be my friends.",
        proof=(
            "unposed laughter",
            "a lunch table with room at it",
            "the student section as a single organism",
            "a tradition being performed by students who know it by heart",
            "an ordinary hallway conversation",
            "a freshman being pulled into something by an upperclassman",
            "a teacher joking with students between classes",
        ),
        evidence_test="Could a 13-year-old picture himself inside this frame?",
        target_share=0.20,
        keywords=(
            "lunch", "hallway", "club", "student section", "spirit week",
            "homecoming", "tradition", "friends", "pep rally", "dance",
            "orientation", "freshman", "intramural", "lock-in", "trivia",
            "cafeteria", "bus ride",
        ),
    ),
    Pillar.OUTCOMES: PillarSpec(
        pillar=Pillar.OUTCOMES,
        name="Outcomes",
        parent_promise="This tuition buys a documented return.",
        student_promise="Where I go after here gets better because I came here.",
        proof=(
            "a named acceptance with a named student",
            "a scholarship figure a family can verify",
            "an alum back on campus with a job and a story",
            "an AP score distribution or dual-enrollment transcript",
            "a signing table",
            "a graduate doing the work he was formed for",
            "a before-and-after a student can describe in one sentence",
        ),
        evidence_test="Is there a specific, checkable fact here -- a name, a number, a place?",
        target_share=0.15,
        keywords=(
            "acceptance", "accepted", "scholarship", "signing", "committed",
            "graduation", "graduate", "alumni", "alum", "college", "national merit",
            "award", "internship", "career", "valedictorian", "decision day",
            "gpa", "act ", "sat ",
        ),
    ),
}

assert abs(sum(p.target_share for p in PILLARS.values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# Language discipline
# ---------------------------------------------------------------------------

# Phrases every private school already uses. They are not wrong; they are
# invisible. Each maps to what must replace it: a specific, observable fact.
BANNED_PHRASES: dict[str, str] = {
    "academic excellence": "name the course, the assignment, or the score",
    "excellence in education": "name what was actually difficult about the work",
    "preparing tomorrow's leaders": "name one graduate and what he leads now",
    "tomorrow's leaders": "name a graduate and what he does",
    "well-rounded": "name the two specific things this student does",
    "faith-based education": "show one thing the faith actually changed today",
    "state-of-the-art": "show the equipment being used and by whom",
    "second to none": "give the comparison a number",
    "nurturing environment": "show one adult noticing one student",
    "rich tradition": "name the tradition and who performs it",
    "student-centered": "show the student doing the deciding",
    "world-class": "cut it, or cite the ranking",
    "unlock their potential": "state what the student can do now that he could not before",
    "lifelong learners": "show what a student chose to learn without being told",
    "holistic": "list the parts instead of the label",
    "cutting-edge": "show the work, not the adjective",
    "family atmosphere": "show a specific relationship",
    "premier": "cut it",
}

# Hooks that trade institutional credibility for a click.
CLICKBAIT_PATTERNS: tuple[str, ...] = (
    r"you won'?t believe",
    r"\bshocking\b",
    r"nobody (?:is )?talking about",
    r"no one talks about",
    r"this changes everything",
    r"\bgone wrong\b",
    r"doctors hate",
    r"the truth about .* they",
    r"you'?ll never guess",
)


@dataclass(frozen=True)
class CopyFlag:
    """A piece of copy that must be fixed before it can be approved."""

    kind: str  # "banned_phrase" | "clickbait"
    found: str
    remedy: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.found!r} -> {self.remedy}"


def scan_copy(text: str) -> list[CopyFlag]:
    """Flag institutional filler and credibility-damaging hooks.

    Runs on every generated draft before it can enter the approval queue.
    """
    flags: list[CopyFlag] = []
    lowered = text.lower()
    for phrase, remedy in BANNED_PHRASES.items():
        if phrase in lowered:
            flags.append(CopyFlag("banned_phrase", phrase, remedy))
    for pattern in CLICKBAIT_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            flags.append(
                CopyFlag(
                    "clickbait",
                    match.group(0),
                    "rewrite without overclaiming -- credibility is the asset",
                )
            )
    return flags


def classify_pillars(text: str) -> list[tuple[Pillar, int]]:
    """Rank pillars by keyword evidence in free text, strongest first."""
    lowered = f" {text.lower()} "
    hits: list[tuple[Pillar, int]] = []
    for pillar, spec in PILLARS.items():
        count = sum(1 for kw in spec.keywords if kw in lowered)
        if count:
            hits.append((pillar, count))
    hits.sort(key=lambda item: (-item[1], item[0].value))
    return hits


def proof_prompt(pillar: Pillar) -> str:
    """The 'prove it' instruction handed to whoever is holding the camera."""
    spec = PILLARS[pillar]
    return (
        f"{spec.name}: {spec.evidence_test} Show one of -- "
        + "; ".join(spec.proof[:4])
        + "."
    )
