"""The daily capture machine.

Teachers, coaches and moderators are never asked "what should we post?" They
are handed a shot list: a specific, finishable set of instructions that takes
under ten minutes and requires no marketing knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

from .brand import Pillar

# What we ask for on an ordinary day, from anyone, anywhere in the building.
BASELINE_DAILY: tuple[str, ...] = (
    "5 vertical clips, 5-10 seconds each, of students actually working",
    "1 teacher-student interaction -- a question being answered at a desk",
    "1 wide shot of the room so a parent can see the whole environment",
    "3 student reaction shots (thinking, laughing, concentrating)",
    "1 student saying in one sentence what he is doing and why",
    "1 unscripted hallway or lunch moment",
)

CAPTURE_RULES: tuple[str, ...] = (
    "Hold the phone vertically unless someone tells you otherwise.",
    "Get closer than feels natural. Then get closer again.",
    "Do not ask anyone to look at the camera or to do it again.",
    "Ten seconds of one thing beats sixty seconds of everything.",
    "Steady beats smooth: brace your elbows, do not walk while filming.",
    "If a student is not cleared for photos, do not film him. Ask first.",
    "Upload before you leave the room. The QR code is on your door.",
)


@dataclass(frozen=True)
class CaptureRecipe:
    key: str
    name: str
    pillar: Pillar
    minutes: int
    shots: tuple[str, ...]
    who: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "pillar": self.pillar.value,
            "minutes": self.minutes,
            "shots": list(self.shots),
            "who": self.who,
            "note": self.note,
        }


RECIPES: dict[str, CaptureRecipe] = {
    r.key: r
    for r in (
        CaptureRecipe(
            "classroom", "Ordinary classroom", Pillar.CHALLENGED, 8,
            (
                "the board with the actual problem or question on it",
                "two students working the problem, from the side, close",
                "the teacher asking a follow-up question -- get the audio",
                "one student's face while he is thinking, not while he is answering",
                "one wide shot from the back corner",
            ),
            "the teacher in the room, or a student assistant",
            "Do not clear the desks. Clutter reads as real.",
        ),
        CaptureRecipe(
            "lab", "Laboratory or shop", Pillar.CHALLENGED, 10,
            (
                "hands and equipment, close enough to fill the frame",
                "the moment something changes color, moves or fails",
                "a student recording data by hand",
                "a student explaining the procedure in one sentence",
                "safety goggles on -- always check the frame before filming",
            ),
            "the lab instructor",
        ),
        CaptureRecipe(
            "mass", "Mass or chapel", Pillar.CATHOLIC, 8,
            (
                "students participating -- singing, kneeling, responding",
                "a wide shot showing how full the chapel is",
                "hands: a missal, a rosary, folded hands",
                "a priest with students afterward, in ordinary conversation",
                "one student in genuine attention, from a respectful distance",
            ),
            "campus ministry",
            "Never film during the consecration or during confession. Ever.",
        ),
        CaptureRecipe(
            "service", "Service or outreach", Pillar.FORMATION, 8,
            (
                "students working, sweating, carrying -- not posing with a box",
                "the person being served, only with their explicit permission",
                "a student's hands doing the unglamorous part",
                "one student saying why he signed up",
                "the ride home, tired",
            ),
            "the moderator on site",
        ),
        CaptureRecipe(
            "athletics_game", "Game night", Pillar.BELONGING, 12,
            (
                "the student section as one organism, from the field",
                "a bench reaction to something on the field",
                "a coach coaching -- teaching, not yelling",
                "parents in the stands",
                "the handshake line or the postgame prayer",
            ),
            "coach, manager or student photographer",
            "Athletics is fuel, not the identity. One game post per week is usually enough.",
        ),
        CaptureRecipe(
            "arts", "Rehearsal or performance", Pillar.BELONGING, 10,
            (
                "rehearsal, not just performance -- the repetition is the story",
                "an instrument or a brush in the hands, close",
                "the director giving one correction",
                "backstage before the curtain",
                "the moment after the last note",
            ),
            "the director",
        ),
        CaptureRecipe(
            "hallway", "Passing period and lunch", Pillar.BELONGING, 5,
            (
                "one unposed hallway conversation",
                "a lunch table with genuine laughter",
                "an upperclassman pulling a freshman into something",
                "a teacher joking with students between classes",
            ),
            "anyone with a phone and two free minutes",
        ),
        CaptureRecipe(
            "mentorship", "Adults knowing students", Pillar.KNOWN, 6,
            (
                "a one-on-one conversation at a desk or a doorway",
                "an adult using a student's name -- get the audio",
                "a teacher staying after to explain something again",
                "an advisor checking in on a student who looked off today",
            ),
            "the adult involved, or a colleague passing by",
            "This is the single most persuasive footage we can capture for parents.",
        ),
        CaptureRecipe(
            "outcome", "Acceptance, signing, award", Pillar.OUTCOMES, 6,
            (
                "the student holding or reading the actual letter",
                "the reaction of the people around him",
                "a clean shot of the name and the destination",
                "one sentence: where he is going and what he will study",
                "the teacher who got him there, in the same frame",
            ),
            "college counseling or athletics",
            "Get the number and the spelling right. Outcomes claims need verification.",
        ),
        CaptureRecipe(
            "alumni", "Alumni on campus", Pillar.OUTCOMES, 8,
            (
                "the alum walking a hallway he used to walk",
                "the alum with a current teacher who taught him",
                "one sentence: what he does now, and what here prepared him for it",
                "the alum talking to current students",
            ),
            "advancement or alumni relations",
        ),
        CaptureRecipe(
            "heritage", "Campus, history and Polish heritage", Pillar.CATHOLIC, 10,
            (
                "architectural detail most students walk past",
                "an artifact, plaque or photograph with a story attached",
                "a tradition being performed by students who know it by heart",
                "campus in the season it is in right now",
            ),
            "anyone -- this is the easiest evergreen library to build",
            "Only St. Mary's can produce this footage. Nobody can copy it.",
        ),
        CaptureRecipe(
            "shadow_day", "Visit or shadow day", Pillar.BELONGING, 8,
            (
                "the visiting student being met at the door by his host",
                "the visitor inside a class, participating",
                "lunch -- the moment the visitor stops looking like a visitor",
                "the parent waiting in the lobby (with permission)",
                "one sentence from the host about what he showed him",
            ),
            "admissions",
            "Consent first, always -- visiting students are not our students yet.",
        ),
    )
}


@dataclass
class CaptureAssignment:
    """One specific request handed to one specific person on one specific day."""

    when: date
    recipe: CaptureRecipe
    owner: str
    reason: str
    shots: tuple[str, ...]
    priority: int = 2  # 1 = highest

    def to_dict(self) -> dict[str, Any]:
        return {
            "when": self.when.isoformat(),
            "recipe": self.recipe.key,
            "name": self.recipe.name,
            "owner": self.owner,
            "reason": self.reason,
            "shots": list(self.shots),
            "minutes": self.recipe.minutes,
            "priority": self.priority,
        }

    def as_text(self) -> str:
        lines = [
            f"{self.recipe.name} -- {self.owner} ({self.recipe.minutes} min)",
            f"Why: {self.reason}",
        ]
        lines += [f"  [ ] {shot}" for shot in self.shots]
        if self.recipe.note:
            lines.append(f"  ! {self.recipe.note}")
        return "\n".join(lines)


def recipe_for_pillar(pillar: Pillar) -> list[CaptureRecipe]:
    return [r for r in RECIPES.values() if r.pillar is pillar]


def build_capture_list(
    when: date,
    *,
    events: Sequence[Any] = (),
    pillar_deficits: Sequence[Pillar] = (),
    include_baseline: bool = True,
) -> list[CaptureAssignment]:
    """Today's capture requests: what is happening, plus what we are short on.

    `events` are CalendarEvent-like objects exposing `.name`, `.capture_recipe`
    and `.department`.
    """
    assignments: list[CaptureAssignment] = []
    seen: set[str] = set()

    for event in events:
        key = getattr(event, "capture_recipe", "") or ""
        recipe = RECIPES.get(key)
        if not recipe or recipe.key in seen:
            continue
        seen.add(recipe.key)
        assignments.append(
            CaptureAssignment(
                when=when,
                recipe=recipe,
                owner=getattr(event, "department", "") or recipe.who,
                reason=f"on the calendar today: {getattr(event, 'name', 'scheduled event')}",
                shots=recipe.shots,
                priority=1,
            )
        )

    for pillar in pillar_deficits:
        for recipe in recipe_for_pillar(pillar):
            if recipe.key in seen:
                continue
            seen.add(recipe.key)
            assignments.append(
                CaptureAssignment(
                    when=when,
                    recipe=recipe,
                    owner=recipe.who,
                    reason=f"we are running thin on {pillar.spec.name}",
                    shots=recipe.shots,
                    priority=2,
                )
            )
            break

    if include_baseline:
        assignments.append(
            CaptureAssignment(
                when=when,
                recipe=RECIPES["classroom"],
                owner="every teacher, one class period",
                reason="baseline daily capture -- the library only grows if this happens",
                shots=BASELINE_DAILY,
                priority=3,
            )
        )

    assignments.sort(key=lambda a: a.priority)
    return assignments


def staff_one_pager() -> str:
    """The laminated sheet that goes next to the classroom door."""
    lines = [
        "HOW TO SEND US CONTENT",
        "",
        "1. Film or shoot it on your phone. Vertical.",
        "2. Scan the QR code on your door.",
        "3. Answer four questions: what, which department, your name, one sentence.",
        "4. Done. Do not rename files, resize photos or write captions.",
        "",
        "TODAY WE ALWAYS WANT:",
    ]
    lines += [f"  - {shot}" for shot in BASELINE_DAILY]
    lines += ["", "RULES:"]
    lines += [f"  - {rule}" for rule in CAPTURE_RULES]
    return "\n".join(lines)
