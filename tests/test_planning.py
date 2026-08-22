"""Calendar, mix balance, capture lists and the daily brief."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from brandops import config
from brandops.brand import Pillar
from brandops.calendar import (
    OPPORTUNISTIC,
    PLANNED,
    align_audience,
    align_pillar,
    default_calendar,
    easter,
    events_between,
    funnel_phase,
    liturgical_anchors,
    ninety_day_campaigns,
    nth_weekday,
    thirty_day_plan,
    week_plan,
)
from brandops.capture import BASELINE_DAILY, RECIPES, build_capture_list, staff_one_pager
from brandops.engine import distribution_plan, group_by_event, run_today
from brandops.mix import ATHLETICS_CAP, analyze, is_athletics, weighted_sequence
from brandops.packages import build_package
from brandops.platforms import Platform
from brandops.triage import triage


# -- liturgical calendar ----------------------------------------------------

@pytest.mark.parametrize(
    "year,expected",
    [(2025, date(2025, 4, 20)), (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28))],
)
def test_easter_computus(year, expected):
    assert easter(year) == expected


def test_ash_wednesday_is_forty_six_days_before_easter():
    anchors = {e.name: e.when for e in liturgical_anchors(2026)}
    assert anchors["Ash Wednesday"] == date(2026, 2, 18)
    assert easter(2026) - anchors["Ash Wednesday"] == timedelta(days=46)


def test_liturgical_dates_are_marked_verified():
    assert all(e.verified for e in liturgical_anchors(2026))


def test_school_anchors_are_marked_unverified_until_someone_checks_them():
    template = [e for e in default_calendar(2026) if e.kind in ("school", "admissions", "academic")]
    assert template and all(not e.verified for e in template)


def test_nth_weekday_finds_labor_day():
    assert nth_weekday(2026, 9, 0, 1) == date(2026, 9, 7)


def test_funnel_phase_covers_the_whole_year():
    day = date(2026, 1, 1)
    while day < date(2027, 1, 1):
        phase, objective = funnel_phase(day)
        assert phase and objective
        day += timedelta(days=1)


def test_funnel_phase_wraps_the_new_year():
    assert funnel_phase(date(2026, 12, 20))[0] == "application"
    assert funnel_phase(date(2027, 1, 20))[0] == "application"


# -- mix --------------------------------------------------------------------

def test_athletics_over_the_cap_raises_a_warning():
    records = [{"pillar": "belonging_and_community", "audience": "grade_8",
                "platform": "tiktok", "text": "varsity football game"} for _ in range(8)]
    report = analyze(records)
    assert report.athletics_share > ATHLETICS_CAP
    assert any("athletics" in w for w in report.warnings)


def test_mix_names_the_neglected_pillars():
    records = [{"pillar": "belonging_and_community", "audience": "grade_8",
                "platform": "tiktok", "text": "lunch"} for _ in range(10)]
    deficits = analyze(records).pillar_deficits()
    assert Pillar.CHALLENGED in deficits or Pillar.KNOWN in deficits


def test_empty_window_says_so_rather_than_dividing_by_zero():
    report = analyze([])
    assert report.total == 0
    assert report.warnings


def test_is_athletics_does_not_fire_on_a_chemistry_lab():
    assert not is_athletics("AP Chemistry lab titration")
    assert is_athletics("varsity hockey game")


def test_weighted_sequence_length_and_deficit_priority():
    sequence = weighted_sequence(10, deficits=[Pillar.CATHOLIC])
    assert len(sequence) == 10
    assert sequence[0] is Pillar.CATHOLIC


def test_weighted_sequence_handles_zero():
    assert weighted_sequence(0) == []


# -- week plan --------------------------------------------------------------

def test_week_plan_holds_thirty_percent_open(today):
    slots = week_plan(today)
    planned = [s for s in slots if s.kind == PLANNED]
    held = [s for s in slots if s.kind == OPPORTUNISTIC]
    assert len(planned) == round(config.WEEKLY_POST_TARGET * config.PLANNED_SHARE)
    assert len(held) == config.WEEKLY_POST_TARGET - len(planned)
    assert all(s.open for s in held)


def test_week_plan_spans_seven_days(today):
    slots = week_plan(today)
    days = {s.when for s in slots}
    assert min(days) >= today and max(days) <= today + timedelta(days=6)


def test_planned_slots_name_a_pillar_before_anyone_shoots(today):
    for slot in week_plan(today):
        if slot.kind == PLANNED:
            assert slot.pillar is not None and slot.audience is not None


def test_linkedin_never_carries_student_life():
    assert align_pillar(Platform.LINKEDIN, Pillar.BELONGING) is Pillar.OUTCOMES
    assert align_pillar(Platform.FACEBOOK, Pillar.BELONGING) is Pillar.BELONGING


def test_aligned_audience_is_served_by_both_pillar_and_platform():
    audience = align_audience(Platform.TIKTOK, Pillar.BELONGING)
    assert audience in Platform.TIKTOK.spec.primary_audiences


def test_thirty_day_plan_returns_four_weeks(today):
    weeks = thirty_day_plan(today, default_calendar(2026))
    assert len(weeks) == 4
    assert weeks[1].start == today + timedelta(days=7)


def test_ninety_day_campaigns_are_contiguous(today):
    campaigns = ninety_day_campaigns(today)
    assert len(campaigns) == 3
    for earlier, later in zip(campaigns, campaigns[1:]):
        assert later.start == earlier.end + timedelta(days=1)


def test_paid_campaigns_declare_their_measurement(today):
    for campaign in ninety_day_campaigns(today):
        assert campaign.measurement


# -- capture ----------------------------------------------------------------

def test_capture_list_covers_calendar_events_first(today):
    events = events_between(default_calendar(2026), date(2026, 8, 26), date(2026, 8, 26))
    assignments = build_capture_list(date(2026, 8, 26), events=events)
    assert assignments[0].priority == 1
    assert "calendar" in assignments[0].reason


def test_capture_list_fills_pillar_deficits(today):
    assignments = build_capture_list(today, pillar_deficits=[Pillar.KNOWN])
    reasons = " ".join(a.reason for a in assignments)
    assert "Known & Safe" in reasons


def test_baseline_capture_always_present(today):
    assignments = build_capture_list(today)
    assert any(a.shots == BASELINE_DAILY for a in assignments)


def test_every_recipe_has_concrete_shots():
    for key, recipe in RECIPES.items():
        assert recipe.shots, f"{key} has no shot list"
        assert recipe.minutes <= 15, f"{key} asks for too much of a teacher's day"


def test_mass_recipe_carries_the_hard_rule():
    assert "consecration" in RECIPES["mass"].note.lower()


def test_one_pager_tells_staff_not_to_do_marketing_chores():
    text = staff_one_pager().lower()
    assert "do not rename files" in text


# -- engine -----------------------------------------------------------------

def test_run_today_produces_a_priority_story(lab_video, today):
    brief = run_today(today, assets=[lab_video])
    assert brief.priority is not None
    assert brief.priority.pillar is Pillar.CHALLENGED
    assert len(brief.priority.hooks) >= 3


def test_daily_brief_has_all_twelve_operating_sections(lab_video, today):
    text = run_today(today, assets=[lab_video]).as_text()
    for heading in ("PRIORITY STORY", "AUDIENCE:", "BRAND PILLAR:", "HOOKS", "CAPTURE PLAN",
                    "CONTENT PACKAGE", "COPY", "PRODUCTION", "DISTRIBUTION", "CTA:",
                    "PAID POTENTIAL:", "FOLLOW-UP"):
        assert heading in text, f"missing section: {heading}"


def test_daily_brief_has_the_morning_ideation_sections(lab_video, today):
    text = run_today(today, assets=[lab_video]).as_text()
    for heading in ("TODAY", "THIS WEEK", "MISSING", "CAPTURE REQUEST"):
        assert heading in text


def test_brief_reports_the_mix_gap(lab_video, today):
    published = [{"pillar": "belonging_and_community", "audience": "grade_8",
                  "platform": "tiktok", "text": "varsity game"} for _ in range(8)]
    brief = run_today(today, assets=[lab_video], published=published)
    assert any("athletics" in m for m in brief.missing)


def test_empty_inbox_produces_a_brief_without_a_priority(today):
    brief = run_today(today)
    assert brief.priority is None
    assert brief.capture_request, "an empty inbox still gets a capture request"


def test_group_by_event_keeps_same_event_together(lab_video, mass_photo):
    groups = group_by_event([lab_video, mass_photo, lab_video])
    assert len(groups) == 2


def test_distribution_sequences_story_first_then_the_slower_surfaces(lab_video, today):
    package = build_package(triage(lab_video, today=today), [lab_video])
    plan = distribution_plan(package, today)
    platforms = [step["platform"] for step in plan]
    assert platforms, "nothing scheduled"
    assert platforms.index("instagram_story") < platforms.index("facebook")
    assert plan[0]["when"] == today.isoformat()
