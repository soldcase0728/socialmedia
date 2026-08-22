"""The daily content engine.

`run_today()` returns the morning brief: the three to five strongest
opportunities, the stories to capture this week, what the mix is missing,
today's capture requests, and -- for the single strongest story -- the full
twelve-part operating output from story through paid potential.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Mapping, Sequence

from . import config
from .assets import Asset, Status
from .audiences import Audience, audience_read
from .brand import Pillar
from .calendar import CalendarEvent, events_between, events_on, funnel_phase
from .capture import CaptureAssignment, build_capture_list
from .copywriting import CopyDraft, write_package_copy
from .memory import BrandMemory
from .mix import MixReport, analyze
from .packages import ContentPackage, build_package
from .platforms import Platform
from .scoring import Verdict
from .triage import TriageResult, triage_batch

# How a single story rolls out across surfaces. Same story, different cut --
# never the same file posted five times.
DISTRIBUTION_ORDER: dict[Platform, tuple[int, str]] = {
    Platform.INSTAGRAM_STORY: (0, "same day, raw, while it is still today"),
    Platform.INSTAGRAM_REEL: (0, "afternoon window, the polished 25s cut"),
    Platform.TIKTOK: (0, "evening, rougher cut, student voice"),
    Platform.FACEBOOK: (1, "next morning, with the context parents want"),
    Platform.INSTAGRAM_FEED: (1, "midday, the single strongest frame"),
    Platform.YOUTUBE_SHORTS: (2, "titled for search, long shelf life"),
    Platform.YOUTUBE: (2, "the full version, if there is one"),
    Platform.LINKEDIN: (2, "outcome first, once, with the number in it"),
}


@dataclass
class Opportunity:
    """One event's worth of assets, triaged and ranked."""

    event: str
    assets: list[Asset]
    triage: TriageResult

    @property
    def score_total(self) -> int:
        return self.triage.score.total

    @property
    def verdict(self) -> Verdict:
        return self.triage.verdict

    def why(self) -> str:
        strengths = ", ".join(self.triage.score.strengths[:3]) or "no standout strengths"
        return (
            f"{self.score_total}/50 ({self.verdict.value}); strongest on {strengths}; "
            f"{self.triage.urgency.replace('_', ' ')}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "asset_ids": [a.asset_id for a in self.assets],
            "score_total": self.score_total,
            "verdict": self.verdict.value,
            "why": self.why(),
            "pillar": self.triage.primary_pillar.value,
            "audience_read": self.triage.audience_read,
        }


@dataclass
class PriorityStory:
    """The twelve-part operating output for the strongest story available."""

    story: str
    why: str
    audiences: tuple[Audience, ...]
    audience_read: str
    pillar: Pillar
    perception: str
    hooks: list[dict[str, Any]]
    capture_plan: list[str]
    package: ContentPackage
    copy: list[CopyDraft]
    production: list[str]
    distribution: list[dict[str, Any]]
    cta: str
    paid_potential: str
    follow_up: list[str]
    memory_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "story": self.story,
            "why": self.why,
            "audiences": [a.value for a in self.audiences],
            "audience_read": self.audience_read,
            "pillar": self.pillar.value,
            "perception": self.perception,
            "hooks": self.hooks,
            "capture_plan": list(self.capture_plan),
            "package": self.package.to_dict(),
            "copy": [c.to_dict() for c in self.copy],
            "production": list(self.production),
            "distribution": list(self.distribution),
            "cta": self.cta,
            "paid_potential": self.paid_potential,
            "follow_up": list(self.follow_up),
            "memory_notes": list(self.memory_notes),
        }


