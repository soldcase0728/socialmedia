"""Phase 1 report generation -- structural inventory outputs.

Produces:

* ``01_File_Inventory.xlsx`` / ``.csv``
* ``02_Bates_Structural_Report.xlsx``
* ``03_Exact_Duplicate_Report.xlsx``
* ``04_Unreadable_or_Corrupt_Files.xlsx``
* ``Phase_1_Summary.md``

Rows stream straight from SQLite, so memory stays flat regardless of how many
documents the production contains.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence

from .bates import find_filename_gaps
from .config import Config
from .database import Database
from .logging_setup import get_logger
from .reports import (
    CALCULATED,
    Column,
    INFERRED,
    OBSERVED,
    ReportWriter,
    Sheet,
    format_bytes,
)
from .version import APP_NAME, APP_VERSION

log = get_logger("phase1_reports")

PHASE = "phase1"

PRELIMINARY_GAP_NOTE = (
    "PRELIMINARY. These gaps are computed from filenames only. Each PDF in "
    "this production may contain several Bates-numbered pages, so a numeric "
    "jump between filenames does not by itself establish that pages are "
    "missing. Confirm against observed page stamps in Phase 3."
)

INVENTORY_NOTE = (
    "Derived review metadata from Phase 1 (structural inventory). No "
    "substantive document content was read to produce this sheet."
)


# ---------------------------------------------------------------------------
# column definitions
# ---------------------------------------------------------------------------
def inventory_columns() -> List[Column]:
    """Columns for the file inventory sheet."""
    return [
        Column("filename", "Filename", provenance=OBSERVED,
               description="File name exactly as it appears in the production."),
        Column("rel_path", "Relative Path", width=40, provenance=OBSERVED,
               description="Path relative to the root of the source folder."),
        Column("abs_path", "Google Drive Local Path", width=55, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Absolute local path. Click to open the source file "
                           "read-only in the default application."),
        Column("extension", "File Type", provenance=OBSERVED,
               description="File extension, lowercased."),
        Column("file_size", "File Size (bytes)", provenance=OBSERVED,
               number_format="#,##0",
               description="Size in bytes as reported by the file system."),
        Column("size_human", "File Size", provenance=CALCULATED,
               description="File size in human-readable units."),
        Column("created_ts", "Created (UTC)", provenance=OBSERVED,
               description="File-system creation time where the platform "
                           "records one. Blank on file systems that do not. "
                           "This is a file-system timestamp, not a document "
                           "authoring date."),
        Column("modified_ts", "Modified (UTC)", provenance=OBSERVED,
               description="File-system modification time. Reflects when the "
                           "file was written to this disk, which for a synced "
                           "Drive folder may be the sync time rather than the "
                           "original document date."),
        Column("sha256", "SHA-256", width=48, provenance=CALCULATED,
               description="SHA-256 digest of the file's bytes. Any two files "
                           "sharing this value are byte-identical."),
        Column("page_count", "PDF Page Count", provenance=OBSERVED,
               number_format="#,##0",
               description="Page count read from the PDF. Blank when the file "
                           "is not a PDF or could not be opened."),
        Column("filename_bates", "Bates from Filename", provenance=CALCULATED,
               description="Bates number parsed from the filename using the "
                           "configured pattern. Not a stamp observed on a page."),
        Column("filename_compliant_text", "Filename Pattern Compliant",
               provenance=CALCULATED,
               description="Yes when the filename fully matches the configured "
                           "production naming pattern."),
        Column("duplicate_filename_text", "Duplicate Filename",
               provenance=CALCULATED,
               description="Yes when this base filename occurs more than once "
                           "anywhere in the production."),
        Column("exact_dup_group", "Exact Duplicate Group", provenance=CALCULATED,
               description="Group identifier shared by byte-identical files. "
                           "Blank when the file is unique."),
        Column("encrypted_text", "Encrypted / Password Protected",
               provenance=OBSERVED,
               description="Yes when the PDF reports that it requires a "
                           "password. No password was attempted."),
        Column("corrupt_text", "Corrupt or Unreadable", provenance=OBSERVED,
               description="Yes when the file could not be opened or read by "
                           "either PDF library."),
        Column("placeholder_text", "Cloud Placeholder", provenance=OBSERVED,
               description="Yes when the file appears to be a Google Drive stub "
                           "that has not been downloaded locally. These are "
                           "retried, not treated as corrupt."),
        Column("processing_status", "Processing Status", provenance=CALCULATED,
               description="Pipeline state for this file."),
        Column("error_message", "Notes / Error", width=45, wrap=True,
               provenance=CALCULATED,
               description="Any error or condition recorded while probing the "
                           "file. Never contains document text."),
    ]


def bates_columns() -> List[Column]:
    """Columns for the Bates structural sheet."""
    return [
        Column("filename_bates", "Bates from Filename", provenance=CALCULATED,
               description="Normalised Bates number parsed from the filename."),
        Column("filename_bates_num", "Bates Number (numeric)",
               provenance=CALCULATED, number_format="#,##0",
               description="Numeric portion, for sorting and gap analysis."),
        Column("filename", "Filename", provenance=OBSERVED,
               description="File name as produced."),
        Column("rel_path", "Relative Path", width=40, provenance=OBSERVED,
               description="Path relative to the source folder root."),
        Column("abs_path", "Local File Link", width=50, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the local source file."),
        Column("page_count", "PDF Page Count", provenance=OBSERVED,
               number_format="#,##0",
               description="Pages in this PDF. A value above 1 means this "
                           "single file spans multiple Bates numbers."),
        Column("implied_end_bates", "Implied End Bates (calculated)",
               provenance=CALCULATED,
               description="Begin Bates + page count - 1. CALCULATED ONLY: no "
                           "page stamp was read in Phase 1, so this is an "
                           "arithmetic projection, not an observation."),
        Column("filename_compliant_text", "Filename Pattern Compliant",
               provenance=CALCULATED,
               description="Yes when the filename matches the configured "
                           "production naming pattern."),
        Column("issue", "Structural Issue", width=40, wrap=True,
               provenance=CALCULATED,
               description="Structural problem detected with this file's "
                           "naming or Bates number, if any."),
    ]


def gap_columns() -> List[Column]:
    """Columns for the preliminary filename-gap sheet."""
    return [
        Column("after", "Last Bates Before Gap", provenance=CALCULATED,
               number_format="#,##0",
               description="Highest filename Bates number before the gap."),
        Column("before", "First Bates After Gap", provenance=CALCULATED,
               number_format="#,##0",
               description="Lowest filename Bates number after the gap."),
        Column("missing_count", "Numbers Not Present in Any Filename",
               provenance=CALCULATED, number_format="#,##0",
               description="Count of Bates numbers in this range that do not "
                           "appear in any filename."),
        Column("status", "Status", provenance=INFERRED,
               description="Always 'Preliminary' at Phase 1."),
        Column("note", "Why This Is Preliminary", width=70, wrap=True,
               provenance=INFERRED,
               description="Explanation of why a filename gap may not be a "
                           "true production gap."),
    ]


def duplicate_columns() -> List[Column]:
    """Columns for the exact-duplicate sheet."""
    return [
        Column("exact_dup_group", "Exact Duplicate Group", provenance=CALCULATED,
               description="Group identifier derived from the SHA-256 digest."),
        Column("group_size", "Files in Group", provenance=CALCULATED,
               number_format="#,##0",
               description="How many byte-identical files share this digest."),
        Column("filename", "Filename", provenance=OBSERVED,
               description="File name as produced."),
        Column("filename_bates", "Bates from Filename", provenance=CALCULATED,
               description="Bates number parsed from the filename."),
        Column("rel_path", "Relative Path", width=40, provenance=OBSERVED,
               description="Path relative to the source folder root."),
        Column("abs_path", "Local File Link", width=50, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the local source file."),
        Column("file_size", "File Size (bytes)", provenance=OBSERVED,
               number_format="#,##0", description="Size in bytes."),
        Column("page_count", "PDF Page Count", provenance=OBSERVED,
               number_format="#,##0", description="Pages in this PDF."),
        Column("sha256", "SHA-256", width=48, provenance=CALCULATED,
               description="Full digest. Re-hash any file to verify the group."),
        Column("role", "Role in Group", provenance=CALCULATED,
               description="'First by Bates order' marks the copy with the "
                           "lowest Bates number; the rest are additional "
                           "identical copies. This is an ordering convention, "
                           "not a determination of which copy to produce."),
    ]


def problem_columns() -> List[Column]:
    """Columns for the unreadable/corrupt sheet."""
    return [
        Column("filename", "Filename", provenance=OBSERVED,
               description="File name as produced."),
        Column("rel_path", "Relative Path", width=40, provenance=OBSERVED,
               description="Path relative to the source folder root."),
        Column("abs_path", "Local File Link", width=50, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the local source file."),
        Column("file_size", "File Size (bytes)", provenance=OBSERVED,
               number_format="#,##0", description="Size in bytes."),
        Column("problem", "Problem Category", provenance=CALCULATED,
               description="Why this file could not be fully inventoried."),
        Column("error_message", "Detail", width=60, wrap=True,
               provenance=CALCULATED,
               description="Diagnostic detail. Never contains document text."),
        Column("suggested_action", "Suggested Action", width=50, wrap=True,
               provenance=INFERRED,
               description="What to try next. A suggestion only."),
    ]


# ---------------------------------------------------------------------------
# row builders
# ---------------------------------------------------------------------------
def _yes_no(value: Any) -> str:
    """Render a truthy database flag as Yes/No."""
    return "Yes" if value else "No"


def iter_inventory_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream inventory rows in Bates then filename order."""
    for row in database.iter_query(
        "SELECT * FROM files ORDER BY filename_bates_num IS NULL, "
        "filename_bates_num, filename"
    ):
        yield {
            "filename": row["filename"],
            "rel_path": row["rel_path"],
            "abs_path": row["abs_path"],
            "extension": row["extension"],
            "file_size": row["file_size"],
            "size_human": format_bytes(row["file_size"] or 0),
            "created_ts": row["created_ts"],
            "modified_ts": row["modified_ts"],
            "sha256": row["sha256"],
            "page_count": row["page_count"],
            "filename_bates": row["filename_bates"],
            "filename_compliant_text": _yes_no(row["filename_compliant"]),
            "duplicate_filename_text": _yes_no(row["duplicate_filename"]),
            "exact_dup_group": row["exact_dup_group"],
            "encrypted_text": _yes_no(row["is_encrypted"]),
            "corrupt_text": _yes_no(row["is_corrupt"]),
            "placeholder_text": _yes_no(row["is_placeholder"]),
            "processing_status": row["processing_status"],
            "error_message": row["error_message"] or row["notes"],
        }


