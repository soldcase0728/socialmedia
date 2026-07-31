"""Command-line interface.

Every phase is a subcommand.  Phases are gated: Phase 2 and Phase 3 refuse to
run until the preceding phase has completed, and the full Phase 2 run refuses
to start until a pilot has been run, so the workflow cannot skip its own
checkpoints by accident.

Run ``python -m src.cli --help`` (or ``wri --help`` once installed) for usage.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .config import Config, ConfigError, summarize_candidates
from .database import Database, open_database
from .inventory import ReadOnlySourceError, find_source_folders, run_phase1
from .logging_setup import get_logger, setup_logging
from .version import APP_NAME, APP_VERSION

log = get_logger("cli")

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NEEDS_INPUT = 2


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser."""
    parser = argparse.ArgumentParser(
        prog="wri",
        description=(
            f"{APP_NAME} {APP_VERSION} -- local, read-only derived indexing for "
            "a Bates-numbered document production. Produces DERIVED review "
            "metadata only; never native metadata."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", type=Path, default=None,
                        help="Path to config.yaml (default: project config.yaml)")
    parser.add_argument("--source", type=Path, default=None,
                        help="Override the read-only source folder")
    parser.add_argument("--output", type=Path, default=None,
                        help="Override the derived-index output folder")
    parser.add_argument("--workers", type=int, default=None,
                        help="Override the worker count")
    parser.add_argument("--no-progress", action="store_true",
                        help="Disable progress bars (useful for logs)")
    parser.add_argument("--quiet", action="store_true",
                        help="Console logging at WARNING and above")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "locate", help="Search likely locations for the source folder"
    )

    doctor = subparsers.add_parser(
        "doctor", help="Check dependencies, paths and permissions"
    )
    doctor.add_argument("--check-ocr", action="store_true",
                        help="Also check for a local OCR engine")

    phase1 = subparsers.add_parser(
        "phase1", help="Phase 1: structural inventory (no content is read)"
    )
    phase1.add_argument("--force", action="store_true",
                        help="Re-probe every file even if unchanged")
    phase1.add_argument("--limit", type=int, default=None,
                        help="Process at most N new files (smoke test)")
    phase1.add_argument("--no-reports", action="store_true",
                        help="Update the database without writing workbooks")

    phase2 = subparsers.add_parser(
        "phase2", help="Phase 2: text extraction and page-condition audit"
    )
    phase2.add_argument("--pilot", action="store_true",
                        help="Process only the stratified pilot sample")
    phase2.add_argument("--full", action="store_true",
                        help="Process the whole production (requires a pilot "
                             "to have been run first)")
    phase2.add_argument("--force", action="store_true",
                        help="Re-extract documents already processed")
    phase2.add_argument("--ocr", dest="ocr", action="store_true", default=None,
                        help="Enable OCR for this run")
    phase2.add_argument("--no-ocr", dest="ocr", action="store_false",
                        help="Disable OCR for this run")
    phase2.add_argument("--no-reports", action="store_true",
                        help="Update the database without writing workbooks")

    phase3 = subparsers.add_parser(
        "phase3", help="Phase 3: derived review metadata and review queues"
    )
    phase3.add_argument("--force", action="store_true",
                        help="Re-derive metadata for documents already done")
    phase3.add_argument("--no-reports", action="store_true",
                        help="Update the database without writing workbooks")

    reports = subparsers.add_parser(
        "reports", help="Regenerate reports from the existing database"
    )
    reports.add_argument("--phase", choices=["1", "2", "3", "all"], default="all",
                         help="Which phase's reports to regenerate")

    subparsers.add_parser(
        "qc-sample", help="Generate the human quality-control sample workbook"
    )

    retry = subparsers.add_parser(
        "retry-failed", help="Re-attempt only the files that previously failed"
    )
    retry.add_argument("--phase", choices=["1", "2", "3"], default="2",
                       help="Which phase to retry (default: 2)")

    status = subparsers.add_parser("status", help="Show processing state counts")
    status.add_argument("--verbose", action="store_true",
                        help="Include per-phase run statistics")

    search = subparsers.add_parser(
        "search", help="Search the local FTS5 index (returns locations, not text)"
    )
    search.add_argument("expression", help="FTS5 match expression")
    search.add_argument("--limit", type=int, default=50, help="Maximum hits")

    return parser


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------
class RunContext:
    """Resolved configuration, paths, logging and database for one invocation."""

    def __init__(self, args: argparse.Namespace) -> None:
        self.config = Config.load(args.config)
        self.source = self.config.resolve_source_folder(args.source)
        self.output = self.config.resolve_output_folder(self.source, args.output)
        self.output.mkdir(parents=True, exist_ok=True)

        logging_cfg = self.config.section("logging")
        log_dir = self.output / str(logging_cfg.get("logs_dirname", "logs"))
        setup_logging(
            log_dir,
            level=str(logging_cfg.get("level", "INFO")),
            console_level="WARNING" if args.quiet
            else str(logging_cfg.get("console_level", "INFO")),
            max_bytes=int(logging_cfg.get("max_bytes", 50 * 1024 * 1024)),
            backup_count=int(logging_cfg.get("backup_count", 10)),
        )
        self.database: Database = open_database(self.output)
        self.progress = not args.no_progress
        self.workers = args.workers

    def close(self) -> None:
        """Close the database connection."""
        self.database.close()

    def __enter__(self) -> "RunContext":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_locate(args: argparse.Namespace) -> int:
    """Search likely locations for the production folder."""
    setup_logging(None)
    config = Config.load(args.config)
    name = config.source_folder_name()
    roots = config.search_roots()
    if not roots:
        print(
            "None of the configured search roots exist on this machine.\n"
            "Configured roots:\n  "
            + "\n  ".join(str(r) for r in (config.get("paths", "search_roots") or []))
            + "\n\nIf this is not the Mac holding the Google Drive folder, run "
              "the tool there, or set paths.source_folder in config.yaml to the "
              "correct absolute path."
        )
        return EXIT_NEEDS_INPUT

    print(f"Searching for a folder named {name!r} under:")
    for root in roots:
        print(f"  {root}")
    candidates = find_source_folders(config)

    if not candidates:
        print(f"\nNo folder named {name!r} was found.")
        print("Check that Google Drive is running and the folder is synced, "
              "then set paths.source_folder in config.yaml manually.")
        return EXIT_NEEDS_INPUT

    print(f"\nFound {len(candidates)} matching folder(s):\n")
    print(summarize_candidates(candidates))
    if len(candidates) == 1:
        print(
            "\nTo use it, set this in config.yaml:\n"
            f"  paths:\n    source_folder: \"{candidates[0].path}\""
        )
    else:
        print(
            "\nMultiple folders matched. Choose one and set it in config.yaml "
            "under paths.source_folder, or pass --source on the command line. "
            "Nothing has been modified."
        )
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check the environment before a long run."""
    import shutil

    setup_logging(None)
    problems: List[str] = []
    print(f"{APP_NAME} {APP_VERSION} environment check\n")
    print(f"Python: {sys.version.split()[0]}")

    for module, label in (
        ("fitz", "PyMuPDF"), ("pypdf", "pypdf"), ("pandas", "pandas"),
        ("openpyxl", "openpyxl"), ("dateutil", "python-dateutil"),
        ("rapidfuzz", "rapidfuzz"), ("tqdm", "tqdm"), ("PIL", "Pillow"),
        ("yaml", "PyYAML"),
    ):
        try:
            __import__(module)
            print(f"  [ok]      {label}")
        except ImportError:
            print(f"  [MISSING] {label}")
            problems.append(f"{label} is not installed")

    import sqlite3

    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE t USING fts5(a)")
        print("  [ok]      SQLite FTS5 support")
    except sqlite3.OperationalError:
        print("  [MISSING] SQLite FTS5 support")
        problems.append("this Python's SQLite lacks FTS5; text search will fail")
    finally:
        connection.close()

    if args.check_ocr:
        for tool in ("ocrmypdf", "tesseract"):
            if shutil.which(tool):
                print(f"  [ok]      {tool}")
            else:
                print(f"  [absent]  {tool} (only needed if OCR is enabled)")

    try:
        config = Config.load(args.config)
        print(f"\nConfig: {config.config_path}  [valid]")
        source = config.resolve_source_folder(args.source)
        print(f"Source folder: {source}")
        readable = _check_readable(source)
        print(f"  readable: {'yes' if readable else 'NO'}")
        if not readable:
            problems.append("the source folder is not readable")
        output = config.resolve_output_folder(source, args.output)
        print(f"Output folder: {output}")
        output.mkdir(parents=True, exist_ok=True)
        probe = output / ".wri_write_test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            print("  writable: yes")
        except OSError as exc:
            print(f"  writable: NO ({exc})")
            problems.append("the output folder is not writable")
    except ConfigError as exc:
        print(f"\nConfiguration problem: {exc}")
        problems.append(str(exc))

    if problems:
        print("\nProblems found:")
        for problem in problems:
            print(f"  - {problem}")
        return EXIT_ERROR
    print("\nAll checks passed.")
    return EXIT_OK


def _check_readable(path: Path) -> bool:
    """Whether a directory can be listed."""
    try:
        next(iter(path.iterdir()), None)
        return True
    except OSError:
        return False


def cmd_phase1(args: argparse.Namespace) -> int:
    """Run the structural inventory."""
    from .phase1_reports import generate_phase1_reports

    with RunContext(args) as context:
        log.info("%s %s -- Phase 1 (structural inventory)", APP_NAME, APP_VERSION)
        log.info("Source (read-only): %s", context.source)
        log.info("Derived index:      %s", context.output)
        result = run_phase1(
            context.config, context.database, context.source,
            workers=context.workers, limit=args.limit, force=args.force,
            progress=context.progress,
        )
        if not args.no_reports:
            generate_phase1_reports(
                context.config, context.database, context.output, context.source
            )
        _print_phase1_summary(context, result)
    return EXIT_OK


def _print_phase1_summary(context: RunContext, result) -> None:
    """Print aggregate Phase 1 numbers (never file content)."""
    from .reports import format_bytes

    stats = context.database.get_stats("phase1")
    print("\n" + "=" * 66)
    print("PHASE 1 COMPLETE -- STRUCTURAL INVENTORY")
    print("=" * 66)
    print(f"  Files scanned this run       {result.scanned:,}")
    print(f"  Files processed              {result.processed:,}")
    print(f"  Skipped (already current)    {result.skipped_unchanged:,}")
    print(f"  Total files in index         {stats.get('total_files', 0):,}")
    print(f"  PDFs                         {stats.get('pdf_files', 0):,}")
    print(f"  Total size                   {format_bytes(stats.get('total_bytes', 0))}")
    print(f"  Bates range (filenames)      "
          f"{stats.get('bates_min')} .. {stats.get('bates_max')}")
    print(f"  Exact duplicate groups       {stats.get('exact_duplicate_groups', 0):,}")
    print(f"  Encrypted PDFs               {stats.get('encrypted_pdfs', 0):,}")
    print(f"  Corrupt / unreadable         {stats.get('corrupt_or_unreadable', 0):,}")
    print(f"  Cloud placeholders           {stats.get('cloud_placeholders', 0):,}")
    print(f"  Preliminary filename gaps    "
          f"{stats.get('preliminary_filename_gap_count', 0):,}")
    print("\n  Filename-based Bates gaps are PRELIMINARY. A multi-page PDF")
    print("  consumes Bates numbers that never appear in any filename.")
    print(f"\n  Reports: {context.output}")
    print("  Read Phase_1_Summary.md next.")
    print("\n  Phase 2 has NOT been run and will not start without approval.")
    print("=" * 66 + "\n")


def cmd_phase2(args: argparse.Namespace) -> int:
    """Run the text and page-condition audit."""
    from .phase2_reports import generate_phase2_reports
    from .pipeline import run_phase2, select_pilot_sample

    if not args.pilot and not args.full:
        print(
            "Specify --pilot or --full.\n\n"
            "  --pilot  process a stratified sample (~"
            f"{Config.load(args.config).get('pilot', 'target_size', default=200)}"
            " documents) so accuracy can be measured first\n"
            "  --full   process the entire production (only after a pilot)"
        )
        return EXIT_NEEDS_INPUT

    with RunContext(args) as context:
        if not _phase_complete(context.database, "phase1"):
            print("Phase 1 has not completed. Run `wri phase1` first.")
            return EXIT_ERROR

        sample_info = None
        file_ids: Optional[List[int]] = None
        if args.pilot:
            sample = select_pilot_sample(context.config, context.database)
            file_ids = sample.file_ids
            sample_info = {"strata": sample.strata, "shortfalls": sample.shortfalls}
            if not file_ids:
                print("The pilot sample is empty. Is Phase 1 complete?")
                return EXIT_ERROR
        elif not _pilot_has_run(context.database):
            print(
                "No pilot run is recorded. Run `wri phase2 --pilot` first and "
                "review Phase_2_Pilot_Summary.md before processing the whole "
                "production."
            )
            return EXIT_ERROR

        result = run_phase2(
            context.config, context.database, context.source, context.output,
            file_ids=file_ids, workers=context.workers, force=args.force,
            enable_ocr=args.ocr, progress=context.progress,
        )
        if not args.no_reports:
            generate_phase2_reports(
                context.config, context.database, context.output, context.source,
                pilot=args.pilot, sample_info=sample_info,
            )

        print("\n" + "=" * 66)
        print(f"PHASE 2 {'PILOT ' if args.pilot else ''}COMPLETE -- "
              "PAGE CONDITION AUDIT")
        print("=" * 66)
        print(f"  Documents processed      {result.documents:,}")
        print(f"  Pages audited            {result.pages:,}")
        print(f"  Extraction failures      {result.failures:,}")
        print(f"  Pages needing OCR        {result.ocr_required:,}")
        print(f"  OCR completed            {result.ocr_completed:,}")
        print(f"  OCR failed               {result.ocr_failed:,}")
        print(f"\n  Reports: {context.output}")
        if args.pilot:
            print("  Read Phase_2_Pilot_Summary.md, then run `wri qc-sample`.")
            print("  Do not run --full until the pilot has been reviewed.")
        print("=" * 66 + "\n")
    return EXIT_OK


def cmd_phase3(args: argparse.Namespace) -> int:
    """Derive review metadata across the production."""
    from .phase3_reports import generate_phase3_reports
    from .pipeline import run_phase3

    with RunContext(args) as context:
        if not _phase_complete(context.database, "phase2"):
            print("Phase 2 has not completed. Run `wri phase2 --pilot` then "
                  "`wri phase2 --full` first.")
            return EXIT_ERROR

        result = run_phase3(
            context.config, context.database, context.source,
            force=args.force, progress=context.progress,
        )
        if not args.no_reports:
            generate_phase3_reports(
                context.config, context.database, context.output, context.source
            )

        print("\n" + "=" * 66)
        print("PHASE 3 COMPLETE -- DERIVED DOCUMENT METADATA")
        print("=" * 66)
        print(f"  Documents indexed              {result.documents:,}")
        print(f"  Documents with issue tags      {result.tagged:,}")
        print(f"  Flagged for manual review      {result.manual_review:,}")
        print(f"  Family relationships inferred  {result.families:,}")
        print(f"  Text duplicate groups          {result.text_dup_groups:,}")
        print(f"  Near-duplicate groups          {result.near_dup_groups:,}")
        print(f"\n  Reports: {context.output}")
        print("  Read Final_Run_Summary.md, then run `wri qc-sample`.")
        print("=" * 66 + "\n")
    return EXIT_OK


def cmd_reports(args: argparse.Namespace) -> int:
    """Regenerate reports from the existing database."""
    from .phase1_reports import generate_phase1_reports
    from .phase2_reports import generate_phase2_reports
    from .phase3_reports import generate_phase3_reports

    with RunContext(args) as context:
        written: List[Path] = []
        if args.phase in ("1", "all"):
            written += generate_phase1_reports(
                context.config, context.database, context.output, context.source
            )
        if args.phase in ("2", "all") and _phase_complete(context.database, "phase2"):
            pilot = context.database.get_stats("phase2").get("mode") == "pilot"
            written += generate_phase2_reports(
                context.config, context.database, context.output, context.source,
                pilot=pilot,
            )
        if args.phase in ("3", "all") and _phase_complete(context.database, "phase3"):
            written += generate_phase3_reports(
                context.config, context.database, context.output, context.source
            )
        print(f"\nRegenerated {len(written)} file(s) in {context.output}\n")
    return EXIT_OK


def cmd_qc_sample(args: argparse.Namespace) -> int:
    """Generate the human quality-control sample."""
    from .qc import generate_qc_workbook

    with RunContext(args) as context:
        if not _phase_complete(context.database, "phase3"):
            print("Phase 3 has not completed; a QC sample needs derived "
                  "metadata. Run `wri phase3` first.")
            return EXIT_ERROR
        path = generate_qc_workbook(
            context.config, context.database, context.output, context.source
        )
        print(f"\nQC sample written to {path}")
        print("Open each document, fill in the two REVIEWER columns, then "
              "compute accuracy per stratum.\n")
    return EXIT_OK


def cmd_retry_failed(args: argparse.Namespace) -> int:
    """Re-attempt only the files that previously failed."""
    from .pipeline import run_phase2, run_phase3

    with RunContext(args) as context:
        rows = context.database.query(
            "SELECT file_id FROM files WHERE processing_status IN "
            "('error','cloud_placeholder') OR extraction_status IN "
            "('failed','partial') OR ocr_status = 'failed'"
        )
        file_ids = [row["file_id"] for row in rows]
        if not file_ids:
            print("No failed files to retry.")
            return EXIT_OK
        print(f"Retrying {len(file_ids)} file(s)...")

        if args.phase == "1":
            run_phase1(
                context.config, context.database, context.source,
                workers=context.workers, force=True, progress=context.progress,
            )
        elif args.phase == "2":
            run_phase2(
                context.config, context.database, context.source, context.output,
                file_ids=file_ids, workers=context.workers, force=True,
                progress=context.progress,
            )
        else:
            run_phase3(
                context.config, context.database, context.source,
                file_ids=file_ids, force=True, progress=context.progress,
            )
        print("Retry complete. Run `wri reports` to refresh the workbooks.")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    """Show processing state counts."""
    with RunContext(args) as context:
        database = context.database
        print(f"\n{APP_NAME} {APP_VERSION}")
        print(f"Source: {context.source}")
        print(f"Output: {context.output}\n")
        print("Processing status:")
        for row in database.query(
            "SELECT processing_status AS s, COUNT(*) AS n FROM files "
            "GROUP BY processing_status ORDER BY n DESC"
        ):
            print(f"  {row['s']:<22} {row['n']:>10,}")
        print("\nExtraction status:")
        for row in database.query(
            "SELECT extraction_status AS s, COUNT(*) AS n FROM files "
            "WHERE is_pdf = 1 GROUP BY extraction_status ORDER BY n DESC"
        ):
            print(f"  {row['s']:<22} {row['n']:>10,}")
        print(f"\nPages audited:      {database.scalar('SELECT COUNT(*) FROM pages'):,}")
        print(f"Documents indexed:  "
              f"{database.scalar('SELECT COUNT(*) FROM documents'):,}")
        print(f"Issue-tag hits:     "
              f"{database.scalar('SELECT COUNT(*) FROM issue_hits'):,}")
        print(f"Audit log entries:  "
              f"{database.scalar('SELECT COUNT(*) FROM audit_log'):,}")

        if args.verbose:
            for phase, stats in sorted(database.get_stats().items()):
                print(f"\n[{phase}]")
                for key, value in sorted(stats.items()):
                    if isinstance(value, dict):
                        value = f"{len(value)} entries"
                    print(f"  {key:<38} {value}")
        print()
    return EXIT_OK


def cmd_search(args: argparse.Namespace) -> int:
    """Search the FTS5 index.  Prints locations only, never text."""
    with RunContext(args) as context:
        rows = context.database.search_text(args.expression, limit=args.limit)
        print(f"\n{len(rows)} hit(s) for {args.expression!r} "
              "(locations only; document text is never printed)\n")
        for row in rows:
            print(f"  {row['filename']}  page {row['page_number']}")
        print(f"\nOpen the files under {context.source} to read them.\n")
    return EXIT_OK


# ---------------------------------------------------------------------------
# gating helpers
# ---------------------------------------------------------------------------
def _phase_complete(database: Database, phase: str) -> bool:
    """Whether a phase recorded a completion entry."""
    row = database.query_one(
        "SELECT 1 FROM audit_log WHERE phase = ? AND operation = ? LIMIT 1",
        (phase, f"{phase}_complete"),
    )
    return row is not None


def _pilot_has_run(database: Database) -> bool:
    """Whether a Phase 2 pilot has been recorded."""
    row = database.query_one(
        "SELECT detail FROM audit_log WHERE operation = 'phase2_start' "
        "AND detail LIKE '%\"pilot\": true%' LIMIT 1"
    )
    return row is not None


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------
COMMANDS = {
    "locate": cmd_locate,
    "doctor": cmd_doctor,
    "phase1": cmd_phase1,
    "phase2": cmd_phase2,
    "phase3": cmd_phase3,
    "reports": cmd_reports,
    "qc-sample": cmd_qc_sample,
    "retry-failed": cmd_retry_failed,
    "status": cmd_status,
    "search": cmd_search,
}


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point.  Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = COMMANDS[args.command]
    try:
        return handler(args)
    except ConfigError as exc:
        print(f"\nConfiguration error: {exc}\n", file=sys.stderr)
        return EXIT_NEEDS_INPUT
    except ReadOnlySourceError as exc:
        print(f"\nRead-only safeguard triggered: {exc}\n", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:
        print("\nInterrupted. Progress is saved; re-run the same command to "
              "resume where it stopped.\n", file=sys.stderr)
        return EXIT_ERROR
    except Exception as exc:  # pragma: no cover - top-level safety net
        log.exception("Unhandled error in %s", args.command)
        print(f"\nError: {type(exc).__name__}: {exc}\n", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
