"""Calendars: 7-day execution, 30-day content, 90-day campaign.

The calendar exists to guarantee coverage, not to force publication. Roughly
70% of slots are planned against it; 30% are held open so an excellent
unplanned moment always outranks a scheduled mediocre one.

The liturgical dates here are computed and correct. The school and admissions
anchors are a *template* keyed off Labor Day -- replace them with the real
calendar by editing SCHOOL_ANCHORS or loading events from a file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Sequence

from . import config
from .audiences import PILLAR_AUDIENCES, Audience
from .brand import Pillar
from .mix import weighted_sequence
from .platforms import Platform

# ---------------------------------------------------------------------------
# Liturgical calendar
# ---------------------------------------------------------------------------


def easter(year: int) -> date:
    """Gregorian Easter (anonymous computus)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    lunar = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * lunar) // 451
    month, day = divmod(h + lunar - 7 * m + 114, 31)
    return date(year, month, day + 1)


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """The nth given weekday of a month (weekday: Monday=0)."""
    day = date(year, month, 1)
    offset = (weekday - day.weekday()) % 7
    return day + timedelta(days=offset + 7 * (n - 1))


def liturgical_anchors(year: int) -> list["CalendarEvent"]:
    """Fixed and movable feasts that matter to this school's identity."""
    pascha = easter(year)
    events = [
        ("Ash Wednesday", pascha - timedelta(days=46), "mass"),
        ("Palm Sunday", pascha - timedelta(days=7), "mass"),
        ("Holy Thursday", pascha - timedelta(days=3), "mass"),
        ("Good Friday", pascha - timedelta(days=2), "mass"),
        ("Easter Sunday", pascha, "mass"),
        ("Divine Mercy Sunday", pascha + timedelta(days=7), "mass"),
        ("Ascension", pascha + timedelta(days=39), "mass"),
        ("Pentecost", pascha + timedelta(days=49), "mass"),
        ("St. Joseph the Worker", date(year, 5, 1), "service"),
        ("Polish Constitution Day", date(year, 5, 3), "heritage"),
        ("Feast of St. Joseph", date(year, 3, 19), "mass"),
        ("Our Lady of Czestochowa", date(year, 8, 26), "heritage"),
        ("Feast of St. John Paul II", date(year, 10, 22), "heritage"),
        ("All Saints", date(year, 11, 1), "mass"),
        ("All Souls", date(year, 11, 2), "mass"),
        ("Immaculate Conception", date(year, 12, 8), "mass"),
        ("Christmas", date(year, 12, 25), "heritage"),
    ]
    return [
        CalendarEvent(
            name=name,
            when=when,
            kind="liturgical",
            department="Campus Ministry",
            pillar=Pillar.CATHOLIC,
            capture_recipe=recipe,
            audiences=(Audience.CURRENT_PARENT, Audience.PROSPECTIVE_PARENT, Audience.ALUMNI),
            verified=True,
        )
        for name, when, recipe in events
    ]


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

EVENT_KINDS = ("school", "academic", "athletics", "liturgical", "admissions", "advancement")


