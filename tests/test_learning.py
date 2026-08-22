"""Measurement, brand memory, storage, cost discipline and the CLI."""

from __future__ import annotations

import json
from datetime import date

import pytest

from brandops import store
from brandops.audiences import Audience
from brandops.brand import Pillar
from brandops.cli import main
from brandops.llm import Claude, caption_prompt, hook_prompt, ideation_prompt
from brandops.measurement import (
    MIN_PLATFORM_SAMPLE,
    VANITY,
    Benchmarks,
    PostResult,
    performance_index,
    weekly_report,
)
from brandops.memory import BrandMemory, PerfStat, learn_from_week
from brandops.platforms import Platform
from brandops.stack import STACK, annual_cost, cost_per_hour_saved, essential, table


def make_result(post_id: str, *, boost: float = 1.0, platform: str = "instagram_reel",
                pillar: Pillar = Pillar.KNOWN, hook: str = "parent_concern",
                when: date = date(2026, 8, 24), inquiries: float = 0.0) -> PostResult:
    return PostResult(
        post_id=post_id,
        platform=platform,
        published_at=when,
        pillar=pillar,
        audience=Audience.PROSPECTIVE_PARENT,
        metrics={
            "impressions": 2000,
            "three_second_views": 600 * boost,
            "completions": 300 * boost,
            "shares": 20 * boost,
            "link_clicks": 30 * boost,
            "inquiries": inquiries,
        },
        hook_structure=hook,
        fmt="vertical video",
        event=f"event for {post_id}",
    )


# -- metrics ----------------------------------------------------------------

def test_rates_are_derived_not_stored():
    result = make_result("p1")
    assert result.hook_rate == pytest.approx(0.30)
    assert result.completion_rate == pytest.approx(0.15)


def test_missing_denominators_do_not_raise():
    result = PostResult("p", "tiktok", date(2026, 8, 24), Pillar.KNOWN,
                        Audience.GRADE_8, metrics={"shares": 4})
    assert result.hook_rate is None
    assert result.rates() == {}


def test_admissions_actions_sum_downstream_behavior():
    result = PostResult("p", "facebook", date(2026, 8, 24), Pillar.OUTCOMES,
                        Audience.PROSPECTIVE_PARENT,
                        metrics={"inquiries": 2, "applications_started": 1})
    assert result.admissions_actions == 3


def test_thin_platform_samples_fall_back_to_the_overall_median():
    # Three posts on one platform would otherwise make every post exactly average.
    results = [make_result(f"p{i}", boost=1 + i) for i in range(3)]
    benchmarks = Benchmarks.from_results(results)
    assert benchmarks.platform_counts["instagram_reel"]["hook_rate"] < MIN_PLATFORM_SAMPLE
    indices = [performance_index(r, benchmarks) for r in results]
    assert len(set(round(i, 3) for i in indices)) > 1


def test_performance_index_needs_two_metrics():
    thin = PostResult("p", "tiktok", date(2026, 8, 24), Pillar.KNOWN, Audience.GRADE_8,
                      metrics={"impressions": 100, "shares": 1})
    assert performance_index(thin, Benchmarks.from_results([thin])) is None


# -- weekly report ----------------------------------------------------------

def test_weekly_report_separates_evidence_from_inference():
    results = [make_result(f"p{i}", boost=2.5 if i == 0 else 1.0) for i in range(5)]
    results.append(make_result("weak", boost=0.2, pillar=Pillar.BELONGING))
    report = weekly_report(results, start=date(2026, 8, 18), end=date(2026, 8, 24))
    assert report.evidence, "no observed evidence recorded"
    # Evidence must be numeric observation; inference must be labeled as unproven.
    assert any("x our median" in e for e in report.evidence)
    text = report.as_text()
    assert "OBSERVED EVIDENCE" in text and "STRATEGIC INFERENCE" in text


def test_small_samples_are_called_out_rather_than_acted_on():
    results = [make_result("p0", boost=3.0), make_result("p1", boost=0.3)]
    report = weekly_report(results, start=date(2026, 8, 18), end=date(2026, 8, 24))
    assert any("too small to act on" in i for i in report.inference)


def test_empty_week_reports_the_gap_instead_of_crashing():
    report = weekly_report([], start=date(2026, 8, 18), end=date(2026, 8, 24))
    assert report.total_posts == 0
    assert report.next_week


def test_no_attribution_prompts_a_measurement_fix():
    results = [make_result(f"p{i}") for i in range(4)]
    report = weekly_report(results, start=date(2026, 8, 18), end=date(2026, 8, 24))
    assert any("UTM" in n for n in report.next_week)


def test_vanity_metrics_are_recorded_but_named_as_such():
    results = [make_result(f"p{i}") for i in range(3)]
    results[0].metrics["reactions"] = 400
    report = weekly_report(results, start=date(2026, 8, 18), end=date(2026, 8, 24))
    assert any("not used to judge" in e for e in report.evidence)
    assert "reactions" in VANITY


