"""Phase 2 report generation -- page-condition audit outputs.

Produces:

* ``05_Page_Condition_Audit.xlsx``
* ``06_Blank_and_Bates_Only_Candidates.xlsx``
* ``07_OCR_Required.xlsx``
* ``08_Extraction_Failures.xlsx``
* ``Phase_2_Pilot_Summary.md`` (pilot runs) or ``Phase_2_Summary.md``
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from .config import Config
from .database import Database
from .logging_setup import get_logger
from .reports import CALCULATED, Column, INFERRED, OBSERVED, ReportWriter, Sheet
from .version import APP_NAME, APP_VERSION

log = get_logger("phase2_reports")

PHASE = "phase2"

CONDITION_MEANINGS: Dict[str, str] = {
    "searchable": "The page carries a usable text layer and can be searched.",
    "image_only": "The page has image content but effectively no text layer. "
                  "A candidate for OCR.",
    "ocr_required": "Text extraction was insufficient and the page holds "
                    "meaningful image content.",
    "ocr_completed": "OCR ran locally and a searchable derivative is cached "
                     "in the derived-index folder. The source PDF was not "
                     "modified.",
    "apparent_blank": "Neither meaningful text nor meaningful image content "
                      "was found.",
    "bates_only": "The only text found on the page was its Bates stamp.",
    "corrupt": "The page could not be read.",
    "uncertain": "The evidence did not clearly support any other category. "
                 "Not guessed.",
}

SUBTYPE_MEANINGS: Dict[str, str] = {
    "truly_blank_candidate": "No text and no images. Most likely a genuinely "
                             "blank page or a backside.",
    "bates_stamp_only": "Bates stamp present, nothing else. Common for "
                        "backsides of double-sided originals.",
    "possible_separator_page": "Page text matches a separator or placeholder "
                               "phrase such as 'this page intentionally left "
                               "blank'.",
    "possible_failed_export": "No text at all where text was expected. May "
                              "indicate a failed conversion during production.",
    "uncertain": "Insufficient evidence to distinguish the above.",
}


# ---------------------------------------------------------------------------
# columns
# ---------------------------------------------------------------------------
def page_columns() -> List[Column]:
    """Columns for the page-condition audit."""
    return [
        Column("filename", "Filename", provenance=OBSERVED,
               description="Source file containing this page."),
        Column("filename_bates", "Bates from Filename", provenance=CALCULATED,
               description="Bates parsed from the filename."),
        Column("page_number", "Page", provenance=OBSERVED, number_format="#,##0",
               description="1-based page number within the PDF."),
        Column("observed_bates", "Bates Observed on Page", provenance=OBSERVED,
               description="Bates stamp actually read from this page's text. "
                           "Stronger evidence than the filename."),
        Column("page_condition", "Page Condition", provenance=CALCULATED,
               description="Condition classification. See the Condition "
                           "Reference sheet."),
        Column("blank_subtype", "Blank / Bates-Only Subtype", provenance=INFERRED,
               description="Where a page is blank or Bates-only, the most "
                           "likely reason. Inferred."),
        Column("char_count", "Characters Extracted", provenance=CALCULATED,
               number_format="#,##0",
               description="Characters of text extracted from the page."),
        Column("word_count", "Words Extracted", provenance=CALCULATED,
               number_format="#,##0",
               description="Whitespace-delimited tokens extracted."),
        Column("has_text_layer_text", "Has Searchable Text Layer",
               provenance=CALCULATED,
               description="Yes when extracted characters met the configured "
                           "threshold."),
        Column("image_count", "Images on Page", provenance=OBSERVED,
               number_format="#,##0",
               description="Number of embedded images the PDF reports."),
        Column("image_coverage_pct", "Approx. Image Coverage (%)",
               provenance=CALCULATED, number_format="0.0",
               description="Total image area as a percentage of page area. "
                           "Overlapping images can inflate this; it is clipped "
                           "at 100%."),
        Column("ocr_status", "OCR Status", provenance=CALCULATED,
               description="Whether OCR is required, completed, failed or "
                           "unnecessary for this page."),
        Column("ocr_cache_path", "OCR Derivative (cache)", width=45, wrap=True,
               provenance=CALCULATED,
               description="Path to the cached OCR derivative inside the "
                           "derived-index folder. The source PDF is unchanged."),
        Column("abs_path", "Local File Link", width=50, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the source PDF."),
        Column("error_message", "Notes / Error", width=40, wrap=True,
               provenance=CALCULATED,
               description="Any error recorded for this page."),
    ]


def blank_columns() -> List[Column]:
    """Columns for the blank / Bates-only candidates sheet."""
    return [
        Column("filename", "Filename", provenance=OBSERVED,
               description="Source file."),
        Column("filename_bates", "Bates from Filename", provenance=CALCULATED,
               description="Bates parsed from the filename."),
        Column("page_number", "Page", provenance=OBSERVED, number_format="#,##0",
               description="1-based page number."),
        Column("observed_bates", "Bates Observed on Page", provenance=OBSERVED,
               description="Bates stamp read from the page."),
        Column("blank_subtype", "Candidate Category", provenance=INFERRED,
               description="Best-supported explanation for the empty page."),
        Column("category_meaning", "What That Means", width=55, wrap=True,
               provenance=INFERRED,
               description="Plain-language explanation of the category."),
        Column("char_count", "Characters", provenance=CALCULATED,
               number_format="#,##0", description="Characters extracted."),
        Column("image_count", "Images", provenance=OBSERVED, number_format="#,##0",
               description="Embedded images reported."),
        Column("image_coverage_pct", "Image Coverage (%)", provenance=CALCULATED,
               number_format="0.0", description="Approximate image coverage."),
        Column("verification_needed", "Verification Needed", width=45, wrap=True,
               provenance=INFERRED,
               description="What a reviewer should check to confirm the "
                           "category."),
        Column("abs_path", "Local File Link", width=50, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the source PDF."),
    ]


def ocr_columns() -> List[Column]:
    """Columns for the OCR-required sheet."""
    return [
        Column("filename", "Filename", provenance=OBSERVED,
               description="Source file."),
        Column("filename_bates", "Bates from Filename", provenance=CALCULATED,
               description="Bates parsed from the filename."),
        Column("pages_needing_ocr", "Pages Needing OCR", provenance=CALCULATED,
               number_format="#,##0",
               description="Count of pages with insufficient text and "
                           "meaningful image content."),
        Column("page_count", "Total Pages", provenance=OBSERVED,
               number_format="#,##0", description="Pages in the PDF."),
        Column("page_list", "Page Numbers", width=30, wrap=True,
               provenance=CALCULATED,
               description="The specific pages that need OCR."),
        Column("file_size", "File Size (bytes)", provenance=OBSERVED,
               number_format="#,##0", description="Size in bytes."),
        Column("ocr_status", "Document OCR Status", provenance=CALCULATED,
               description="Overall OCR state for the document."),
        Column("abs_path", "Local File Link", width=50, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the source PDF."),
    ]


def failure_columns() -> List[Column]:
    """Columns for the extraction-failures sheet."""
    return [
        Column("filename", "Filename", provenance=OBSERVED,
               description="Source file."),
        Column("filename_bates", "Bates from Filename", provenance=CALCULATED,
               description="Bates parsed from the filename."),
        Column("extraction_status", "Extraction Status", provenance=CALCULATED,
               description="Whether extraction failed entirely or partially."),
        Column("page_count", "Pages", provenance=OBSERVED, number_format="#,##0",
               description="Pages the PDF reports."),
        Column("pages_audited", "Pages Successfully Audited",
               provenance=CALCULATED, number_format="#,##0",
               description="Pages the extractor managed to read."),
        Column("error_message", "Detail", width=60, wrap=True,
               provenance=CALCULATED,
               description="Diagnostic detail. Never contains document text."),
        Column("suggested_action", "Suggested Action", width=45, wrap=True,
               provenance=INFERRED, description="What to try next."),
        Column("abs_path", "Local File Link", width=50, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the source PDF."),
    ]


def reference_columns() -> List[Column]:
    """Columns for the condition-reference sheet."""
    return [
        Column("value", "Value", provenance=CALCULATED,
               description="Classification value used in this workbook."),
        Column("kind", "Applies To", provenance=CALCULATED,
               description="Whether the value is a page condition or a "
                           "blank/Bates-only subtype."),
        Column("meaning", "Meaning", width=80, wrap=True, provenance=CALCULATED,
               description="What the classification means."),
    ]


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------
def _page_query(database: Database, extra: str = "", params: Sequence[Any] = ()):
    """Stream joined page/file rows."""
    return database.iter_query(
        "SELECT p.*, f.filename, f.filename_bates, f.abs_path, f.rel_path, "
        "f.page_count AS file_pages, f.file_size FROM pages p "
        "JOIN files f ON f.file_id = p.file_id "
        f"{extra} ORDER BY f.filename_bates_num, f.filename, p.page_number",
        params,
    )


def iter_page_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream every audited page."""
    for row in _page_query(database):
        yield {
            "filename": row["filename"],
            "filename_bates": row["filename_bates"],
            "page_number": row["page_number"],
            "observed_bates": row["observed_bates"],
            "page_condition": row["page_condition"],
            "blank_subtype": row["blank_subtype"],
            "char_count": row["char_count"],
            "word_count": row["word_count"],
            "has_text_layer_text": "Yes" if row["has_text_layer"] else "No",
            "image_count": row["image_count"],
            "image_coverage_pct": round((row["image_coverage"] or 0) * 100, 1),
            "ocr_status": row["ocr_status"],
            "ocr_cache_path": row["ocr_cache_path"],
            "abs_path": row["abs_path"],
            "error_message": row["error_message"],
        }