def iter_bates_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream Bates structural rows, annotating structural problems."""
    for row in database.iter_query(
        "SELECT * FROM files WHERE is_pdf = 1 "
        "ORDER BY filename_bates_num IS NULL, filename_bates_num, filename"
    ):
        issues: List[str] = []
        if row["filename_bates_num"] is None:
            issues.append("no Bates number could be parsed from the filename")
        if not row["filename_compliant"]:
            issues.append("filename does not match the configured production pattern")
        if row["page_count"] is None:
            issues.append("page count unavailable")
        elif row["page_count"] > 1:
            issues.append(
                f"single file spans {row['page_count']} pages, so it covers "
                "multiple Bates numbers"
            )
        if row["is_encrypted"]:
            issues.append("encrypted; not opened")
        if row["is_corrupt"]:
            issues.append("could not be read")

        implied_end = None
        if row["filename_bates_num"] is not None and row["page_count"]:
            implied_end = row["filename_bates_num"] + row["page_count"] - 1

        yield {
            "filename_bates": row["filename_bates"],
            "filename_bates_num": row["filename_bates_num"],
            "filename": row["filename"],
            "rel_path": row["rel_path"],
            "abs_path": row["abs_path"],
            "page_count": row["page_count"],
            "implied_end_bates": implied_end,
            "filename_compliant_text": _yes_no(row["filename_compliant"]),
            "issue": "; ".join(issues) if issues else "none detected",
        }


def iter_duplicate_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream exact-duplicate rows, grouped and ordered."""
    sizes = {
        row["gid"]: row["n"]
        for row in database.query(
            "SELECT exact_dup_group AS gid, COUNT(*) AS n FROM files "
            "WHERE exact_dup_group IS NOT NULL GROUP BY exact_dup_group"
        )
    }
    seen_first: set[str] = set()
    for row in database.iter_query(
        "SELECT * FROM files WHERE exact_dup_group IS NOT NULL "
        "ORDER BY exact_dup_group, filename_bates_num IS NULL, "
        "filename_bates_num, filename"
    ):
        group = row["exact_dup_group"]
        role = "Additional identical copy"
        if group not in seen_first:
            seen_first.add(group)
            role = "First by Bates order"
        yield {
            "exact_dup_group": group,
            "group_size": sizes.get(group, 0),
            "filename": row["filename"],
            "filename_bates": row["filename_bates"],
            "rel_path": row["rel_path"],
            "abs_path": row["abs_path"],
            "file_size": row["file_size"],
            "page_count": row["page_count"],
            "sha256": row["sha256"],
            "role": role,
        }