def test_underperforming_pillar_becomes_a_capture_assignment():
    results = [make_result(f"p{i}", boost=2.0) for i in range(3)]
    results += [make_result(f"w{i}", boost=0.2, pillar=Pillar.CATHOLIC) for i in range(2)]
    report = weekly_report(results, start=date(2026, 8, 18), end=date(2026, 8, 24))
    assert report.capture_assignments


# -- memory -----------------------------------------------------------------

def test_perfstat_running_mean():
    stat = PerfStat()
    stat.record(2.0, "a")
    stat.record(1.0, "b")
    assert stat.mean == pytest.approx(1.5)
    assert stat.n == 2
    assert stat.best_ref == "a"


def test_memory_needs_three_observations_before_it_is_confident():
    stat = PerfStat()
    for _ in range(2):
        stat.record(1.0)
    assert not stat.confident
    stat.record(1.0)
    assert stat.confident


def test_memory_learns_from_a_week_and_recommends():
    # A spread of results, so the median sits between the winners and the rest.
    results = [make_result(f"mid{i}", boost=1.0, hook="what_it_looks_like") for i in range(4)]
    results += [make_result(f"win{i}", boost=3.0, hook="parent_concern") for i in range(3)]
    results += [make_result(f"lose{i}", boost=0.2, hook="student_question") for i in range(3)]
    report = weekly_report(results, start=date(2026, 8, 18), end=date(2026, 8, 24))
    assert report.winners, "test data produced no winners to learn from"
    memory = learn_from_week(BrandMemory(), report)
    notes = memory.recommend(Pillar.KNOWN, Audience.PROSPECTIVE_PARENT)
    assert any("parent_concern" in n for n in notes)


def test_seeded_objections_are_never_mistaken_for_measured_history():
    # A pillar with a seeded objection but no results must still say it has no history.
    notes = BrandMemory().recommend(Pillar.OUTCOMES, Audience.PROSPECTIVE_PARENT)
    assert any("no confident performance history" in n for n in notes)
    assert any("this pillar answers" in n for n in notes)


def test_memory_starts_with_an_objection_library():
    memory = BrandMemory()
    assert memory.objections_for(Pillar.OUTCOMES)
    assert all("evidence_needed" in o for o in memory.objections)


def test_unverified_statistics_are_not_returned_as_verified():
    memory = BrandMemory()
    memory.bank_statistic("Every senior was accepted somewhere", source="counseling office")
    assert memory.statistics and memory.verified_statistics() == []


def test_memory_round_trips_and_persists():
    memory = BrandMemory()
    memory.record_result(make_result("p0", boost=2.0), 1.8)
    memory.bank_quote("If you are off by a drop you start over.", who="Marcus, 11",
                      pillar=Pillar.CHALLENGED)
    memory.save()
    reloaded = BrandMemory.load()
    assert reloaded.to_dict() == memory.to_dict()
    assert reloaded.testimonials[0]["who"] == "Marcus, 11"


def test_cold_start_recommendation_is_honest_about_having_no_history():
    notes = BrandMemory().recommend(Pillar.BELONGING, Audience.GRADE_8)
    assert any("baseline" in n for n in notes)


def test_one_measured_post_is_not_yet_confident():
    memory = BrandMemory()
    memory.record_result(make_result("p0", boost=2.0), 1.8)
    notes = memory.recommend(Pillar.KNOWN, Audience.PROSPECTIVE_PARENT)
    assert any("no confident performance history" in n for n in notes)


# -- store ------------------------------------------------------------------

def test_store_round_trip_and_atomic_write(isolated_store):
    store.save("assets", {"assets": [{"a": 1}]})
    assert store.load("assets")["assets"] == [{"a": 1}]
    assert not list(isolated_store.glob("*.tmp")), "temp file left behind"


def test_missing_collection_returns_the_default():
    assert store.load("nothing_here", {"x": []}) == {"x": []}


# -- stack ------------------------------------------------------------------

def test_stack_table_has_the_required_columns():
    header = table().splitlines()[0]
    for column in ("Tool", "Purpose", "Monthly Cost", "Existing Alternative",
                   "Labor Saved", "Essential"):
        assert column in header


def test_media_budget_is_excluded_from_software_cost():
    assert annual_cost() < 5000, "media spend leaked into the software figure"


def test_every_tool_declares_an_existing_alternative():
    assert all(tool.existing_alternative for tool in STACK)


def test_essential_stack_is_cheap_per_hour_saved():
    assert cost_per_hour_saved() < 25
    assert any("Microsoft 365" in t.name for t in essential())


# -- llm --------------------------------------------------------------------