def iter_blank_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream blank and Bates-only page candidates."""
    verification = {
        "truly_blank_candidate": "Open the page and confirm it is blank. If it "
                                 "is not, the PDF may have a broken content "
                                 "stream.",
        "bates_stamp_only": "Confirm the page carries only a stamp. Common for "
                            "the reverse of a double-sided original.",
        "possible_separator_page": "Confirm this is a production separator and "
                                   "not a withheld document.",
        "possible_failed_export": "Compare against the native file if "
                                  "available. A failed export may need to be "
                                  "re-requested from the producing party.",
        "uncertain": "Open the page and categorise it manually.",
    }
    for row in _page_query(
        database,
        "WHERE p.page_condition IN ('apparent_blank', 'bates_only') "
        "OR p.blank_subtype IS NOT NULL",
    ):
        subtype = row["blank_subtype"] or "uncertain"
        yield {
            "filename": row["filename"],
            "filename_bates": row["filename_bates"],
            "page_number": row["page_number"],
            "observed_bates": row["observed_bates"],
            "blank_subtype": subtype,
            "category_meaning": SUBTYPE_MEANINGS.get(subtype, ""),
            "char_count": row["char_count"],
            "image_count": row["image_count"],
            "image_coverage_pct": round((row["image_coverage"] or 0) * 100, 1),
            "verification_needed": verification.get(subtype, ""),
            "abs_path": row["abs_path"],
        }


def iter_ocr_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream documents with pages awaiting OCR."""
    rows = database.query(
        "SELECT f.file_id, f.filename, f.filename_bates, f.abs_path, "
        "f.page_count, f.file_size, f.ocr_status, "
        "COUNT(p.page_row_id) AS needing, "
        "GROUP_CONCAT(p.page_number) AS page_list "
        "FROM files f JOIN pages p ON p.file_id = f.file_id "
        "WHERE p.ocr_status IN ('required', 'failed') "
        "GROUP BY f.file_id ORDER BY needing DESC, f.filename_bates_num"
    )
    for row in rows:
        pages = sorted(int(p) for p in (row["page_list"] or "").split(",") if p)
        yield {
            "filename": row["filename"],
            "filename_bates": row["filename_bates"],
            "pages_needing_ocr": row["needing"],
            "page_count": row["page_count"],
            "page_list": _compact_ranges(pages),
            "file_size": row["file_size"],
            "ocr_status": row["ocr_status"],
            "abs_path": row["abs_path"],
        }


