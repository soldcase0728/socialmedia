"""The unattended morning and Friday jobs.

Designed to run from cron or Windows Task Scheduler on the machine where the
content inbox is synced -- that is the only place with the actual assets, so it
is the only place the full brief (triage, hooks, copy) can be produced.

Each run writes dated files plus a stable `*-latest.md`, so a Power Automate
flow can watch one filename and post it to Teams. Failures are written to the
same folder and re-raised, so a silent job cannot look like a successful one.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from . import config, store
from .calendar import default_calendar
from .capture import build_capture_list
from .engine import run_today
from .measurement import weekly_report
from .memory import BrandMemory, learn_from_week
from .mix import analyze
from .state import load_assets, load_published, load_results

BRIEF_STEM = "brief"
CAPTURE_STEM = "capture"
WEEKLY_STEM = "weekly"
ERROR_STEM = "ERROR"


def output_dir() -> Path:
    """Where the job writes. Defaults to `briefs/` beside the data directory."""
    import os

    configured = os.environ.get("BRANDOPS_OUT")
    if configured:
        return Path(configured)
    return store.data_dir().parent / "briefs"


def school_year_for(when: date) -> int:
    """The fall year whose calendar covers this date."""
    return when.year if when.month >= 8 else when.year - 1


@dataclass
class RunResult:
    when: date
    written: list[Path]
    headline: str
    ok: bool = True

    def summary(self) -> str:
        files = "\n".join(f"  {p}" for p in self.written)
        return f"{self.when.isoformat()}: {self.headline}\n{files}"


def _write(directory: Path, stem: str, when: date, body: str) -> list[Path]:
    """Write the dated file and refresh the stable `-latest` copy."""
    directory.mkdir(parents=True, exist_ok=True)
    dated = directory / f"{stem}-{when.isoformat()}.md"
    latest = directory / f"{stem}-latest.md"
    dated.write_text(body, encoding="utf-8")
    latest.write_text(body, encoding="utf-8")
    return [dated, latest]


def _fence(title: str, when: date, body: str) -> str:
    return f"# {title}\n\n_Generated {when.isoformat()}_\n\n```\n{body}\n```\n"


def run_daily(when: date | None = None, *, directory: Path | None = None) -> RunResult:
    """The morning job: the full brief, plus the capture list as its own file.

    The capture list is separated deliberately -- it is the half that gets
    forwarded to teachers, and nobody forwards a document with draft ad copy in it.
    """
    when = when or date.today()
    directory = directory or output_dir()

    brief = run_today(
        when,
        assets=load_assets(),
        events=default_calendar(school_year_for(when)),
        published=load_published(),
        memory=BrandMemory.load(),
    )
    written = _write(directory, BRIEF_STEM, when, _fence("Content Engine Brief", when, brief.as_text()))

    capture_text = "\n\n".join(a.as_text() for a in brief.capture_request)
    written += _write(
        directory,
        CAPTURE_STEM,
        when,
        _fence(f"Capture List -- {when:%A, %B %d}", when, capture_text),
    )

    if brief.priority:
        headline = f"{len(brief.today)} opportunity(ies); lead story: {brief.today[0].event}"
    else:
        headline = "nothing in the inbox scores high enough to publish -- capture list only"
    if brief.inbox_unresolved:
        headline += f" | {brief.inbox_unresolved} asset(s) still unresolved"
    return RunResult(when=when, written=written, headline=headline)


def run_weekly(
    when: date | None = None,
    *,
    directory: Path | None = None,
    learn: bool = True,
) -> RunResult:
    """The Friday job: the intelligence report, folded into brand memory."""
    when = when or date.today()
    directory = directory or output_dir()
    start = when - timedelta(days=6)

    results = load_results()
    if not results:
        body = (
            "No results have been recorded yet.\n\n"
            "The weekly report is only as good as `brandops record`. Until published\n"
            "posts are recorded with their metrics, every recommendation this system\n"
            "makes is a guess wearing a number."
        )
        written = _write(directory, WEEKLY_STEM, when, _fence("Weekly Intelligence Report", when, body))
        return RunResult(when=when, written=written, headline="no results recorded this week", ok=True)

    report = weekly_report(results, start=start, end=when, history=results)
    body = report.as_text()

    published = load_published()
    if published:
        body += "\n\n" + analyze(published).as_text()

    if learn:
        memory = BrandMemory.load()
        learn_from_week(memory, report)
        memory.save()
        body += "\n\n(Results folded into brand memory.)"

    written = _write(directory, WEEKLY_STEM, when, _fence("Weekly Intelligence Report", when, body))
    return RunResult(
        when=when,
        written=written,
        headline=f"{report.total_posts} post(s), {len(report.winners)} winner(s), "
                 f"{report.admissions_actions:.0f} admissions action(s)",
    )


def run_safely(job, when: date | None = None, *, directory: Path | None = None) -> RunResult:
    """Run a job, writing the traceback where a human will see it if it fails.

    A scheduled job that fails quietly is worse than no scheduled job: the
    marketing office keeps believing a brief was produced.
    """
    when = when or date.today()
    directory = directory or output_dir()
    try:
        return job(when, directory=directory)
    except Exception:
        body = (
            "The scheduled job failed. Nothing was produced for today.\n\n"
            + traceback.format_exc()
        )
        written = _write(directory, ERROR_STEM, when, _fence("Job Failed", when, body))
        return RunResult(when=when, written=written, headline="JOB FAILED -- see the traceback", ok=False)
