"""Measurement and the weekly intelligence report.

Two disciplines enforced here. First, vanity metrics are recorded but never
allowed to drive a recommendation. Second, observed evidence and strategic
inference are kept in separate fields -- because confusing the two is how a
marketing department convinces itself of something for a year.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Sequence

from .audiences import Audience, audience_read
from .brand import Pillar

# Canonical metric names, grouped the way the report reads them.
ATTENTION = ("impressions", "reach", "three_second_views", "avg_watch_seconds",
             "completions", "thumbstop_rate")
ENGAGEMENT = ("shares", "saves", "comments", "reactions")
INTEREST = ("profile_visits", "link_clicks", "site_sessions")
ADMISSIONS = ("inquiries", "visit_registrations", "shadow_registrations",
              "applications_started", "applications_completed", "enrollments")

# Recorded, reported, never used as evidence that something worked.
VANITY = ("reactions", "followers", "likes")

ALL_METRICS = ATTENTION + ENGAGEMENT + INTEREST + ADMISSIONS


@dataclass
class PostResult:
    """What one published item actually did."""

    post_id: str
    platform: str
    published_at: date
    pillar: Pillar
    audience: Audience
    metrics: dict[str, float] = field(default_factory=dict)
    hook_structure: str = ""
    fmt: str = ""
    event: str = ""
    paid: bool = False

    def get(self, name: str) -> float | None:
        value = self.metrics.get(name)
        return float(value) if value is not None else None

    def _ratio(self, numerator: str, denominator: str) -> float | None:
        num, den = self.get(numerator), self.get(denominator)
        if num is None or not den:
            return None
        return num / den

    @property
    def base(self) -> float | None:
        return self.get("impressions") or self.get("reach")

    @property
    def hook_rate(self) -> float | None:
        """Three-second retention: did the opening hold anyone at all?"""
        views, base = self.get("three_second_views"), self.base
        if views is None or not base:
            return self.get("thumbstop_rate")
        return views / base

    @property
    def completion_rate(self) -> float | None:
        completions, base = self.get("completions"), self.base
        if completions is None or not base:
            return None
        return completions / base

    @property
    def share_rate(self) -> float | None:
        return self._ratio("shares", "impressions") or self._ratio("shares", "reach")

    @property
    def save_rate(self) -> float | None:
        return self._ratio("saves", "impressions") or self._ratio("saves", "reach")

    @property
    def click_rate(self) -> float | None:
        return self._ratio("link_clicks", "impressions") or self._ratio("link_clicks", "reach")

    @property
    def admissions_actions(self) -> float:
        return sum(self.get(m) or 0.0 for m in ADMISSIONS)

    def rates(self) -> dict[str, float]:
        found = {
            "hook_rate": self.hook_rate,
            "completion_rate": self.completion_rate,
            "share_rate": self.share_rate,
            "save_rate": self.save_rate,
            "click_rate": self.click_rate,
        }
        return {k: v for k, v in found.items() if v is not None}

    def to_dict(self) -> dict[str, Any]:
        return {
            "post_id": self.post_id,
            "platform": self.platform,
            "published_at": self.published_at.isoformat(),
            "pillar": self.pillar.value,
            "audience": self.audience.value,
            "metrics": dict(self.metrics),
            "hook_structure": self.hook_structure,
            "format": self.fmt,
            "event": self.event,
            "paid": self.paid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PostResult":
        return cls(
            post_id=data["post_id"],
            platform=data["platform"],
            published_at=date.fromisoformat(data["published_at"]),
            pillar=Pillar(data["pillar"]),
            audience=Audience(data["audience"]),
            metrics={k: float(v) for k, v in (data.get("metrics") or {}).items()},
            hook_structure=data.get("hook_structure", ""),
            fmt=data.get("format", ""),
            event=data.get("event", ""),
            paid=bool(data.get("paid", False)),
        )


# A platform median drawn from two or three posts is just those posts. Below
# this many samples we benchmark against everything instead, or the report
# reports that every post was exactly average.
MIN_PLATFORM_SAMPLE = 5


@dataclass
class Benchmarks:
    """Medians drawn from our own history -- not from an industry blog post."""

    by_platform: dict[str, dict[str, float]] = field(default_factory=dict)
    platform_counts: dict[str, dict[str, int]] = field(default_factory=dict)
    overall: dict[str, float] = field(default_factory=dict)
    sample: int = 0

    @classmethod
    def from_results(cls, results: Sequence[PostResult]) -> "Benchmarks":
        by_platform: dict[str, dict[str, list[float]]] = {}
        overall: dict[str, list[float]] = {}
        for result in results:
            for name, value in result.rates().items():
                by_platform.setdefault(result.platform, {}).setdefault(name, []).append(value)
                overall.setdefault(name, []).append(value)
        return cls(
            by_platform={
                platform: {k: statistics.median(v) for k, v in rates.items()}
                for platform, rates in by_platform.items()
            },
            platform_counts={
                platform: {k: len(v) for k, v in rates.items()}
                for platform, rates in by_platform.items()
            },
            overall={k: statistics.median(v) for k, v in overall.items()},
            sample=len(results),
        )

    def median(self, platform: str, rate: str) -> float | None:
        """Platform median when we have enough of that platform; otherwise overall."""
        count = self.platform_counts.get(platform, {}).get(rate, 0)
        if count >= MIN_PLATFORM_SAMPLE:
            platform_median = self.by_platform.get(platform, {}).get(rate)
            if platform_median:
                return platform_median
        return self.overall.get(rate) or None


def performance_index(result: PostResult, benchmarks: Benchmarks) -> float | None:
    """How this post did against our own median. 1.0 is typical."""
    ratios: list[float] = []
    for name, value in result.rates().items():
        median = benchmarks.median(result.platform, name)
        if median:
            ratios.append(min(value / median, 3.0))
    if len(ratios) < 2:
        return None
    return sum(ratios) / len(ratios)


@dataclass
class GroupPerformance:
    key: str
    n: int
    index: float
    admissions_actions: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "n": self.n,
            "index": round(self.index, 2),
            "admissions_actions": self.admissions_actions,
        }


def _group(
    results: Sequence[PostResult],
    benchmarks: Benchmarks,
    key_fn,
) -> list[GroupPerformance]:
    buckets: dict[str, list[PostResult]] = {}
    for result in results:
        key = key_fn(result)
        if key:
            buckets.setdefault(str(key), []).append(result)
    groups: list[GroupPerformance] = []
    for key, items in buckets.items():
        indices = [i for i in (performance_index(r, benchmarks) for r in items) if i is not None]
        if not indices:
            continue
        groups.append(
            GroupPerformance(
                key=key,
                n=len(items),
                index=sum(indices) / len(indices),
                admissions_actions=sum(r.admissions_actions for r in items),
            )
        )
    groups.sort(key=lambda g: -g.index)
    return groups


WINNER_INDEX = 1.4
LOSER_INDEX = 0.65
MIN_SAMPLE_FOR_INFERENCE = 3


@dataclass
class WeeklyReport:
    start: date
    end: date
    total_posts: int
    winners: list[tuple[PostResult, float]] = field(default_factory=list)
    losers: list[tuple[PostResult, float]] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    inference: list[str] = field(default_factory=list)
    by_pillar: list[GroupPerformance] = field(default_factory=list)
    by_audience: list[GroupPerformance] = field(default_factory=list)
    by_hook: list[GroupPerformance] = field(default_factory=list)
    by_format: list[GroupPerformance] = field(default_factory=list)
    by_platform: list[GroupPerformance] = field(default_factory=list)
    admissions_actions: float = 0.0
    next_week: list[str] = field(default_factory=list)
    capture_assignments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": [self.start.isoformat(), self.end.isoformat()],
            "total_posts": self.total_posts,
            "winners": [{"post_id": r.post_id, "index": round(i, 2), "event": r.event}
                        for r, i in self.winners],
            "losers": [{"post_id": r.post_id, "index": round(i, 2), "event": r.event}
                       for r, i in self.losers],
            "evidence": list(self.evidence),
            "inference": list(self.inference),
            "by_pillar": [g.to_dict() for g in self.by_pillar],
            "by_audience": [g.to_dict() for g in self.by_audience],
            "by_hook": [g.to_dict() for g in self.by_hook],
            "by_format": [g.to_dict() for g in self.by_format],
            "by_platform": [g.to_dict() for g in self.by_platform],
            "admissions_actions": self.admissions_actions,
            "next_week": list(self.next_week),
            "capture_assignments": list(self.capture_assignments),
        }

    def as_text(self) -> str:
        lines = [
            f"WEEKLY INTELLIGENCE REPORT  {self.start} to {self.end}",
            f"{self.total_posts} items published | {self.admissions_actions:.0f} downstream admissions actions",
            "",
            "WINNERS",
        ]
        lines += [f"  {r.post_id} ({r.platform}) index {i:.2f} -- {r.event or r.pillar.spec.name}"
                  for r, i in self.winners] or ["  nothing cleared the bar this week"]
        lines += ["", "LOSERS"]
        lines += [f"  {r.post_id} ({r.platform}) index {i:.2f} -- {r.event or r.pillar.spec.name}"
                  for r, i in self.losers] or ["  nothing underperformed badly"]
        lines += ["", "OBSERVED EVIDENCE"]
        lines += [f"  - {e}" for e in self.evidence] or ["  - not enough data yet"]
        lines += ["", "STRATEGIC INFERENCE (unproven -- test before acting as if settled)"]
        lines += [f"  ? {i}" for i in self.inference] or ["  ? none worth stating yet"]
        lines += ["", "PILLAR PERFORMANCE"]
        lines += [f"  {g.key:<26} index {g.index:.2f} (n={g.n})" for g in self.by_pillar]
        lines += ["", "CREATIVE PERFORMANCE"]
        lines += [f"  hook: {g.key:<22} index {g.index:.2f} (n={g.n})" for g in self.by_hook]
        lines += ["", "NEXT WEEK"]
        lines += [f"  - {n}" for n in self.next_week]
        lines += ["", "CAPTURE ASSIGNMENTS"]
        lines += [f"  - {c}" for c in self.capture_assignments]
        return "\n".join(lines)


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def weekly_report(
    results: Sequence[PostResult],
    *,
    start: date | None = None,
    end: date | None = None,
    history: Sequence[PostResult] = (),
) -> WeeklyReport:
    """Build the weekly report from this week's results, benchmarked on history."""
    window = list(results)
    if start and end:
        window = [r for r in results if start <= r.published_at <= end]
    if not window:
        today = end or date.today()
        return WeeklyReport(
            start=start or today - timedelta(days=6),
            end=today,
            total_posts=0,
            evidence=["nothing was published in this window"],
            next_week=["publish something, or explain why the week was empty"],
        )

    start = start or min(r.published_at for r in window)
    end = end or max(r.published_at for r in window)
    benchmarks = Benchmarks.from_results(list(history) + window)

    indexed = [(r, performance_index(r, benchmarks)) for r in window]
    scored = [(r, i) for r, i in indexed if i is not None]
    scored.sort(key=lambda pair: -pair[1])

    report = WeeklyReport(
        start=start,
        end=end,
        total_posts=len(window),
        winners=[(r, i) for r, i in scored if i >= WINNER_INDEX][:5],
        losers=[(r, i) for r, i in scored if i <= LOSER_INDEX][-5:],
        by_pillar=_group(window, benchmarks, lambda r: r.pillar.spec.name),
        by_audience=_group(window, benchmarks, lambda r: r.audience.spec.name),
        by_hook=_group(window, benchmarks, lambda r: r.hook_structure),
        by_format=_group(window, benchmarks, lambda r: r.fmt),
        by_platform=_group(window, benchmarks, lambda r: r.platform),
        admissions_actions=sum(r.admissions_actions for r in window),
    )

    # ---- observed evidence: numbers only, no explanation attached ----------
    for result, index in report.winners:
        rates = result.rates()
        detail = ", ".join(f"{k.replace('_', ' ')} {_fmt_rate(v)}" for k, v in rates.items())
        report.evidence.append(
            f"{result.post_id} on {result.platform} ran {index:.2f}x our median ({detail})"
        )
    for result, index in report.losers:
        report.evidence.append(
            f"{result.post_id} on {result.platform} ran {index:.2f}x our median"
        )
    if report.admissions_actions:
        top = max(report.by_pillar, key=lambda g: g.admissions_actions, default=None)
        if top and top.admissions_actions:
            report.evidence.append(
                f"{top.admissions_actions:.0f} of this week's admissions actions followed "
                f"{top.key} content"
            )
    vanity_present = [m for m in VANITY if any(r.get(m) for r in window)]
    if vanity_present:
        report.evidence.append(
            f"recorded but not used to judge anything: {', '.join(vanity_present)}"
        )

    # ---- strategic inference: labeled, sample-gated, always falsifiable ----
    audiences = [r.audience for r in window]
    read = audience_read(audiences)
    if report.by_audience:
        best_audience = report.by_audience[0]
        if best_audience.n >= MIN_SAMPLE_FOR_INFERENCE:
            report.inference.append(
                f"content aimed at {best_audience.key} is outperforming (index "
                f"{best_audience.index:.2f}, n={best_audience.n}); the week's mix skewed {read}"
            )
        else:
            report.inference.append(
                f"{best_audience.key} leads on index but n={best_audience.n} -- too small to act on"
            )
    if report.by_hook and report.by_hook[0].n >= MIN_SAMPLE_FOR_INFERENCE:
        hook = report.by_hook[0]
        report.inference.append(
            f"the '{hook.key}' hook structure is carrying the openings (index {hook.index:.2f}, "
            f"n={hook.n}) -- run it twice more before treating it as a rule"
        )
    weak_pillars = [g for g in report.by_pillar if g.index < 1.0 and g.n >= 2]
    if weak_pillars:
        worst = weak_pillars[-1]
        report.inference.append(
            f"{worst.key} is underperforming (index {worst.index:.2f}); the likelier explanation "
            "is weak evidence in the footage rather than a weak message -- check the shots before "
            "changing the strategy"
        )

    # ---- next week + capture ---------------------------------------------
    if report.winners:
        best = report.winners[0][0]
        report.next_week.append(
            f"re-cut {best.post_id} for the platforms it did not run on, and test it as paid creative"
        )
        report.capture_assignments.append(
            f"more of whatever produced {best.post_id}: {best.event or best.pillar.spec.name}"
        )
    for group in report.by_pillar[-2:]:
        if group.index < 1.0:
            pillar = next((p for p in Pillar if p.spec.name == group.key), None)
            if pillar:
                report.next_week.append(
                    f"{group.key}: stop asserting it, show it -- {pillar.spec.evidence_test}"
                )
                report.capture_assignments.append(
                    f"{group.key}: {pillar.spec.proof[0]}; {pillar.spec.proof[1]}"
                )
    if not report.admissions_actions:
        report.next_week.append(
            "no downstream admissions actions were attributed this week -- add UTM tags or a "
            "landing page per campaign before drawing conclusions about what converts"
        )
    return report