def iter_failure_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream documents whose extraction failed or only partly succeeded."""
    rows = database.query(
        "SELECT f.*, (SELECT COUNT(*) FROM pages p WHERE p.file_id = f.file_id) "
        "AS audited FROM files f "
        "WHERE f.extraction_status IN ('failed', 'partial', 'encrypted') "
        "ORDER BY f.filename_bates_num, f.filename"
    )
    actions = {
        "failed": "Open the file in a PDF viewer to confirm it is readable. If "
                  "it opens normally, re-run `wri retry-failed`.",
        "partial": "Some pages read and some did not. Review the specific pages "
                   "on the Page Condition Audit sheet.",
        "encrypted": "The PDF is password protected and was not opened. No "
                     "password was attempted and the file was not modified.",
    }
    for row in rows:
        yield {
            "filename": row["filename"],
            "filename_bates": row["filename_bates"],
            "extraction_status": row["extraction_status"],
            "page_count": row["page_count"],
            "pages_audited": row["audited"],
            "error_message": row["error_message"],
            "suggested_action": actions.get(row["extraction_status"], ""),
            "abs_path": row["abs_path"],
        }


def iter_reference_rows() -> Iterator[Dict[str, Any]]:
    """Stream the classification reference sheet."""
    for value, meaning in CONDITION_MEANINGS.items():
        yield {"value": value, "kind": "Page condition", "meaning": meaning}
    for value, meaning in SUBTYPE_MEANINGS.items():
        yield {"value": value, "kind": "Blank / Bates-only subtype",
               "meaning": meaning}


def _compact_ranges(numbers: Sequence[int]) -> str:
    """Render a sorted page list as compact ranges, e.g. ``1-3, 7, 9-11``."""
    if not numbers:
        return ""
    parts: List[str] = []
    start = previous = numbers[0]
    for value in numbers[1:]:
        if value == previous + 1:
            previous = value
            continue
        parts.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = value
    parts.append(str(start) if start == previous else f"{start}-{previous}")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------
def generate_phase2_reports(
    config: Config,
    database: Database,
    output_dir: Path,
    source: Path,
    *,
    pilot: bool = True,
    sample_info: Optional[Dict[str, Any]] = None,
) -> List[Path]:
    """Write every Phase 2 output and return the paths written."""
    stats = database.get_stats()
    writer = ReportWriter(
        output_dir, source_root=source, settings=config.section("reports"),
        run_stats=stats,
    )
    written: List[Path] = []
    scope = "pilot sample" if pilot else "full production"
    note = (
        f"Page-condition audit over the {scope}. Classifications are derived "
        "by software from the PDF page content. No document text appears in "
        "this workbook."
    )

    written.append(
        writer.write_workbook(
            "05_Page_Condition_Audit.xlsx",
            [
                Sheet("Page Condition Audit", page_columns(),
                      iter_page_rows(database), note=note),
                Sheet("Condition Reference", reference_columns(),
                      iter_reference_rows(),
                      note="What each classification value means."),
            ],
        )
    )

    written.append(
        writer.write_workbook(
            "06_Blank_and_Bates_Only_Candidates.xlsx",
            [
                Sheet("Blank and Bates-Only", blank_columns(),
                      iter_blank_rows(database),
                      note="CANDIDATES ONLY. Each row needs human "
                           "confirmation. A page with no extractable text is "
                           "not necessarily blank."),
            ],
        )
    )

    written.append(
        writer.write_workbook(
            "07_OCR_Required.xlsx",
            [
                Sheet("OCR Required", ocr_columns(), iter_ocr_rows(database),
                      note="Documents with pages that have no usable text "
                           "layer but do have image content. OCR, if run, "
                           "writes a derivative to the cache folder; the "
                           "source PDF is never modified."),
            ],
        )
    )

    written.append(
        writer.write_workbook(
            "08_Extraction_Failures.xlsx",
            [
                Sheet("Extraction Failures", failure_columns(),
                      iter_failure_rows(database),
                      note="Documents that could not be fully read."),
            ],
        )
    )

    filename = "Phase_2_Pilot_Summary.md" if pilot else "Phase_2_Summary.md"
    written.append(
        writer.write_markdown(
            filename,
            build_phase2_summary(config, database, stats.get(PHASE, {}), source,
                                 output_dir, pilot=pilot, sample_info=sample_info),
        )
    )

    database.audit("phase2_reports", phase=PHASE, target=str(output_dir),
                   outcome="completed", detail={"files": [p.name for p in written]})
    return written


def build_phase2_summary(
    config: Config,
    database: Database,
    stats: Dict[str, Any],
    source: Path,
    output_dir: Path,
    *,
    pilot: bool,
    sample_info: Optional[Dict[str, Any]] = None,
) -> str:
    """Render the Phase 2 Markdown summary (aggregates only)."""
    conditions = stats.get("page_condition_counts", {}) or {}
    subtypes = stats.get("blank_subtype_counts", {}) or {}
    total_pages = sum(conditions.values()) or 1

    def condition_table() -> str:
        lines = ["| Page condition | Pages | Share |", "| --- | ---: | ---: |"]
        for key, count in sorted(conditions.items(), key=lambda kv: -kv[1]):
            lines.append(f"| `{key}` | {count:,} | {100 * count / total_pages:.1f}% |")
        return "\n".join(lines)

    def subtype_table() -> str:
        if not subtypes:
            return "_No blank or Bates-only pages were detected._"
        lines = ["| Subtype | Pages |", "| --- | ---: |"]
        for key, count in sorted(subtypes.items(), key=lambda kv: -kv[1]):
            lines.append(f"| `{key}` | {count:,} |")
        return "\n".join(lines)

    def strata_table() -> str:
        if not sample_info or not sample_info.get("strata"):
            return "_Not a stratified pilot run._"
        lines = ["| Stratum | Documents selected | Shortfall |",
                 "| --- | ---: | ---: |"]
        shortfalls = sample_info.get("shortfalls", {})
        for name, ids in sample_info["strata"].items():
            missing = shortfalls.get(name, 0)
            lines.append(
                f"| `{name}` | {len(ids):,} | "
                f"{missing if missing else '-'} |"
            )
        return "\n".join(lines)

    docs = stats.get("documents_processed", 0)
    failures = stats.get("extraction_failures", 0)
    accuracy_note = (
        "**Measured accuracy is not yet available.** Nothing in this run has "
        "been compared against a human-verified gold standard. The figures "
        "below are the classifier's own output, not its accuracy. Confirm the "
        "quality-control sample before processing the full production."
    )
    stop_note = (
        "\n---\n\n## Stop here\n\nThis was a **pilot** over a stratified "
        "sample, not the full production. Review the quality-control sample "
        "and the accuracy problems listed above before approving a full "
        "Phase 2 run.\n"
        if pilot
        else ""
    )

    return f"""# Phase 2 {"Pilot " if pilot else ""}Summary -- Text and Page-Condition Audit

