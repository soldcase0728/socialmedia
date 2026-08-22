"""Brand memory: the reason the system is smarter in March than in September.

Every measured result feeds performance statistics here, and every strong
quote, objection, statistic and story gets banked. Nothing starts from zero on
a Monday morning.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from . import store
from .audiences import Audience
from .brand import Pillar

MEMORY_KEY = "memory"


@dataclass
class PerfStat:
    """A running average. Kept simple so it can be read straight out of JSON."""

    n: int = 0
    mean: float = 0.0
    best: float = 0.0
    best_ref: str = ""

    def record(self, value: float, ref: str = "") -> "PerfStat":
        self.mean = (self.mean * self.n + value) / (self.n + 1)
        self.n += 1
        if value > self.best:
            self.best = value
            self.best_ref = ref
        return self

    @property
    def confident(self) -> bool:
        """Three observations is not proof, but it is enough to plan around."""
        return self.n >= 3

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PerfStat":
        return cls(
            n=int(data.get("n", 0)),
            mean=float(data.get("mean", 0.0)),
            best=float(data.get("best", 0.0)),
            best_ref=data.get("best_ref", ""),
        )


# Starting objection library. These are the questions admissions offices at
# schools like this one actually field. Replace them with what OUR admissions
# team hears -- that list is more valuable than any of this.
SEED_OBJECTIONS: list[dict[str, str]] = [
    {"objection": "Is it worth the tuition?",
     "pillar": Pillar.OUTCOMES.value,
     "answer": "Show the return with names and numbers, not adjectives.",
     "evidence_needed": "verified acceptances, scholarship totals, a named graduate's path",
     "source": "template -- replace with what admissions actually hears"},
    {"objection": "Will my son be known here, or will he disappear?",
     "pillar": Pillar.KNOWN.value,
     "answer": "Show one adult paying attention to one specific student.",
     "evidence_needed": "advisor check-in footage, a teacher using a student's name",
     "source": "template"},
    {"objection": "Isn't this mostly an athletics school?",
     "pillar": Pillar.CHALLENGED.value,
     "answer": "Answer with the classroom, not by defending athletics.",
     "evidence_needed": "AP and dual-enrollment work in progress, competition results",
     "source": "template"},
    {"objection": "How rigorous is it really?",
     "pillar": Pillar.CHALLENGED.value,
     "answer": "Show work hard enough that a parent recognizes it as hard.",
     "evidence_needed": "a whiteboard, a revised draft, a lab that failed the first time",
     "source": "template"},
    {"objection": "We're not Catholic. Will he belong?",
     "pillar": Pillar.CATHOLIC.value,
     "answer": "Show faith as lived and welcoming, not as a membership test.",
     "evidence_needed": "students participating naturally, a priest in ordinary conversation",
     "source": "template"},
    {"objection": "It is a long drive.",
     "pillar": Pillar.BELONGING.value,
     "answer": "Make the day on the other end of the drive look worth it.",
     "evidence_needed": "morning arrival, the bus, what happens before first period",
     "source": "template"},
    {"objection": "He would be coming alone, without his friends.",
     "pillar": Pillar.BELONGING.value,
     "answer": "Show a freshman being pulled in by upperclassmen in week one.",
     "evidence_needed": "orientation, lunch tables, a host on a shadow day",
     "source": "template"},
    {"objection": "What happens if he struggles?",
     "pillar": Pillar.KNOWN.value,
     "answer": "Show the support structure operating on a normal day.",
     "evidence_needed": "tutoring, an advisor noticing, a teacher staying after",
     "source": "template"},
]


@dataclass
class BrandMemory:
    """Everything the system has learned, in one file a human can read."""

    hooks: dict[str, PerfStat] = field(default_factory=dict)
    pillars: dict[str, PerfStat] = field(default_factory=dict)
    platforms: dict[str, PerfStat] = field(default_factory=dict)
    formats: dict[str, PerfStat] = field(default_factory=dict)
    audiences: dict[str, PerfStat] = field(default_factory=dict)

    best_posts: list[dict[str, Any]] = field(default_factory=list)
    student_stories: list[dict[str, Any]] = field(default_factory=list)
    testimonials: list[dict[str, Any]] = field(default_factory=list)
    statistics: list[dict[str, Any]] = field(default_factory=list)
    objections: list[dict[str, Any]] = field(default_factory=lambda: list(SEED_OBJECTIONS))
    outcomes: list[dict[str, Any]] = field(default_factory=list)
    traditions: list[str] = field(default_factory=list)
    signature_phrases: list[str] = field(default_factory=list)
    photography_patterns: list[str] = field(default_factory=list)
    underused_stories: list[str] = field(default_factory=list)
    evergreen: list[dict[str, Any]] = field(default_factory=list)

    # -- learning -----------------------------------------------------------

    def record_result(self, result: Any, index: float) -> "BrandMemory":
        """Fold one measured post into the running statistics."""
        ref = getattr(result, "post_id", "")
        buckets = (
            (self.hooks, getattr(result, "hook_structure", "")),
            (self.pillars, getattr(getattr(result, "pillar", None), "value", "")),
            (self.platforms, getattr(result, "platform", "")),
            (self.formats, getattr(result, "fmt", "")),
            (self.audiences, getattr(getattr(result, "audience", None), "value", "")),
        )
        for bucket, key in buckets:
            if key:
                bucket.setdefault(key, PerfStat()).record(index, ref)

        if index >= 1.4:
            self.best_posts.append({
                "post_id": ref,
                "index": round(index, 2),
                "platform": getattr(result, "platform", ""),
                "pillar": getattr(getattr(result, "pillar", None), "value", ""),
                "hook_structure": getattr(result, "hook_structure", ""),
                "event": getattr(result, "event", ""),
            })
            self.best_posts.sort(key=lambda p: -p["index"])
            del self.best_posts[25:]
        return self

    # -- retrieval ----------------------------------------------------------

    def _ranked(self, bucket: dict[str, PerfStat], limit: int, confident_only: bool) -> list[tuple[str, PerfStat]]:
        items = [(k, v) for k, v in bucket.items() if not confident_only or v.confident]
        items.sort(key=lambda kv: -kv[1].mean)
        return items[:limit]

    def top_hooks(self, limit: int = 3, *, confident_only: bool = True) -> list[tuple[str, PerfStat]]:
        return self._ranked(self.hooks, limit, confident_only)

    def top_platforms(self, limit: int = 3, *, confident_only: bool = True) -> list[tuple[str, PerfStat]]:
        return self._ranked(self.platforms, limit, confident_only)

    def objections_for(self, pillar: Pillar) -> list[dict[str, Any]]:
        return [o for o in self.objections if o.get("pillar") == pillar.value]

    def verified_statistics(self) -> list[dict[str, Any]]:
        return [s for s in self.statistics if s.get("verified")]

    def recommend(self, pillar: Pillar, audience: Audience) -> list[str]:
        """What history says to do with this pillar and audience.

        Performance notes and the seeded objection library are separate: a
        starting objection must never be mistaken for evidence we have measured
        something. When there is no performance history, say so plainly.
        """
        performance: list[str] = []
        for structure, stat in self.top_hooks(2):
            performance.append(
                f"open with a '{structure}' hook -- it averages {stat.mean:.2f}x median over "
                f"{stat.n} posts (best: {stat.best_ref})"
            )
        pillar_stat = self.pillars.get(pillar.value)
        if pillar_stat and pillar_stat.confident:
            verb = "has been carrying" if pillar_stat.mean >= 1.0 else "has been underperforming at"
            performance.append(
                f"{pillar.spec.name} {verb} {pillar_stat.mean:.2f}x median (n={pillar_stat.n})"
            )
        audience_stat = self.audiences.get(audience.value)
        if audience_stat and audience_stat.confident:
            performance.append(
                f"{audience.spec.name} content averages {audience_stat.mean:.2f}x median "
                f"(n={audience_stat.n})"
            )

        if not performance:
            observed = sum(stat.n for stat in self.hooks.values())
            performance.append(
                "no confident performance history for this combination yet "
                f"({observed} post(s) measured so far) -- this week's result becomes the baseline"
            )

        objections = [
            f"this pillar answers: \"{o['objection']}\" -- needs {o['evidence_needed']}"
            for o in self.objections_for(pillar)[:1]
        ]
        return performance + objections

    # -- banking ------------------------------------------------------------

    def bank_quote(self, quote: str, *, who: str, pillar: Pillar, when: date | None = None) -> None:
        self.testimonials.append({
            "quote": quote.strip(),
            "who": who,
            "pillar": pillar.value,
            "when": (when or date.today()).isoformat(),
        })

    def bank_statistic(self, statement: str, *, source: str, verified: bool = False,
                       expires: str = "") -> None:
        self.statistics.append({
            "statement": statement,
            "source": source,
            "verified": verified,
            "expires": expires,
        })

    def bank_story(self, story: str, *, pillar: Pillar, status: str = "unused") -> None:
        self.student_stories.append({"story": story, "pillar": pillar.value, "status": status})
        if status == "unused":
            self.underused_stories.append(story)

    # -- persistence --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "hooks": {k: v.to_dict() for k, v in self.hooks.items()},
            "pillars": {k: v.to_dict() for k, v in self.pillars.items()},
            "platforms": {k: v.to_dict() for k, v in self.platforms.items()},
            "formats": {k: v.to_dict() for k, v in self.formats.items()},
            "audiences": {k: v.to_dict() for k, v in self.audiences.items()},
            "best_posts": self.best_posts,
            "student_stories": self.student_stories,
            "testimonials": self.testimonials,
            "statistics": self.statistics,
            "objections": self.objections,
            "outcomes": self.outcomes,
            "traditions": self.traditions,
            "signature_phrases": self.signature_phrases,
            "photography_patterns": self.photography_patterns,
            "underused_stories": self.underused_stories,
            "evergreen": self.evergreen,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BrandMemory":
        def stats(key: str) -> dict[str, PerfStat]:
            return {k: PerfStat.from_dict(v) for k, v in (data.get(key) or {}).items()}

        return cls(
            hooks=stats("hooks"),
            pillars=stats("pillars"),
            platforms=stats("platforms"),
            formats=stats("formats"),
            audiences=stats("audiences"),
            best_posts=list(data.get("best_posts") or []),
            student_stories=list(data.get("student_stories") or []),
            testimonials=list(data.get("testimonials") or []),
            statistics=list(data.get("statistics") or []),
            objections=list(data.get("objections") or SEED_OBJECTIONS),
            outcomes=list(data.get("outcomes") or []),
            traditions=list(data.get("traditions") or []),
            signature_phrases=list(data.get("signature_phrases") or []),
            photography_patterns=list(data.get("photography_patterns") or []),
            underused_stories=list(data.get("underused_stories") or []),
            evergreen=list(data.get("evergreen") or []),
        )

    @classmethod
    def load(cls) -> "BrandMemory":
        return cls.from_dict(store.load(MEMORY_KEY, {}))

    def save(self) -> None:
        store.save(MEMORY_KEY, self.to_dict())


def learn_from_week(memory: BrandMemory, report: Any) -> BrandMemory:
    """Fold a WeeklyReport's indexed results into memory."""
    for result, index in list(report.winners) + list(report.losers):
        memory.record_result(result, index)
    return memory