@dataclass
class CalendarEvent:
    name: str
    when: date
    kind: str
    department: str = ""
    pillar: Pillar | None = None
    capture_recipe: str = ""
    audiences: tuple[Audience, ...] = ()
    note: str = ""
    verified: bool = False
    """False means the date came from the template, not from the school office."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "when": self.when.isoformat(),
            "kind": self.kind,
            "department": self.department,
            "pillar": self.pillar.value if self.pillar else None,
            "capture_recipe": self.capture_recipe,
            "audiences": [a.value for a in self.audiences],
            "note": self.note,
            "verified": self.verified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CalendarEvent":
        return cls(
            name=data["name"],
            when=date.fromisoformat(data["when"]),
            kind=data.get("kind", "school"),
            department=data.get("department", ""),
            pillar=Pillar(data["pillar"]) if data.get("pillar") else None,
            capture_recipe=data.get("capture_recipe", ""),
            audiences=tuple(Audience(a) for a in data.get("audiences", ())),
            note=data.get("note", ""),
            verified=bool(data.get("verified", False)),
        )


def school_year_anchors(fall_year: int) -> list[CalendarEvent]:
    """Template school/admissions calendar for the year beginning in `fall_year`.

    Anchored to Labor Day. Every event here is `verified=False` until someone
    checks it against the school's published calendar.
    """
    labor_day = nth_weekday(fall_year, 9, 0, 1)
    first_day = labor_day + timedelta(days=1)
    spring = fall_year + 1

    def ev(name, when, kind, department, pillar, recipe, audiences, note=""):
        return CalendarEvent(name, when, kind, department, pillar, recipe, audiences, note)

    return [
        ev("First day of school", first_day, "school", "Student Life", Pillar.BELONGING,
           "hallway", (Audience.CURRENT_PARENT, Audience.GRADE_8)),
        ev("Opening Mass of the Holy Spirit", first_day + timedelta(days=2), "liturgical",
           "Campus Ministry", Pillar.CATHOLIC, "mass",
           (Audience.CURRENT_PARENT, Audience.PROSPECTIVE_PARENT)),
        ev("Fall open house", nth_weekday(fall_year, 10, 6, 3), "admissions", "Admissions",
           Pillar.KNOWN, "shadow_day", (Audience.PROSPECTIVE_PARENT, Audience.GRADE_8),
           "Peak inquiry window. Everything captured here has paid potential."),
        ev("Homecoming week", first_day + timedelta(days=44), "school", "Student Life",
           Pillar.BELONGING, "athletics_game",
           (Audience.GRADE_6_7, Audience.GRADE_8, Audience.ALUMNI)),
        ev("Shadow day window opens", date(fall_year, 10, 15), "admissions", "Admissions",
           Pillar.BELONGING, "shadow_day", (Audience.GRADE_8,)),
        ev("First semester exams", date(fall_year, 12, 15), "academic", "Academics",
           Pillar.CHALLENGED, "classroom", (Audience.CURRENT_PARENT,)),
        ev("Application deadline", date(fall_year, 12, 15), "admissions", "Admissions",
           Pillar.OUTCOMES, "", (Audience.GRADE_8, Audience.PROSPECTIVE_PARENT),
           "Verify the real deadline before any post references it."),
        ev("Catholic Schools Week", nth_weekday(spring, 1, 6, 5), "school", "Marketing",
           Pillar.CATHOLIC, "mass",
           (Audience.PROSPECTIVE_PARENT, Audience.CURRENT_PARENT, Audience.ALUMNI)),
        ev("Winter open house", nth_weekday(spring, 1, 6, 3), "admissions", "Admissions",
           Pillar.KNOWN, "shadow_day", (Audience.PROSPECTIVE_PARENT, Audience.GRADE_8)),
        ev("Acceptance letters released", date(spring, 2, 1), "admissions", "Admissions",
           Pillar.OUTCOMES, "outcome", (Audience.GRADE_8, Audience.PROSPECTIVE_PARENT)),
        ev("Enrollment decision deadline", date(spring, 3, 15), "admissions", "Admissions",
           Pillar.OUTCOMES, "", (Audience.PROSPECTIVE_PARENT,),
           "Verify with admissions -- this drives the whole yield campaign."),
        ev("Spring musical", date(spring, 4, 10), "school", "Arts", Pillar.BELONGING,
           "arts", (Audience.CURRENT_PARENT, Audience.GRADE_6_7)),
        ev("College decision day", date(spring, 5, 1), "academic", "College Counseling",
           Pillar.OUTCOMES, "outcome",
           (Audience.PROSPECTIVE_PARENT, Audience.ALUMNI, Audience.DONOR)),
        ev("Baccalaureate Mass", date(spring, 5, 22), "liturgical", "Campus Ministry",
           Pillar.CATHOLIC, "mass", (Audience.CURRENT_PARENT, Audience.ALUMNI)),
        ev("Graduation", date(spring, 5, 23), "school", "Head of School", Pillar.OUTCOMES,
           "outcome", (Audience.CURRENT_PARENT, Audience.ALUMNI, Audience.DONOR)),
    ]


def default_calendar(fall_year: int) -> list[CalendarEvent]:
    events = school_year_anchors(fall_year) + liturgical_anchors(fall_year) + \
        liturgical_anchors(fall_year + 1)
    events.sort(key=lambda e: e.when)
    return events


def events_on(events: Sequence[CalendarEvent], when: date) -> list[CalendarEvent]:
    return [e for e in events if e.when == when]


def events_between(events: Sequence[CalendarEvent], start: date, end: date) -> list[CalendarEvent]:
    return sorted((e for e in events if start <= e.when <= end), key=lambda e: e.when)


# ---------------------------------------------------------------------------
# Admissions funnel phase
# ---------------------------------------------------------------------------

FUNNEL_PHASES: tuple[tuple[tuple[int, int], tuple[int, int], str, str], ...] = (
    ((8, 1), (10, 14), "awareness", "Be seen. Familiarity with 6th-8th graders, trust-building with parents."),
    ((10, 15), (12, 15), "interest_to_visit", "Convert attention into a visit: open house, shadow days, tours."),
    ((12, 16), (2, 1), "application", "Reduce friction to applying. Deadlines, process, reassurance."),
    ((2, 2), (4, 15), "yield", "Turn acceptance into enrollment. Belonging, freshman year, other families."),
    ((4, 16), (7, 31), "retention_and_story", "Reinforce the decision, bank evergreen stories, build the library."),
)


def funnel_phase(when: date) -> tuple[str, str]:
    for (sm, sd), (em, ed), name, objective in FUNNEL_PHASES:
        start = (sm, sd)
        end = (em, ed)
        point = (when.month, when.day)
        if start <= end:
            if start <= point <= end:
                return name, objective
        else:  # window wraps the new year
            if point >= start or point <= end:
                return name, objective
    return "awareness", FUNNEL_PHASES[0][3]


# ---------------------------------------------------------------------------
# Slots
# ---------------------------------------------------------------------------

PLANNED = "planned"
OPPORTUNISTIC = "opportunistic"

# The rotation a normal week walks through, in priority order.
WEEKLY_PLATFORM_ROTATION: tuple[Platform, ...] = (
    Platform.INSTAGRAM_REEL,
    Platform.FACEBOOK,
    Platform.TIKTOK,
    Platform.INSTAGRAM_FEED,
    Platform.INSTAGRAM_REEL,
    Platform.YOUTUBE_SHORTS,
    Platform.FACEBOOK,
    Platform.LINKEDIN,
)


@dataclass
class Slot:
    when: date
    time: str
    platform: Platform
    pillar: Pillar | None
    audience: Audience | None
    kind: str = PLANNED
    purpose: str = ""
    filled_by: str = ""
    event: str = ""

    @property
    def open(self) -> bool:
        return not self.filled_by

    def to_dict(self) -> dict[str, Any]:
        return {
            "when": self.when.isoformat(),
            "time": self.time,
            "platform": self.platform.value,
            "pillar": self.pillar.value if self.pillar else None,
            "audience": self.audience.value if self.audience else None,
            "kind": self.kind,
            "purpose": self.purpose,
            "filled_by": self.filled_by,
            "event": self.event,
        }


def _first_window(platform: Platform) -> str:
    windows = config.POSTING_WINDOWS.get(platform.value, ("12:00",))
    return windows[0]



# Some pillar/platform pairings are simply wrong: LinkedIn does not carry
# student-life content, and TikTok does not carry donor outcomes. Realign
# rather than publish a mismatch.
PLATFORM_PILLARS: dict[Platform, tuple[Pillar, ...]] = {
    Platform.LINKEDIN: (Pillar.OUTCOMES, Pillar.CHALLENGED, Pillar.FORMATION),
    Platform.TIKTOK: (Pillar.BELONGING, Pillar.CHALLENGED, Pillar.CATHOLIC, Pillar.FORMATION),
    Platform.INSTAGRAM_STORY: (Pillar.BELONGING, Pillar.KNOWN, Pillar.CATHOLIC,
                               Pillar.CHALLENGED, Pillar.FORMATION),
}


def align_pillar(platform: Platform, pillar: Pillar | None) -> Pillar | None:
    """Swap a pillar the platform cannot carry for one it can."""
    allowed = PLATFORM_PILLARS.get(platform)
    if pillar is None or allowed is None or pillar in allowed:
        return pillar
    return allowed[0]


def align_audience(platform: Platform, pillar: Pillar | None) -> Audience:
    """Pick the audience both the pillar and the platform actually serve."""
    primary = platform.spec.primary_audiences
    if pillar is not None:
        for audience in PILLAR_AUDIENCES[pillar]:
            if audience in primary:
                return audience
    return primary[0]


def week_plan(
    start: date,
    *,
    events: Sequence[CalendarEvent] = (),
    deficits: Sequence[Pillar] = (),
    target: int | None = None,
) -> list[Slot]:
    """The 7-day execution calendar.

    Planned slots carry a pillar and an audience before anyone shoots anything.
    Opportunistic slots stay deliberately empty.
    """
    target = target or config.WEEKLY_POST_TARGET
    planned_count = round(target * config.PLANNED_SHARE)
    open_count = target - planned_count
    pillars = weighted_sequence(planned_count, deficits)
    slots: list[Slot] = []

    for index in range(planned_count):
        day = start + timedelta(days=index % 7)
        platform = WEEKLY_PLATFORM_ROTATION[index % len(WEEKLY_PLATFORM_ROTATION)]
        pillar = align_pillar(platform, pillars[index] if index < len(pillars) else None)
        audience = align_audience(platform, pillar)
        todays_events = events_on(events, day)
        slots.append(
            Slot(
                when=day,
                time=_first_window(platform),
                platform=platform,
                pillar=pillar,
                audience=audience,
                kind=PLANNED,
                purpose=(pillar.spec.parent_promise if pillar else ""),
                event=todays_events[0].name if todays_events else "",
            )
        )

    for index in range(open_count):
        day = start + timedelta(days=(index * 2) % 7)
        slots.append(
            Slot(
                when=day,
                time="held",
                platform=Platform.INSTAGRAM_STORY,
                pillar=None,
                audience=None,
                kind=OPPORTUNISTIC,
                purpose="held open for whatever actually happens that day",
            )
        )

    slots.sort(key=lambda s: (s.when, s.time))
    return slots


@dataclass
class ThemeWeek:
    start: date
    theme: str
    pillar: Pillar
    audience: Audience
    events: list[CalendarEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "theme": self.theme,
            "pillar": self.pillar.value,
            "audience": self.audience.value,
            "events": [e.name for e in self.events],
        }


def thirty_day_plan(start: date, events: Sequence[CalendarEvent] = ()) -> list[ThemeWeek]:
    """Four themed weeks, pillar-balanced, aware of what is already scheduled."""
    pillars = weighted_sequence(4)
    weeks: list[ThemeWeek] = []
    for index in range(4):
        week_start = start + timedelta(days=7 * index)
        week_events = events_between(events, week_start, week_start + timedelta(days=6))
        pillar = week_events[0].pillar if week_events and week_events[0].pillar else pillars[index]
        phase, _ = funnel_phase(week_start)
        audience = (
            Audience.GRADE_8 if phase in ("interest_to_visit", "application", "yield")
            else Audience.PROSPECTIVE_PARENT
        )
        theme = week_events[0].name if week_events else f"{pillar.spec.name}: prove it"
        weeks.append(ThemeWeek(week_start, theme, pillar, audience, week_events))
    return weeks


@dataclass
class Campaign:
    start: date
    end: date
    phase: str
    objective: str
    audience: Audience
    pillars: tuple[Pillar, ...]
    paid: bool
    measurement: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "phase": self.phase,
            "objective": self.objective,
            "audience": self.audience.value,
            "pillars": [p.value for p in self.pillars],
            "paid": self.paid,
            "measurement": self.measurement,
        }


CAMPAIGN_SHAPES: dict[str, tuple[Audience, tuple[Pillar, ...], bool, str]] = {
    "awareness": (Audience.GRADE_6_7, (Pillar.BELONGING, Pillar.CHALLENGED), False,
                  "reach and 3-second retention with 6th-8th graders"),
    "interest_to_visit": (Audience.PROSPECTIVE_PARENT, (Pillar.KNOWN, Pillar.CHALLENGED), True,
                          "visit and open-house registrations"),
    "application": (Audience.GRADE_8, (Pillar.BELONGING, Pillar.OUTCOMES), True,
                    "applications started and completed"),
    "yield": (Audience.PROSPECTIVE_PARENT, (Pillar.BELONGING, Pillar.FORMATION), True,
              "accepted-to-enrolled conversion"),
    "retention_and_story": (Audience.CURRENT_PARENT, (Pillar.FORMATION, Pillar.CATHOLIC), False,
                            "evergreen library growth and parent advocacy"),
}


def ninety_day_campaigns(start: date) -> list[Campaign]:
    """Three consecutive 30-day campaign windows keyed to the admissions funnel."""
    campaigns: list[Campaign] = []
    for index in range(3):
        window_start = start + timedelta(days=30 * index)
        window_end = window_start + timedelta(days=29)
        phase, objective = funnel_phase(window_start)
        audience, pillars, paid, measurement = CAMPAIGN_SHAPES[phase]
        campaigns.append(
            Campaign(window_start, window_end, phase, objective, audience, pillars, paid, measurement)
        )
    return campaigns