**Generated:** {datetime.now(timezone.utc).isoformat(timespec="seconds")}
**Application:** {APP_NAME} {APP_VERSION}
**Source folder (read-only):** `{source}`
**Derived index folder:** `{output_dir}`
**Scope:** {"stratified pilot sample" if pilot else "full production"}

> **DERIVED REVIEW METADATA.** Page conditions below were classified by
> software from the PDF page content. They are not native metadata and are not
> a substitute for human review.

---

## What Phase 2 did

Native PDF text extraction was attempted for every page first. OCR was used
only where extraction was insufficient *and* the page held meaningful image
content. Any OCR ran locally and wrote its derivative to a cache inside the
derived-index folder. No source PDF was modified, annotated, or OCRed in
place. No document text appears in any workbook or in the terminal.

---

## Documents and pages

| Measure | Value |
| --- | ---: |
| Documents processed | {docs:,} |
| Pages audited | {stats.get('pages_audited', 0):,} |
| Documents with any extractable text | {stats.get('documents_with_any_text', 0):,} |
| Pages with a Bates stamp read from the page | {stats.get('pages_with_observed_bates', 0):,} |
| Extraction failures | {failures:,} |
| Pages needing OCR | {stats.get('pages_needing_ocr', 0):,} |
| Documents OCR completed | {stats.get('documents_ocr_completed', 0):,} |
| Documents OCR failed | {stats.get('documents_ocr_failed', 0):,} |