def iter_problem_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream rows for files that could not be fully inventoried."""
    for row in database.iter_query(
        "SELECT * FROM files WHERE is_corrupt = 1 OR is_encrypted = 1 "
        "OR is_placeholder = 1 OR processing_status = 'error' "
        "ORDER BY filename_bates_num IS NULL, filename_bates_num, filename"
    ):
        if row["is_placeholder"]:
            problem = "Cloud placeholder (not downloaded)"
            action = (
                "In Finder, right-click the file and choose 'Make available "
                "offline', wait for the download, then re-run Phase 1. The "
                "file will be picked up automatically."
            )
        elif row["is_encrypted"]:
            problem = "Encrypted / password protected"
            action = (
                "No password was attempted. If the password is known, decrypt "
                "a COPY outside the production folder and index that copy "
                "separately. Never modify the produced file."
            )
        elif row["is_corrupt"]:
            problem = "Corrupt or unreadable"
            action = (
                "Confirm the file opens in a PDF viewer. If it does not, this "
                "is a production defect worth raising with the producing party."
            )
        else:
            problem = "Processing error"
            action = "Re-run with `wri retry-failed` to attempt this file again."
        yield {
            "filename": row["filename"],
            "rel_path": row["rel_path"],
            "abs_path": row["abs_path"],
            "file_size": row["file_size"],
            "problem": problem,
            "error_message": row["error_message"],
            "suggested_action": action,
        }


def iter_gap_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream preliminary filename-gap rows."""
    numbers = [
        row["filename_bates_num"]
        for row in database.query(
            "SELECT filename_bates_num FROM files WHERE filename_bates_num IS NOT NULL"
        )
    ]
    for gap in find_filename_gaps(numbers, preliminary=True):
        yield {
            "after": gap.after,
            "before": gap.before,
            "missing_count": gap.missing_count,
            "status": "Preliminary",
            "note": gap.note,
        }


