"""Software stack and cost discipline.

Before anything gets recommended it has to survive four questions, in order:
can Microsoft 365 do it, can the chat subscription do it, can the platform's
own tools do it -- and only then, is it worth paying for separately?

Every figure below is a budget estimate to verify against current vendor
pricing, not a quote. What matters is the ratio the school optimizes for:
cost per useful hour saved, not feature count.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

PRICING_AS_OF = "2026-08 -- estimates; confirm current vendor pricing before purchase"

# The school year, not the calendar year: roughly 40 working weeks.
SCHOOL_WEEKS = 40


@dataclass(frozen=True)
class Tool:
    name: str
    purpose: str
    monthly_low: float
    monthly_high: float
    existing_alternative: str
    hours_saved_per_week: float
    essential: bool
    note: str = ""

    @property
    def monthly_mid(self) -> float:
        return (self.monthly_low + self.monthly_high) / 2

    @property
    def annual_mid(self) -> float:
        return self.monthly_mid * 12

    @property
    def cost_label(self) -> str:
        if self.monthly_high == 0:
            return "$0 (already licensed)"
        if self.monthly_low == self.monthly_high:
            return f"${self.monthly_low:.0f}"
        return f"${self.monthly_low:.0f}-${self.monthly_high:.0f}"


STACK: tuple[Tool, ...] = (
    Tool(
        name="Microsoft 365 (SharePoint, Forms, Power Automate, Lists, Teams)",
        purpose=("Content inbox behind the QR code, intake form, triage routing, content "
                 "queue, approval notifications"),
        monthly_low=0, monthly_high=0,
        existing_alternative="already licensed -- this IS the alternative to four SaaS products",
        hours_saved_per_week=3.0,
        essential=True,
        note="Do not buy a DAM, a form builder, a workflow tool or a task tracker. You own all four.",
    ),
    Tool(
        name="Claude or ChatGPT (one team seat)",
        purpose="Ideation, captions, hook options, transcript-to-edit-plan, weekly analysis",
        monthly_low=20, monthly_high=30,
        existing_alternative="none at this quality; the API is an option if volume justifies it",
        hours_saved_per_week=4.0,
        essential=True,
        note="One seat, used by the person who runs the queue. Not per-department seats.",
    ),
    Tool(
        name="Native platform schedulers (Meta Business Suite, TikTok, YouTube Studio)",
        purpose="Scheduling and first-party analytics on every platform we actually use",
        monthly_low=0, monthly_high=0,
        existing_alternative="this IS the alternative to a paid scheduler",
        hours_saved_per_week=1.5,
        essential=True,
        note="Free, first-party, and the analytics are better than the resold versions.",
    ),
    Tool(
        name="CapCut (free tier) or Adobe Express",
        purpose="Vertical cutting, auto-captions, audio cleanup on a phone or laptop",
        monthly_low=0, monthly_high=15,
        existing_alternative="Clipchamp is included with Microsoft 365",
        hours_saved_per_week=2.5,
        essential=True,
        note="Start on the free tier. Upgrade only when a specific limit blocks a specific job.",
    ),
    Tool(
        name="Canva Teams",
        purpose="Quote cards, story templates, consistent typography for non-designers",
        monthly_low=10, monthly_high=15,
        existing_alternative="PowerPoint templates (owned) cover quote cards adequately",
        hours_saved_per_week=1.0,
        essential=False,
        note="Worth it only if two or more non-designers are producing graphics weekly.",
    ),
    Tool(
        name="Cross-platform scheduler (Metricool, Buffer, Later or similar)",
        purpose="One queue and one analytics view across all platforms",
        monthly_low=25, monthly_high=100,
        existing_alternative="native schedulers plus a Microsoft List; free, more work",
        hours_saved_per_week=2.0,
        essential=False,
        note=("Justified once someone is posting to five or more accounts weekly. Below that "
              "it is a convenience purchase."),
    ),
    Tool(
        name="GA4 + UTM tagging",
        purpose="Connect campaigns to visits, inquiries and applications",
        monthly_low=0, monthly_high=0,
        existing_alternative="this IS the alternative to an attribution product",
        hours_saved_per_week=0.5,
        essential=True,
        note="Without this, every claim about what converts is a guess.",
    ),
    Tool(
        name="Paid social budget (Meta / TikTok admissions campaigns)",
        purpose="Move a defined audience from awareness to visit, inquiry and application",
        monthly_low=300, monthly_high=1500,
        existing_alternative="none -- this is media, not software",
        hours_saved_per_week=0.0,
        essential=False,
        note=("Budget it separately from software. Seasonal: heaviest in the visit and yield "
              "windows, near zero in June."),
    ),
)

DECISION_LADDER: tuple[str, ...] = (
    "1. Can Microsoft 365 do it? (SharePoint, Forms, Power Automate, Lists, Teams, Clipchamp)",
    "2. Can the chat subscription we already pay for do it?",
    "3. Can the platform's own native tools do it?",
    "4. Only then: does a paid application save more hours than it costs?",
)

DO_NOT_PAY_TWICE: tuple[str, ...] = (
    "idea generation", "captions", "social scheduling", "analytics",
    "AI rewriting", "content calendars", "file storage",
)


def software_only(tools: Sequence[Tool] = STACK) -> list[Tool]:
    """Media spend is not software. Keep it out of the software math."""
    return [t for t in tools if "media, not software" not in t.existing_alternative]


def annual_cost(tools: Sequence[Tool] | None = None) -> float:
    return sum(t.annual_mid for t in software_only(tools or STACK))


def hours_saved_per_year(tools: Sequence[Tool] | None = None) -> float:
    return sum(t.hours_saved_per_week for t in software_only(tools or STACK)) * SCHOOL_WEEKS


def cost_per_hour_saved(tools: Sequence[Tool] | None = None) -> float:
    hours = hours_saved_per_year(tools)
    return annual_cost(tools) / hours if hours else float("inf")


def essential(tools: Sequence[Tool] = STACK) -> list[Tool]:
    return [t for t in software_only(tools) if t.essential]


def table(tools: Sequence[Tool] = STACK) -> str:
    """The required table: tool, purpose, cost, alternative, labor saved, essential."""
    header = (
        "| Tool | Purpose | Monthly Cost | Existing Alternative | Labor Saved | Essential? |\n"
        "| --- | --- | --- | --- | --- | --- |"
    )
    rows = [
        f"| {t.name} | {t.purpose} | {t.cost_label} | {t.existing_alternative} | "
        f"{t.hours_saved_per_week:.1f} hrs/wk | {'Essential' if t.essential else 'Optional'} |"
        for t in tools
    ]
    return "\n".join([header, *rows])


def summary(tools: Sequence[Tool] = STACK) -> str:
    minimum = essential(tools)
    min_annual = sum(t.annual_mid for t in minimum)
    min_hours = sum(t.hours_saved_per_week for t in minimum) * SCHOOL_WEEKS
    lines = [
        f"Pricing basis: {PRICING_AS_OF}",
        "",
        "Before recommending anything new:",
        *[f"  {step}" for step in DECISION_LADDER],
        "",
        "Never pay separately for what the stack already covers: "
        + ", ".join(DO_NOT_PAY_TWICE) + ".",
        "",
        f"Essential stack:  ${min_annual:,.0f}/year, ~{min_hours:,.0f} staff hours saved "
        f"({SCHOOL_WEEKS}-week school year)",
    ]
    if min_hours:
        lines.append(f"  -> ${min_annual / min_hours:,.2f} per hour saved")
    lines += [
        f"Full stack incl. optional: ${annual_cost(tools):,.0f}/year, "
        f"~{hours_saved_per_year(tools):,.0f} hours saved",
        f"  -> ${cost_per_hour_saved(tools):,.2f} per hour saved",
        "",
        "Media budget is tracked separately and is not part of the software figure.",
    ]
    return "\n".join(lines)