---

## Page conditions

{condition_table()}

### Blank and Bates-only subtypes

{subtype_table()}

Every row on the `06_Blank_and_Bates_Only_Candidates.xlsx` sheet is a
**candidate**. A page with no extractable text may be genuinely blank, may be
an image the extractor could not read, or may be a failed export. The workbook
states which explanation the evidence supports and what a reviewer should
check.

---

## Pilot sample composition

{strata_table()}

A shortfall means the collection did not contain enough documents matching
that stratum. It is recorded rather than silently ignored.

---

## Accuracy

{accuracy_note}

To measure accuracy, run `wri qc-sample --phase 2`, open the sampled pages,
and record how many classifications were correct. Report that measured figure
here before relying on the full run.

---

## Files produced

| File | Contents |
| --- | --- |
| `05_Page_Condition_Audit.xlsx` | Every page, with its condition and counts |
| `06_Blank_and_Bates_Only_Candidates.xlsx` | Blank / Bates-only candidates to verify |
| `07_OCR_Required.xlsx` | Documents with pages lacking a text layer |
| `08_Extraction_Failures.xlsx` | Documents that could not be fully read |
| `{'Phase_2_Pilot_Summary.md' if pilot else 'Phase_2_Summary.md'}` | This document |

---

## Known limitations

1. Image coverage is approximate. Overlapping images inflate it; the value is
   clipped at 100%.
2. A page classified `searchable` may still contain image content that holds
   information the text layer omits.
3. `uncertain` is used deliberately when evidence is insufficient. Those pages
   are not guesses and should be reviewed.
4. Bates stamps are read from the page footer region first. A stamp placed
   elsewhere, or rendered as an image without OCR, will not be detected.
{stop_note}"""