# ---------------------------------------------------------------------------
# report generation
# ---------------------------------------------------------------------------
def generate_phase1_reports(
    config: Config, database: Database, output_dir: Path, source: Path
) -> List[Path]:
    """Write every Phase 1 output and return the paths written."""
    stats = database.get_stats()
    writer = ReportWriter(
        output_dir,
        source_root=source,
        settings=config.section("reports"),
        run_stats=stats,
    )
    written: List[Path] = []

    inventory_cols = inventory_columns()
    written.append(
        writer.write_workbook(
            "01_File_Inventory.xlsx",
            [
                Sheet("File Inventory", inventory_cols,
                      iter_inventory_rows(database), note=INVENTORY_NOTE)
            ],
        )
    )
    written.append(
        writer.write_csv("01_File_Inventory.csv", inventory_cols,
                         iter_inventory_rows(database))
    )

    written.append(
        writer.write_workbook(
            "02_Bates_Structural_Report.xlsx",
            [
                Sheet("Bates Structure", bates_columns(), iter_bates_rows(database),
                      note="Bates numbers here are parsed from FILENAMES only. "
                           "Page stamps are not read until Phase 2/3."),
                Sheet("Preliminary Filename Gaps", gap_columns(),
                      iter_gap_rows(database), note=PRELIMINARY_GAP_NOTE),
            ],
            limitations=_bates_limitations(),
        )
    )

    written.append(
        writer.write_workbook(
            "03_Exact_Duplicate_Report.xlsx",
            [
                Sheet("Exact Duplicates", duplicate_columns(),
                      iter_duplicate_rows(database),
                      note="Files in the same group are byte-identical "
                           "(same SHA-256). Verify by re-hashing any two.")
            ],
        )
    )

    written.append(
        writer.write_workbook(
            "04_Unreadable_or_Corrupt_Files.xlsx",
            [
                Sheet("Problem Files", problem_columns(),
                      iter_problem_rows(database),
                      note="Files that could not be fully inventoried. Cloud "
                           "placeholders are NOT corrupt: they simply have not "
                           "been downloaded from Google Drive yet.")
            ],
        )
    )

    written.append(
        writer.write_markdown(
            "Phase_1_Summary.md",
            build_phase1_summary(config, database, stats.get(PHASE, {}), source,
                                 output_dir),
        )
    )

    database.audit(
        "phase1_reports",
        phase=PHASE,
        target=str(output_dir),
        outcome="completed",
        detail={"files": [p.name for p in written]},
    )
    return written