@dataclass
class DailyBrief:
    when: date
    phase: str
    phase_objective: str
    today: list[Opportunity] = field(default_factory=list)
    this_week: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    capture_request: list[CaptureAssignment] = field(default_factory=list)
    priority: PriorityStory | None = None
    mix: MixReport | None = None
    inbox_unresolved: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.when.isoformat(),
            "phase": self.phase,
            "phase_objective": self.phase_objective,
            "today": [o.to_dict() for o in self.today],
            "this_week": list(self.this_week),
            "missing": list(self.missing),
            "capture_request": [c.to_dict() for c in self.capture_request],
            "priority": self.priority.to_dict() if self.priority else None,
            "mix": self.mix.to_dict() if self.mix else None,
            "inbox_unresolved": self.inbox_unresolved,
        }

    def as_text(self) -> str:
        lines = [
            f"CONTENT ENGINE -- {self.when:%A, %B %d, %Y}",
            f"Admissions phase: {self.phase} -- {self.phase_objective}",
            "",
            "TODAY -- strongest opportunities",
        ]
        lines += [f"  {i}. {o.event} -- {o.why()}" for i, o in enumerate(self.today, 1)] or \
                 ["  nothing in the inbox scores high enough to publish today"]
        lines += ["", "THIS WEEK -- stories to capture"]
        lines += [f"  - {s}" for s in self.this_week] or ["  - calendar is quiet; go find something"]
        lines += ["", "MISSING -- what the mix has neglected"]
        lines += [f"  - {m}" for m in self.missing] or ["  - mix is balanced"]
        lines += ["", "CAPTURE REQUEST -- today"]
        for assignment in self.capture_request:
            lines.append("  " + assignment.as_text().replace("\n", "\n  "))

        if self.priority:
            p = self.priority
            lines += [
                "",
                "=" * 66,
                "PRIORITY STORY",
                f"  {p.story}",
                f"  Why: {p.why}",
                "",
                f"AUDIENCE: {p.audience_read} ({', '.join(a.spec.name for a in p.audiences)})",
                f"BRAND PILLAR: {p.pillar.spec.name} -- {p.perception}",
                "",
                "HOOKS",
            ]
            lines += [f"  {i}. {h['text']}  [{h['structure']}]" for i, h in enumerate(p.hooks, 1)]
            lines += ["", "CAPTURE PLAN"]
            lines += [f"  [ ] {c}" for c in p.capture_plan]
            lines += ["", "CONTENT PACKAGE"]
            lines += [f"  - {i.key}: {i.destination} ({i.fmt}, {i.audience.spec.name})"
                      for i in p.package.items]
            lines += ["", "COPY"]
            for draft in p.copy:
                where = draft.platform.spec.name if draft.platform else "internal"
                lines += [f"  --- {where} ---"]
                lines += ["    " + line for line in draft.text.splitlines()]
                if draft.warnings:
                    lines += [f"    ! {w}" for w in draft.warnings]
            lines += ["", "PRODUCTION"]
            lines += [f"  - {step}" for step in p.production]
            lines += ["", "DISTRIBUTION"]
            lines += [f"  {d['when']} {d['time']:>5}  {d['platform']:<16} {d['note']}"
                      for d in p.distribution]
            lines += ["", f"CTA: {p.cta or 'none -- familiarity only for this audience'}"]
            lines += [f"PAID POTENTIAL: {p.paid_potential}"]
            lines += ["", "FOLLOW-UP -- capture while the opportunity is open"]
            lines += [f"  [ ] {f}" for f in p.follow_up]
            if p.memory_notes:
                lines += ["", "WHAT WE HAVE LEARNED BEFORE"]
                lines += [f"  - {n}" for n in p.memory_notes]
        return "\n".join(lines)


def group_by_event(assets: Sequence[Asset]) -> dict[tuple[str, date], list[Asset]]:
    groups: dict[tuple[str, date], list[Asset]] = {}
    for asset in assets:
        groups.setdefault((asset.event, asset.captured_at), []).append(asset)
    return groups


def distribution_plan(package: ContentPackage, when: date) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for item in package.items:
        if item.platform is None:
            continue
        offset, note = DISTRIBUTION_ORDER.get(item.platform, (1, "when it fits"))
        windows = config.POSTING_WINDOWS.get(item.platform.value, ("12:00",))
        time = windows[min(offset, len(windows) - 1)]
        plan.append({
            "when": (when + timedelta(days=offset)).isoformat(),
            "time": time,
            "platform": item.platform.value,
            "note": note,
        })
    plan.sort(key=lambda d: (d["when"], d["time"]))
    if plan:
        plan[0]["note"] += " (first out -- it sets the read on everything after it)"
    return plan