def test_prompts_carry_the_brand_rules():
    prompt = caption_prompt(story="AP Chemistry lab", pillar=Pillar.CHALLENGED,
                            audience=Audience.PROSPECTIVE_PARENT,
                            platform=Platform.FACEBOOK)
    assert "Never invent a fact" in prompt.system
    assert "academic excellence" in prompt.system
    assert "Facebook" in prompt.user


def test_hook_prompt_demands_the_footage_justify_the_hook():
    prompt = hook_prompt(story="Signing day", pillar=Pillar.OUTCOMES,
                         audience=Audience.PROSPECTIVE_PARENT)
    assert "honest" in prompt.user


def test_ideation_prompt_asks_for_the_four_sections():
    prompt = ideation_prompt(when="2026-08-24", yesterday=[], today=["Mass"],
                             this_week=[], deficits=["Outcomes"], phase="awareness")
    for section in ("TODAY", "THIS WEEK", "MISSING", "CAPTURE REQUEST"):
        assert section in prompt.user


def test_offline_claude_hands_back_a_pasteable_prompt(monkeypatch):
    claude = Claude()
    if claude.available:  # a key is configured in this environment
        pytest.skip("Anthropic credentials are present; offline path not exercised")
    prompt = hook_prompt(story="Mass", pillar=Pillar.CATHOLIC,
                         audience=Audience.CURRENT_PARENT)
    with pytest.raises(RuntimeError) as exc:
        claude.complete(prompt)
    assert "## Task" in str(exc.value)


# -- cli --------------------------------------------------------------------

def test_cli_intake_triage_and_queue_round_trip(capsys):
    assert main([
        "intake", "--event", "AP Chemistry lab", "--department", "Science",
        "--contributor", "Mr. Kowalski", "--description", "candid: students titrating",
        "--file", "a.mov", "--duration", "14", "--date", "2026-08-24",
    ]) == 0
    assert main(["triage", "--date", "2026-08-24"]) == 0
    assert "LEAD" in capsys.readouterr().out

    assert main(["queue", "build", "AP Chemistry lab"]) == 0
    assert main(["queue", "list"]) == 0
    out = capsys.readouterr().out
    assert "APPROVE / EDIT / REJECT / HOLD" in out


def test_cli_refuses_to_approve_without_a_named_human(capsys):
    main(["intake", "--event", "Lunch", "--department", "Student Life",
          "--contributor", "R", "--description", "lunch table", "--date", "2026-08-24"])
    main(["queue", "build", "Lunch"])
    capsys.readouterr()
    card_id = json.loads(store.path_for("queue").read_text())["cards"][0]["card_id"]
    assert main(["queue", "approve", card_id]) == 1
    assert "--by is required" in capsys.readouterr().err


def test_cli_today_runs_on_an_empty_inbox(capsys):
    assert main(["today", "--date", "2026-08-24"]) == 0
    assert "CONTENT ENGINE" in capsys.readouterr().out


def test_cli_json_output_is_parseable(capsys):
    main(["intake", "--event", "Mass", "--department", "Campus Ministry",
          "--contributor", "Fr. N", "--description", "students singing",
          "--date", "2026-08-24"])
    capsys.readouterr()
    assert main(["--json", "triage", "--date", "2026-08-24"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["primary_pillar"] == "catholic_identity"


def test_cli_lint_exits_nonzero_on_filler(capsys):
    assert main(["lint", "Our academic excellence speaks for itself"]) == 1
    assert "academic excellence" in capsys.readouterr().out


def test_cli_weekly_requires_recorded_results(capsys):
    assert main(["weekly", "--date", "2026-08-27"]) == 1
    assert "no results recorded" in capsys.readouterr().err


def test_cli_record_then_weekly_and_learn(capsys):
    for index, boost in enumerate((1, 2, 3)):
        main([
            "record", f"p{index}", "--platform", "instagram_reel",
            "--pillar", "known_and_safe", "--audience", "prospective_parent",
            "--date", "2026-08-24", "--hook", "parent_concern",
            "--format", "vertical video",
            "--metric", "impressions=2000",
            "--metric", f"three_second_views={300 * boost}",
            "--metric", f"shares={5 * boost}",
            "--metric", f"link_clicks={7 * boost}",
        ])
    capsys.readouterr()
    assert main(["weekly", "--date", "2026-08-27", "--learn"]) == 0
    assert "WEEKLY INTELLIGENCE REPORT" in capsys.readouterr().out
    assert main(["memory"]) == 0
    assert "parent_concern" in capsys.readouterr().out


def test_cli_reference_commands_run(capsys):
    for argv in (["stack"], ["rubric"], ["onepager"], ["capture", "--date", "2026-08-24"],
                 ["plan", "week", "--date", "2026-08-24"], ["plan", "30", "--date", "2026-08-24"],
                 ["plan", "90", "--date", "2026-08-24"],
                 ["prompt", "hooks", "--story", "AP Chemistry lab"]):
        assert main(argv) == 0, argv
        assert capsys.readouterr().out.strip(), argv