def _bates_limitations() -> List[str]:
    """Limitations text specific to the Bates structural report."""
    from .reports import DEFAULT_LIMITATIONS

    return [
        "Every Bates value in this workbook was parsed from a FILENAME. No "
        "Bates stamp printed on a page was read during Phase 1.",
        "The 'Implied End Bates' column is arithmetic (begin + pages - 1). It "
        "assumes one Bates number per page and that the filename Bates is the "
        "document's first page. Neither assumption has been verified at this "
        "stage.",
        "Gaps on the 'Preliminary Filename Gaps' sheet are not established "
        "production gaps. Multi-page PDFs consume Bates numbers that never "
        "appear in any filename.",
        *DEFAULT_LIMITATIONS,
    ]


# ---------------------------------------------------------------------------
# markdown summary
# ---------------------------------------------------------------------------
def build_phase1_summary(
    config: Config,
    database: Database,
    stats: Dict[str, Any],
    source: Path,
    output_dir: Path,
) -> str:
    """Render the Phase 1 Markdown summary (aggregates only, no content)."""
    distribution = stats.get("page_count_distribution", {}) or {}
    extensions = stats.get("extension_distribution", {}) or {}

    def page_bucket_table() -> str:
        """Summarise the page-count distribution into readable buckets."""
        buckets = {"1": 0, "2-5": 0, "6-20": 0, "21-100": 0, "101+": 0, "unknown": 0}
        for key, count in distribution.items():
            if key == "unknown" or key == "None":
                buckets["unknown"] += count
                continue
            try:
                pages = int(key)
            except ValueError:
                buckets["unknown"] += count
                continue
            if pages <= 1:
                buckets["1"] += count
            elif pages <= 5:
                buckets["2-5"] += count
            elif pages <= 20:
                buckets["6-20"] += count
            elif pages <= 100:
                buckets["21-100"] += count
            else:
                buckets["101+"] += count
        lines = ["| Pages per PDF | Files |", "| --- | ---: |"]
        for label, count in buckets.items():
            lines.append(f"| {label} | {count:,} |")
        return "\n".join(lines)

    def extension_table() -> str:
        """Summarise the file-type distribution."""
        lines = ["| Extension | Files |", "| --- | ---: |"]
        for ext, count in sorted(extensions.items(), key=lambda kv: -kv[1])[:15]:
            lines.append(f"| `{ext}` | {count:,} |")
        return "\n".join(lines)

    bates_min = stats.get("bates_min")
    bates_max = stats.get("bates_max")
    distinct = stats.get("bates_distinct") or 0
    span = stats.get("bates_span") or 0

    return f"""# Phase 1 Summary -- Structural Inventory

**Generated:** {datetime.now(timezone.utc).isoformat(timespec="seconds")}
**Application:** {APP_NAME} {APP_VERSION}
**Source folder (read-only):** `{source}`
**Derived index folder:** `{output_dir}`

> **These are DERIVED review metadata.** Every value below was computed by
> software from the produced files themselves. None of it is original or
> native document metadata. The production did not include a CSV, DAT, OPT or
> native-file index, so no native metadata was available.

---

## What Phase 1 did

Phase 1 walked the source folder recursively and recorded structural facts
only. It did **not** read substantive document content, did not extract text,
did not OCR anything, and did not send any data anywhere. The source folder
was opened read-only; nothing in it was renamed, moved, altered, annotated,
combined or deleted.

---

## Collection totals

| Measure | Value |
| --- | ---: |
| Total files | {stats.get('total_files', 0):,} |
| PDF files | {stats.get('pdf_files', 0):,} |
| Non-PDF files | {stats.get('non_pdf_files', 0):,} |
| Total storage size | {format_bytes(stats.get('total_bytes', 0))} |
| Total pages observed across PDFs | {stats.get('total_pages_observed', 0):,} |

### File types

{extension_table()}

---

## Bates numbers parsed from filenames

| Measure | Value |
| --- | ---: |
| Minimum apparent Bates number | {bates_min if bates_min is not None else 'none found'} |
| Maximum apparent Bates number | {bates_max if bates_max is not None else 'none found'} |
| Distinct Bates numbers in filenames | {distinct:,} |
| Numeric span (max - min + 1) | {span:,} |
| Files with no parseable Bates number | {stats.get('files_without_filename_bates', 0):,} |
| PDFs whose filename does not match the production pattern | {stats.get('filename_non_compliant_pdfs', 0):,} |

### Preliminary Bates gaps -- read this carefully

| Measure | Value |
| --- | ---: |
| Preliminary gap ranges (filenames only) | {stats.get('preliminary_filename_gap_count', 0):,} |
| Bates numbers absent from every filename | {stats.get('preliminary_missing_bates_numbers', 0):,} |

**These are PRELIMINARY and are very likely NOT missing documents.** Each PDF
in this production may contain several Bates-numbered pages. A five-page PDF
named `WILSONRODE000010-null.pdf` consumes Bates 000010 through 000014, but
only 000010 appears in a filename -- so 000011-000014 show up here as an
apparent "gap" while being perfectly present in the production. Real gap
analysis requires reading Bates stamps off the pages, which happens in Phase
2/3.

---

## Duplicates

| Measure | Value |
| --- | ---: |
| Files sharing a base filename with another file | {stats.get('files_with_duplicate_filenames', 0):,} |
| Exact (byte-identical) duplicate groups | {stats.get('exact_duplicate_groups', 0):,} |
| Files belonging to an exact duplicate group | {stats.get('files_in_exact_duplicate_groups', 0):,} |

Exact duplicates are established by SHA-256, so they are reproducible: re-hash
any two files in a group and the digests will match.

---

## Files needing attention

| Condition | Files |
| --- | ---: |
| Encrypted / password protected | {stats.get('encrypted_pdfs', 0):,} |
| Corrupt or unreadable | {stats.get('corrupt_or_unreadable', 0):,} |
| Cloud placeholders (not downloaded from Drive) | {stats.get('cloud_placeholders', 0):,} |

Cloud placeholders are **not** corrupt files. They are stubs for documents
Google Drive has not downloaded locally yet. Make them available offline in
Finder and re-run Phase 1; the run is resumable and will pick them up without
redoing completed work.

---

## Page-count distribution

{page_bucket_table()}

The number of PDFs with more than one page is the single most important figure
for Bates analysis: it is exactly the reason filename-based gaps are
unreliable.

---

## Files produced

| File | Contents |
| --- | --- |
| `01_File_Inventory.xlsx` | Every file, with clickable local links |
| `01_File_Inventory.csv` | Same data, plain CSV |
| `02_Bates_Structural_Report.xlsx` | Bates parsing, structural issues, preliminary gaps |
| `03_Exact_Duplicate_Report.xlsx` | Byte-identical duplicate groups |
| `04_Unreadable_or_Corrupt_Files.xlsx` | Encrypted, corrupt and placeholder files |
| `Phase_1_Summary.md` | This document |
| `wilson_rode_index.sqlite` | Processing-state database (authoritative) |
| `logs/wilson_rode_indexer.log` | Full audit log |

---

## Limitations of Phase 1

1. Bates numbers here come from **filenames only**. No page stamp was read.
2. Filename-based gaps are **preliminary** and are expected to shrink or
   disappear once page stamps are read.
3. Page counts come from the PDF page tree. A file that reports 3 pages may
   still contain blank or image-only pages; Phase 2 determines that.
4. `Created` timestamps are file-system timestamps. On a Google Drive-synced
   folder they often reflect the sync, not the document's authoring date.
   They are not evidence of when a document was created.
5. Nothing here says anything about document content, relevance, privilege or
   significance. Phase 1 did not read content.

---

## Next step

Phase 2 (text and page-condition audit) has **not** been run. It will begin
with a pilot sample of approximately
{int(config.get('pilot', 'target_size', default=200))} documents so its
accuracy can be measured before the full production is processed.

Phase 2 will not start until you explicitly approve it.
"""