def _priority_story(
    opportunity: Opportunity,
    when: date,
    memory: BrandMemory | None,
) -> PriorityStory:
    triaged = opportunity.triage
    pillar = triaged.primary_pillar
    package = build_package(triaged, opportunity.assets)
    lead_asset = opportunity.assets[0]
    evidence = [a.possible_story for a in opportunity.assets if a.possible_story]
    hook = triaged.hooks[0] if triaged.hooks else None

    social_items = [i for i in package.items if i.platform]
    drafts = write_package_copy(
        social_items,
        story=opportunity.event,
        pillar=pillar,
        hook=hook,
        evidence=evidence or [lead_asset.description],
    )

    production: list[str] = []
    for item in social_items[:2]:
        for step in item.production:
            if step not in production:
                production.append(step)

    primary_audience = triaged.audiences[0]
    cta_source = next((d.cta for d in drafts if d.cta), "")
    paid = (
        "Yes -- test as admissions creative with its own audience, proposition and CTA. "
        "Define the measurement before it spends."
        if triaged.paid_candidate
        else "No -- run it organically; it does not carry an admissions proposition."
    )

    return PriorityStory(
        story=triaged.story_angle,
        why=opportunity.why(),
        audiences=triaged.audiences,
        audience_read=triaged.audience_read,
        pillar=pillar,
        perception=pillar.spec.parent_promise,
        hooks=[h.to_dict() for h in triaged.hooks],
        capture_plan=list(triaged.needs_more_footage) or ["nothing further -- shoot list is complete"],
        package=package,
        copy=drafts,
        production=production,
        distribution=distribution_plan(package, when),
        cta=cta_source,
        paid_potential=paid,
        follow_up=list(triaged.needs_more_footage) + [
            f"missing fact for a stronger hook: {fact}" for fact in triaged.missing_facts
        ],
        memory_notes=memory.recommend(pillar, primary_audience) if memory else [],
    )


def run_today(
    when: date | None = None,
    *,
    assets: Sequence[Asset] = (),
    events: Sequence[CalendarEvent] = (),
    published: Sequence[Mapping[str, Any]] = (),
    memory: BrandMemory | None = None,
    max_today: int = 5,
) -> DailyBrief:
    """Run the morning content engine."""
    when = when or date.today()
    phase, objective = funnel_phase(when)

    fresh = [a for a in assets if a.status in (Status.RAW, Status.REVIEWED, Status.CONTENT_OPPORTUNITY)]
    opportunities: list[Opportunity] = []
    for (event, _), group in group_by_event(fresh).items():
        ranked = triage_batch(group, today=when)
        if ranked:
            opportunities.append(Opportunity(event=event, assets=group, triage=ranked[0]))
    opportunities.sort(key=lambda o: (-o.score_total, o.event))

    publishable = [o for o in opportunities if o.verdict in (Verdict.LEAD, Verdict.PUBLISH)]
    today = (publishable or opportunities)[:max_today]

    mix = analyze(list(published)) if published else None
    missing: list[str] = []
    deficits: list[Pillar] = []
    if mix:
        deficits = mix.pillar_deficits()
        missing.extend(mix.warnings)
    else:
        missing.append("no published history loaded -- mix balance cannot be checked yet")

    if memory:
        for story in memory.underused_stories[:2]:
            missing.append(f"banked but never used: {story}")

    upcoming = events_between(events, when, when + timedelta(days=7))
    this_week = [
        f"{e.when:%a %m/%d} {e.name} ({e.department or 'unassigned'})"
        + (f" -- shoot list: {e.capture_recipe}" if e.capture_recipe else "")
        + ("" if e.verified else "  [date unverified -- check the school calendar]")
        for e in upcoming[:10]
    ]
    for pillar in deficits[:2]:
        this_week.append(
            f"deliberate {pillar.spec.name} shoot: {pillar.spec.proof[0]}"
        )

    brief = DailyBrief(
        when=when,
        phase=phase,
        phase_objective=objective,
        today=today,
        this_week=this_week,
        missing=missing,
        capture_request=build_capture_list(
            when, events=events_on(events, when), pillar_deficits=deficits
        ),
        mix=mix,
        inbox_unresolved=sum(1 for a in assets if not a.resolved),
    )
    if today:
        brief.priority = _priority_story(today[0], when, memory)
    return brief
