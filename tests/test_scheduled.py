"""The unattended morning and Friday jobs."""

from __future__ import annotations

import os
from datetime import date

import pytest

from brandops.assets import from_intake
from brandops.audiences import Audience
from brandops.brand import Pillar
from brandops.measurement import PostResult
from brandops.memory import BrandMemory
from brandops.scheduled import (
    output_dir,
    run_daily,
    run_safely,
    run_weekly,
    school_year_for,
)
from brandops.state import append_published, append_result, save_assets


@pytest.fixture
def out_dir(tmp_path):
    return tmp_path / "briefs"


def test_school_year_straddles_the_calendar_year():
    assert school_year_for(date(2026, 9, 15)) == 2026
    assert school_year_for(date(2027, 2, 15)) == 2026
    assert school_year_for(date(2026, 8, 1)) == 2026


def test_output_dir_honors_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("BRANDOPS_OUT", str(tmp_path / "elsewhere"))
    assert output_dir() == tmp_path / "elsewhere"


def test_output_dir_defaults_beside_the_data_folder(monkeypatch, tmp_path):
    monkeypatch.delenv("BRANDOPS_OUT", raising=False)
    monkeypatch.setenv("BRANDOPS_DATA", str(tmp_path / "state" / "data"))
    assert output_dir() == tmp_path / "state" / "briefs"


def test_daily_job_writes_dated_and_latest_copies(out_dir, lab_video):
    save_assets([lab_video])
    result = run_daily(date(2026, 8, 24), directory=out_dir)

    assert result.ok
    names = {p.name for p in result.written}
    assert names == {
        "brief-2026-08-24.md", "brief-latest.md",
        "capture-2026-08-24.md", "capture-latest.md",
    }
    dated = out_dir / "brief-2026-08-24.md"
    assert dated.read_text() == (out_dir / "brief-latest.md").read_text()
    assert "AP Chemistry lab" in dated.read_text()


def test_capture_file_is_safe_to_forward_to_teachers(out_dir, lab_video):
    # Staff get the shot list. They must not get draft ad copy or paid-media notes.
    save_assets([lab_video])
    run_daily(date(2026, 8, 24), directory=out_dir)
    capture = (out_dir / "capture-latest.md").read_text()

    assert "vertical clips" in capture
    assert "PRIORITY STORY" not in capture
    assert "PAID POTENTIAL" not in capture
    assert "#" not in capture.split("```")[1]  # no hashtags inside the body


def test_daily_headline_reports_the_lead_story(out_dir, lab_video):
    save_assets([lab_video])
    result = run_daily(date(2026, 8, 24), directory=out_dir)
    assert "AP Chemistry lab" in result.headline


def test_daily_job_runs_on_an_empty_inbox(out_dir):
    result = run_daily(date(2026, 8, 24), directory=out_dir)
    assert result.ok
    assert "capture list only" in result.headline
    assert (out_dir / "capture-latest.md").exists()


def test_daily_headline_counts_unresolved_assets(out_dir, lab_video, mass_photo):
    save_assets([lab_video, mass_photo])
    result = run_daily(date(2026, 8, 24), directory=out_dir)
    assert "2 asset(s) still unresolved" in result.headline


def test_weekly_job_with_no_results_says_what_to_do(out_dir):
    result = run_weekly(date(2026, 8, 28), directory=out_dir)
    assert result.ok
    body = (out_dir / "weekly-latest.md").read_text()
    assert "brandops record" in body
    assert "guess wearing a number" in body


def _record(post_id: str, boost: float) -> PostResult:
    result = PostResult(
        post_id=post_id,
        platform="instagram_reel",
        published_at=date(2026, 8, 26),
        pillar=Pillar.KNOWN,
        audience=Audience.PROSPECTIVE_PARENT,
        metrics={
            "impressions": 2000,
            "three_second_views": 400 * boost,
            "completions": 200 * boost,
            "shares": 10 * boost,
            "link_clicks": 15 * boost,
        },
        hook_structure="parent_concern",
        fmt="vertical video",
        event=f"event {post_id}",
    )
    append_result(result)
    append_published({
        "post_id": post_id, "pillar": result.pillar.value,
        "audience": result.audience.value, "platform": result.platform,
        "event": result.event,
    })
    return result


def test_weekly_job_reports_and_folds_into_memory(out_dir):
    for index, boost in enumerate((1.0, 1.0, 1.0, 3.0, 0.2)):
        _record(f"p{index}", boost)

    result = run_weekly(date(2026, 8, 28), directory=out_dir, learn=True)
    body = (out_dir / "weekly-latest.md").read_text()

    assert result.ok
    assert "WEEKLY INTELLIGENCE REPORT" in body
    assert "OBSERVED EVIDENCE" in body and "STRATEGIC INFERENCE" in body
    assert "Mix over the last" in body, "published mix should be appended"
    assert "folded into brand memory" in body
    assert BrandMemory.load().hooks, "memory was not updated"


def test_weekly_job_can_skip_learning(out_dir):
    _record("p0", 2.0)
    run_weekly(date(2026, 8, 28), directory=out_dir, learn=False)
    assert BrandMemory.load().hooks == {}


def test_a_failing_job_is_loud_not_silent(out_dir):
    def boom(when, directory=None):
        raise ValueError("simulated failure")

    result = run_safely(boom, date(2026, 8, 24), directory=out_dir)

    assert not result.ok
    assert "JOB FAILED" in result.headline
    body = (out_dir / "ERROR-2026-08-24.md").read_text()
    assert "simulated failure" in body
    assert "Traceback" in body


def test_run_safely_passes_through_a_successful_job(out_dir, lab_video):
    save_assets([lab_video])
    result = run_safely(run_daily, date(2026, 8, 24), directory=out_dir)
    assert result.ok
    assert not (out_dir / "ERROR-2026-08-24.md").exists()


def test_cli_run_daily_exit_codes(capsys, tmp_path):
    from brandops.cli import main

    assert main(["run-daily", "--date", "2026-08-24", "--out", str(tmp_path / "b")]) == 0
    assert "brief-2026-08-24.md" in capsys.readouterr().out


def test_cli_run_weekly_exit_codes(capsys, tmp_path):
    from brandops.cli import main

    assert main(["run-weekly", "--date", "2026-08-28", "--out", str(tmp_path / "b")]) == 0
    assert "weekly-2026-08-28.md" in capsys.readouterr().out
