"""Phase 3 report generation -- the derived document index and review queues.

Produces workbooks 09 through 20, ``Final_Run_Summary.md`` and
``Processing_Errors.xlsx``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from .bates import find_range_gaps_and_overlaps
from .config import Config
from .database import Database
from .logging_setup import get_logger
from .priority import DISCLAIMER
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

log = get_logger("phase3_reports")

PHASE = "phase3"

MASTER_NOTE = (
    "DERIVED REVIEW METADATA. Every column was derived by software from the "
    "produced PDFs. None of it is native metadata. Columns marked Inferred in "
    "the Data Dictionary are software guesses and must be verified. Issue tags "
    "are keyword screening hits, not legal conclusions. Priority scores order "
    "review work and prove nothing."
)

#: Review queues generated from issue tags: (filename, sheet name, tag, blurb).
REVIEW_QUEUES: Sequence[tuple] = (
    ("16_John_Wilson_Review_Queue.xlsx", "John Wilson", "JOHN_WILSON",
     "Documents where terms associated with John Wilson appeared."),
    ("17_Statute_of_Frauds_Review_Queue.xlsx", "Statute of Frauds",
     "STATUTE_OF_FRAUDS",
     "Documents where statute-of-frauds screening terms appeared."),
    ("18_Expert_and_Damages_Review_Queue.xlsx", "Expert and Damages",
     ("EXPERT_FAILURE", "DAMAGES"),
     "Documents where expert or damages screening terms appeared."),
    ("19_Client_File_Review_Queue.xlsx", "Client File", "CLIENT_FILE",
     "Documents where client-file and production screening terms appeared."),
    ("20_Insurance_Review_Queue.xlsx", "Insurance", "INSURANCE",
     "Documents where insurance and coverage screening terms appeared."),
)


# ---------------------------------------------------------------------------
# master index columns
# ---------------------------------------------------------------------------
def master_columns() -> List[Column]:
    """Columns for the derived document index."""
    return [
        Column("begin_bates", "Begin Bates", provenance=CALCULATED,
               description="First Bates number of the document. See Bates "
                           "Source for how it was obtained."),
        Column("end_bates", "End Bates", provenance=CALCULATED,
               description="Last Bates number of the document. May be "
                           "calculated arithmetically rather than observed."),
        Column("bates_confidence", "Bates Confidence", provenance=CALCULATED,
               description="confirmed / probable / possible / unknown."),
        Column("bates_source", "Bates Source", provenance=CALCULATED,
               description="observed_on_page (strongest), "
                           "parsed_from_filename, calculated, inferred, none."),
        Column("filename", "Filename", provenance=OBSERVED,
               description="Source file name."),
        Column("rel_path", "Relative Path", width=36, provenance=OBSERVED,
               description="Path relative to the source folder root."),
        Column("abs_path", "Local File Link", width=48, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the local source PDF."),
        Column("page_count", "Page Count", provenance=OBSERVED,
               number_format="#,##0", description="Pages in the PDF."),
        Column("file_size", "File Size (bytes)", provenance=OBSERVED,
               number_format="#,##0", description="Size in bytes."),
        Column("sha256", "File Hash (SHA-256)", width=44, provenance=CALCULATED,
               description="Digest of the file's bytes."),
        Column("document_date", "Document Date", provenance=INFERRED,
               description="Apparent date of the document, derived from its "
                           "text. Not a native date field."),
        Column("date_confidence", "Date Confidence", provenance=CALCULATED,
               description="high / medium / low / uncertain."),
        Column("date_source", "Date Source", provenance=CALCULATED,
               description="Which pattern or header supplied the date."),
        Column("email_from", "Author or From", provenance=OBSERVED,
               description="Sender from the top-level e-mail header, or the "
                           "derived author. Read from the page text."),
        Column("email_to", "To", width=34, wrap=True, provenance=OBSERVED,
               description="Recipients from the top-level header, "
                           "semicolon-delimited."),
        Column("email_cc", "CC", width=30, wrap=True, provenance=OBSERVED,
               description="CC recipients, semicolon-delimited."),
        Column("email_bcc", "BCC", width=24, wrap=True, provenance=OBSERVED,
               description="BCC recipients where the export shows them."),
        Column("subject_or_title", "Subject or Title", width=44, wrap=True,
               provenance=OBSERVED,
               description="E-mail subject where present, otherwise a title "
                           "derived from the first substantive line."),
        Column("document_type", "Document Type", provenance=INFERRED,
               description="Rule-based classification."),
        Column("doc_type_confidence", "Document Type Confidence",
               provenance=CALCULATED, number_format="0.000",
               description="0-1. Values below the configured threshold are "
                           "reported as 'unknown' rather than guessed."),
        Column("court_name", "Court", width=32, wrap=True, provenance=OBSERVED,
               description="Court name found in the text."),
        Column("case_number", "Case Number", provenance=OBSERVED,
               description="Case or docket number found in the text."),
        Column("parent_bates", "Parent Bates", provenance=INFERRED,
               description="INFERRED possible parent e-mail. Not native family "
                           "metadata. See workbook 13 for the reason."),
        Column("attachment_bates", "Attachment Bates", width=30, wrap=True,
               provenance=INFERRED,
               description="INFERRED possible attachments. Not native family "
                           "metadata."),
        Column("family_confidence", "Family Confidence", provenance=CALCULATED,
               description="confirmed / probable / possible / unknown for the "
                           "family inference."),
        Column("exact_dup_group", "Exact Duplicate Group", provenance=CALCULATED,
               description="Byte-identical group (SHA-256)."),
        Column("text_dup_group", "Text Duplicate Group", provenance=CALCULATED,
               description="Identical normalised text, different rendering."),
        Column("near_dup_group", "Near-Duplicate Group", provenance=CALCULATED,
               description="SimHash/LSH near-duplicate group."),
        Column("issue_tags", "Issue Tags", width=42, wrap=True,
               provenance=CALCULATED,
               description="Configured screening terms that matched, with hit "
                           "counts. SCREENING ONLY -- not legal conclusions."),
        Column("priority_score", "Priority Score", provenance=CALCULATED,
               number_format="0.00",
               description="Configurable review-ordering score. Proves nothing."),
        Column("priority_explanation", "Priority Score Explanation", width=60,
               wrap=True, provenance=CALCULATED,
               description="Every component that contributed to the score."),
        Column("searchable_status", "Searchable Status", provenance=CALCULATED,
               description="fully / partially searchable, or no text layer."),
        Column("ocr_status", "OCR Status", provenance=CALCULATED,
               description="Whether OCR was required, completed or failed."),
        Column("apparent_blank_status", "Apparent Blank Status",
               provenance=CALCULATED,
               description="Whether any page appeared blank or Bates-only."),
        Column("extraction_confidence", "Extraction Confidence",
               provenance=CALCULATED,
               description="How much of this row the parsers could support."),
        Column("manual_review_text", "Manual Review Required",
               provenance=CALCULATED,
               description="Yes when the record needs human verification "
                           "before it is relied upon."),
        Column("processing_notes", "Processing Notes", width=55, wrap=True,
               provenance=CALCULATED,
               description="How values were derived and what was uncertain."),
    ]


def _master_row(row) -> Dict[str, Any]:
    """Convert a joined documents/files row into master-index cells."""
    return {
        "begin_bates": row["begin_bates"],
        "end_bates": row["end_bates"],
        "bates_confidence": row["bates_confidence"],
        "bates_source": row["bates_source"],
        "filename": row["filename"],
        "rel_path": row["rel_path"],
        "abs_path": row["abs_path"],
        "page_count": row["page_count"],
        "file_size": row["file_size"],
        "sha256": row["sha256"],
        "document_date": row["document_date"],
        "date_confidence": row["date_confidence"],
        "date_source": row["date_source"],
        "email_from": row["email_from"] or row["author"],
        "email_to": row["email_to"],
        "email_cc": row["email_cc"],
        "email_bcc": row["email_bcc"],
        "subject_or_title": row["email_subject"] or row["title"],
        "document_type": row["document_type"],
        "doc_type_confidence": row["doc_type_confidence"],
        "court_name": row["court_name"],
        "case_number": row["case_number"],
        "parent_bates": row["parent_bates"],
        "attachment_bates": row["attachment_bates"],
        "family_confidence": row["family_confidence"],
        "exact_dup_group": row["exact_dup_group"],
        "text_dup_group": row["text_dup_group"],
        "near_dup_group": row["near_dup_group"],
        "issue_tags": row["issue_tags"],
        "priority_score": row["priority_score"],
        "priority_explanation": row["priority_explanation"],
        "searchable_status": row["searchable_status"],
        "ocr_status": row["ocr_status"],
        "apparent_blank_status": row["apparent_blank_status"],
        "extraction_confidence": row["extraction_confidence"],
        "manual_review_text": "Yes" if row["manual_review_required"] else "No",
        "processing_notes": row["processing_notes"],
    }


_MASTER_SQL = (
    "SELECT d.*, f.filename, f.rel_path, f.abs_path, f.file_size, f.sha256 "
    "FROM documents d JOIN files f ON f.file_id = d.file_id "
)


def iter_master_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream the master index in Bates order."""
    for row in database.iter_query(
        _MASTER_SQL + "ORDER BY d.begin_bates_num IS NULL, d.begin_bates_num, "
                      "f.filename"
    ):
        yield _master_row(row)


# ---------------------------------------------------------------------------
# other sheets
# ---------------------------------------------------------------------------
def gap_columns() -> List[Column]:
    """Columns for the Bates gap/overlap report."""
    return [
        Column("kind", "Finding", provenance=CALCULATED,
               description="Gap or Overlap."),
        Column("after", "Range Ends At", provenance=CALCULATED,
               number_format="#,##0", description="Numeric Bates."),
        Column("before", "Next Range Begins At", provenance=CALCULATED,
               number_format="#,##0", description="Numeric Bates."),
        Column("missing_count", "Bates Numbers Affected", provenance=CALCULATED,
               number_format="#,##0",
               description="How many numbers fall in the gap or overlap."),
        Column("basis", "Basis", provenance=CALCULATED,
               description="Whether the finding rests on observed page stamps "
                           "or on calculated ranges."),
        Column("note", "How to Read This", width=70, wrap=True,
               provenance=INFERRED,
               description="What the finding does and does not establish."),
    ]


def iter_gap_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream document-level Bates gaps and overlaps."""
    rows = database.query(
        "SELECT f.filename, d.begin_bates_num, d.end_bates_num, d.bates_source "
        "FROM documents d JOIN files f ON f.file_id = d.file_id "
        "WHERE d.begin_bates_num IS NOT NULL"
    )
    ranges = [(row["filename"], row["begin_bates_num"], row["end_bates_num"])
              for row in rows]
    observed_share = sum(
        1 for row in rows if row["bates_source"] == "observed_on_page"
    ) / max(1, len(rows))
    basis = (
        "observed page stamps (majority)" if observed_share >= 0.5
        else "calculated ranges (majority) -- weaker evidence"
    )
    gaps, overlaps = find_range_gaps_and_overlaps(ranges)
    for gap in gaps:
        yield {
            "kind": "Gap",
            "after": gap.after,
            "before": gap.before,
            "missing_count": gap.missing_count,
            "basis": basis,
            "note": "No document in the index claims these Bates numbers. "
                    "Where the surrounding ranges were calculated rather than "
                    "observed, this may reflect a calculation assumption "
                    "rather than a true production gap.",
        }
    for overlap in overlaps:
        yield {
            "kind": "Overlap",
            "after": overlap.overlap_start,
            "before": overlap.overlap_end,
            "missing_count": overlap.overlap_end - overlap.overlap_start + 1,
            "basis": basis,
            "note": f"'{overlap.first_label}' and '{overlap.second_label}' both "
                    "claim these numbers. Usually means an end Bates was "
                    "calculated from a page count that overstated the "
                    "document's true span.",
        }


def duplicate_group_columns() -> List[Column]:
    """Columns for the duplicate-groups workbook."""
    return [
        Column("group_kind", "Duplicate Kind", provenance=CALCULATED,
               description="exact_binary, normalized_text or near_duplicate."),
        Column("group_id", "Group", provenance=CALCULATED,
               description="Group identifier."),
        Column("relation", "Relationship", provenance=INFERRED,
               description="Why these documents resemble each other."),
        Column("similarity", "Similarity", provenance=CALCULATED,
               number_format="0.0",
               description="Token-set similarity (0-100). 100 for exact "
                           "matches."),
        Column("begin_bates", "Begin Bates", provenance=CALCULATED,
               description="Document's begin Bates."),
        Column("filename", "Filename", provenance=OBSERVED,
               description="Source file name."),
        Column("document_type", "Document Type", provenance=INFERRED,
               description="Rule-based classification."),
        Column("page_count", "Pages", provenance=OBSERVED, number_format="#,##0",
               description="Pages in the PDF."),
        Column("abs_path", "Local File Link", width=48, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the local source PDF."),
    ]


def iter_duplicate_group_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream every duplicate-group membership row."""
    for row in database.iter_query(
        "SELECT m.group_kind, m.group_id, m.relation, m.similarity, "
        "f.filename, f.abs_path, f.page_count, d.begin_bates, d.document_type "
        "FROM duplicate_members m JOIN files f ON f.file_id = m.file_id "
        "LEFT JOIN documents d ON d.file_id = m.file_id "
        "ORDER BY m.group_kind, m.group_id, d.begin_bates_num"
    ):
        yield {
            "group_kind": row["group_kind"],
            "group_id": row["group_id"],
            "relation": row["relation"],
            "similarity": row["similarity"],
            "begin_bates": row["begin_bates"],
            "filename": row["filename"],
            "document_type": row["document_type"],
            "page_count": row["page_count"],
            "abs_path": row["abs_path"],
        }


def family_columns() -> List[Column]:
    """Columns for the family-inference workbook."""
    return [
        Column("parent_bates", "Parent Bates", provenance=INFERRED,
               description="Begin Bates of the possible parent e-mail."),
        Column("child_bates", "Child Bates", provenance=INFERRED,
               description="Begin Bates of the possible attachment."),
        Column("relationship", "Relationship Type", provenance=INFERRED,
               description="Always phrased as 'possible'. Never native family "
                           "metadata."),
        Column("confidence", "Confidence", provenance=CALCULATED,
               description="confirmed / probable / possible / unknown."),
        Column("reason", "Reason for the Inference", width=80, wrap=True,
               provenance=INFERRED,
               description="The specific signals that produced this "
                           "relationship. Read this before relying on the row."),
        Column("parent_filename", "Parent Filename", provenance=OBSERVED,
               description="Source file of the possible parent."),
        Column("child_filename", "Child Filename", provenance=OBSERVED,
               description="Source file of the possible attachment."),
        Column("parent_path", "Parent File Link", width=44, wrap=True,
               provenance=OBSERVED, hyperlink_from="parent_path",
               description="Clickable link to the parent PDF."),
        Column("child_path", "Child File Link", width=44, wrap=True,
               provenance=OBSERVED, hyperlink_from="child_path",
               description="Clickable link to the child PDF."),
    ]


def iter_family_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream inferred family relationships."""
    for row in database.iter_query(
        "SELECT fa.*, pf.filename AS parent_filename, pf.abs_path AS parent_path, "
        "cf.filename AS child_filename, cf.abs_path AS child_path "
        "FROM families fa "
        "LEFT JOIN files pf ON pf.file_id = fa.parent_file_id "
        "LEFT JOIN files cf ON cf.file_id = fa.child_file_id "
        "ORDER BY fa.parent_bates, fa.child_bates"
    ):
        yield {
            "parent_bates": row["parent_bates"],
            "child_bates": row["child_bates"],
            "relationship": row["relationship"],
            "confidence": row["confidence"],
            "reason": row["reason"],
            "parent_filename": row["parent_filename"],
            "child_filename": row["child_filename"],
            "parent_path": row["parent_path"],
            "child_path": row["child_path"],
        }


def issue_columns(include_locator: bool) -> List[Column]:
    """Columns for the issue-tag index."""
    columns = [
        Column("tag", "Issue Tag", provenance=CALCULATED,
               description="Configured screening category. NOT a legal "
                           "conclusion."),
        Column("term", "Matching Term", provenance=OBSERVED,
               description="The configured term that actually matched."),
        Column("begin_bates", "Begin Bates", provenance=CALCULATED,
               description="Document's begin Bates."),
        Column("filename", "Filename", provenance=OBSERVED,
               description="Source file name."),
        Column("page_number", "Page", provenance=OBSERVED, number_format="#,##0",
               description="Page the term appeared on."),
        Column("hit_count", "Hits on Page", provenance=CALCULATED,
               number_format="#,##0",
               description="How many times the term appeared on that page."),
        Column("document_type", "Document Type", provenance=INFERRED,
               description="Rule-based classification."),
        Column("priority_score", "Priority Score", provenance=CALCULATED,
               number_format="0.00", description="Review-ordering score."),
        Column("abs_path", "Local File Link", width=48, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the local source PDF."),
    ]
    if include_locator:
        columns.insert(
            6,
            Column("locator", "Context Locator", width=52, wrap=True,
                   provenance=OBSERVED,
                   description="Short surrounding text to help locate the hit. "
                               "Enabled because issue_tag_options."
                               "redact_context_in_excel is false."),
        )
    return columns


def iter_issue_rows(database: Database, include_locator: bool) -> Iterator[Dict[str, Any]]:
    """Stream issue-tag hits joined to document context."""
    for row in database.iter_query(
        "SELECT h.*, f.filename, f.abs_path, d.begin_bates, d.begin_bates_num, "
        "d.document_type, d.priority_score "
        "FROM issue_hits h JOIN files f ON f.file_id = h.file_id "
        "LEFT JOIN documents d ON d.file_id = h.file_id "
        "ORDER BY h.tag, d.priority_score DESC, d.begin_bates_num, h.page_number"
    ):
        entry = {
            "tag": row["tag"],
            "term": row["term"],
            "begin_bates": row["begin_bates"],
            "filename": row["filename"],
            "page_number": row["page_number"],
            "hit_count": row["hit_count"],
            "document_type": row["document_type"],
            "priority_score": row["priority_score"],
            "abs_path": row["abs_path"],
        }
        if include_locator:
            entry["locator"] = row["locator"]
        yield entry


def queue_columns() -> List[Column]:
    """Columns for a review queue."""
    return [
        Column("priority_score", "Priority Score", provenance=CALCULATED,
               number_format="0.00",
               description="Review-ordering score. Higher means look sooner. "
                           "Proves nothing."),
        Column("begin_bates", "Begin Bates", provenance=CALCULATED,
               description="Document's begin Bates."),
        Column("end_bates", "End Bates", provenance=CALCULATED,
               description="Document's end Bates."),
        Column("filename", "Filename", provenance=OBSERVED,
               description="Source file name."),
        Column("document_date", "Document Date", provenance=INFERRED,
               description="Apparent date derived from the text."),
        Column("document_type", "Document Type", provenance=INFERRED,
               description="Rule-based classification."),
        Column("email_from", "Author or From", provenance=OBSERVED,
               description="Sender or derived author."),
        Column("subject_or_title", "Subject or Title", width=44, wrap=True,
               provenance=OBSERVED, description="Subject, or a derived title."),
        Column("issue_tags", "Issue Tags", width=40, wrap=True,
               provenance=CALCULATED,
               description="Screening tags that matched, with hit counts."),
        Column("page_count", "Pages", provenance=OBSERVED, number_format="#,##0",
               description="Pages in the PDF."),
        Column("manual_review_text", "Manual Review Required",
               provenance=CALCULATED,
               description="Yes when the derived record needs verification."),
        Column("priority_explanation", "Why It Scored This", width=58, wrap=True,
               provenance=CALCULATED,
               description="Every component that contributed to the score."),
        Column("abs_path", "Local File Link", width=48, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the local source PDF."),
    ]


def iter_queue_rows(
    database: Database,
    *,
    tags: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
) -> Iterator[Dict[str, Any]]:
    """Stream a priority-ordered review queue, optionally filtered by tag."""
    params: List[Any] = []
    where = ""
    if tags:
        placeholders = ",".join("?" * len(tags))
        where = (
            f"WHERE d.file_id IN (SELECT file_id FROM issue_hits "
            f"WHERE tag IN ({placeholders})) "
        )
        params.extend(tags)
    sql = (
        _MASTER_SQL + where +
        "ORDER BY d.priority_score DESC, d.begin_bates_num"
    )
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    for row in database.iter_query(sql, params):
        base = _master_row(row)
        yield {
            "priority_score": base["priority_score"],
            "begin_bates": base["begin_bates"],
            "end_bates": base["end_bates"],
            "filename": base["filename"],
            "document_date": base["document_date"],
            "document_type": base["document_type"],
            "email_from": base["email_from"],
            "subject_or_title": base["subject_or_title"],
            "issue_tags": base["issue_tags"],
            "page_count": base["page_count"],
            "manual_review_text": base["manual_review_text"],
            "priority_explanation": base["priority_explanation"],
            "abs_path": base["abs_path"],
        }


def blank_failure_columns() -> List[Column]:
    """Columns for the blank / extraction-failure roll-up."""
    return [
        Column("begin_bates", "Begin Bates", provenance=CALCULATED,
               description="Document's begin Bates."),
        Column("filename", "Filename", provenance=OBSERVED,
               description="Source file name."),
        Column("condition", "Condition", provenance=CALCULATED,
               description="Why the document appears on this sheet."),
        Column("apparent_blank_status", "Apparent Blank Status",
               provenance=CALCULATED,
               description="Whether some or all pages appeared blank."),
        Column("searchable_status", "Searchable Status", provenance=CALCULATED,
               description="Whether a usable text layer was found."),
        Column("page_count", "Pages", provenance=OBSERVED, number_format="#,##0",
               description="Pages in the PDF."),
        Column("blank_pages", "Blank / Bates-Only Pages", provenance=CALCULATED,
               number_format="#,##0",
               description="Count of pages classified blank or Bates-only."),
        Column("processing_notes", "Notes", width=55, wrap=True,
               provenance=CALCULATED, description="Derivation notes."),
        Column("abs_path", "Local File Link", width=48, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the local source PDF."),
    ]


def iter_blank_failure_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream documents that are blank-heavy or failed extraction."""
    for row in database.iter_query(
        "SELECT d.*, f.filename, f.abs_path, f.extraction_status, "
        "(SELECT COUNT(*) FROM pages p WHERE p.file_id = d.file_id "
        " AND p.page_condition IN ('apparent_blank','bates_only')) AS blanks "
        "FROM documents d JOIN files f ON f.file_id = d.file_id "
        "WHERE d.apparent_blank_status != 'no_blank_pages_detected' "
        "   OR f.extraction_status IN ('failed','partial','encrypted') "
        "ORDER BY d.begin_bates_num"
    ):
        if row["extraction_status"] in ("failed", "partial", "encrypted"):
            condition = f"Extraction {row['extraction_status']}"
        elif row["apparent_blank_status"] == "all_pages_blank_or_bates_only":
            condition = "All pages appear blank or Bates-only"
        else:
            condition = "Some pages appear blank or Bates-only"
        yield {
            "begin_bates": row["begin_bates"],
            "filename": row["filename"],
            "condition": condition,
            "apparent_blank_status": row["apparent_blank_status"],
            "searchable_status": row["searchable_status"],
            "page_count": row["page_count"],
            "blank_pages": row["blanks"],
            "processing_notes": row["processing_notes"],
            "abs_path": row["abs_path"],
        }


def error_columns() -> List[Column]:
    """Columns for the processing-errors workbook."""
    return [
        Column("filename", "Filename", provenance=OBSERVED,
               description="Source file name."),
        Column("rel_path", "Relative Path", width=36, provenance=OBSERVED,
               description="Path relative to the source folder root."),
        Column("processing_status", "Processing Status", provenance=CALCULATED,
               description="Pipeline state."),
        Column("extraction_status", "Extraction Status", provenance=CALCULATED,
               description="Text-extraction outcome."),
        Column("ocr_status", "OCR Status", provenance=CALCULATED,
               description="OCR outcome."),
        Column("error_message", "Error", width=60, wrap=True,
               provenance=CALCULATED,
               description="Diagnostic detail. Never contains document text."),
        Column("last_processed_ts", "Last Attempt (UTC)", provenance=CALCULATED,
               description="When the file was last processed."),
        Column("abs_path", "Local File Link", width=48, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the local source file."),
    ]


def iter_error_rows(database: Database) -> Iterator[Dict[str, Any]]:
    """Stream every file in an error or unfinished state."""
    for row in database.iter_query(
        "SELECT * FROM files WHERE processing_status IN "
        "('error','cloud_placeholder','pending') "
        "OR extraction_status IN ('failed','partial','encrypted') "
        "OR ocr_status = 'failed' ORDER BY filename_bates_num, filename"
    ):
        yield {
            "filename": row["filename"],
            "rel_path": row["rel_path"],
            "processing_status": row["processing_status"],
            "extraction_status": row["extraction_status"],
            "ocr_status": row["ocr_status"],
            "error_message": row["error_message"],
            "last_processed_ts": row["last_processed_ts"],
            "abs_path": row["abs_path"],
        }


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------
def generate_phase3_reports(
    config: Config, database: Database, output_dir: Path, source: Path
) -> List[Path]:
    """Write every Phase 3 output and return the paths written."""
    stats = database.get_stats()
    writer = ReportWriter(
        output_dir, source_root=source, settings=config.section("reports"),
        run_stats=stats,
    )
    include_locator = not bool(
        config.get("issue_tag_options", "redact_context_in_excel", default=True)
    )
    written: List[Path] = []
    columns = master_columns()

    written.append(
        writer.write_workbook(
            "09_Derived_Document_Index.xlsx",
            [Sheet("Derived Document Index", columns, iter_master_rows(database),
                   note=MASTER_NOTE)],
        )
    )
    written.append(
        writer.write_csv("09_Derived_Document_Index.csv", columns,
                         iter_master_rows(database))
    )

    written.append(
        writer.write_workbook(
            "10_Bates_Gap_and_Overlap_Report.xlsx",
            [Sheet("Gaps and Overlaps", gap_columns(), iter_gap_rows(database),
                   note="Derived from document-level begin/end Bates ranges. "
                        "Where an end Bates was calculated rather than "
                        "observed, findings here inherit that assumption.")],
        )
    )

    written.append(
        writer.write_workbook(
            "11_Blank_and_Extraction_Failure_Report.xlsx",
            [Sheet("Blank and Failures", blank_failure_columns(),
                   iter_blank_failure_rows(database),
                   note="Documents with blank/Bates-only pages or incomplete "
                        "extraction. Each needs human confirmation.")],
        )
    )

    written.append(
        writer.write_workbook(
            "12_Duplicate_Groups.xlsx",
            [Sheet("Duplicate Groups", duplicate_group_columns(),
                   iter_duplicate_group_rows(database),
                   note="Three independent passes: byte-identical (SHA-256), "
                        "identical normalised text, and SimHash near "
                        "duplicates. The Relationship column says which.")],
        )
    )

    written.append(
        writer.write_workbook(
            "13_Document_Family_Inferences.xlsx",
            [Sheet("Family Inferences", family_columns(), iter_family_rows(database),
                   note="EVERY ROW IS AN INFERENCE. This production has no load "
                        "file, so no native family metadata exists. Read the "
                        "Reason column before relying on any relationship.")],
        )
    )

    written.append(
        writer.write_workbook(
            "14_Issue_Tag_Index.xlsx",
            [Sheet("Issue Tag Index", issue_columns(include_locator),
                   iter_issue_rows(database, include_locator),
                   note="Issue tags are keyword screening hits. They are NOT "
                        "legal conclusions, relevance determinations, or "
                        "privilege calls.")],
        )
    )

    written.append(
        writer.write_workbook(
            "15_Priority_Review_Queue.xlsx",
            [Sheet("Priority Review Queue", queue_columns(),
                   iter_queue_rows(database),
                   note=f"Ordered by priority score, highest first. {DISCLAIMER}")],
        )
    )

    for filename, sheet_name, tag, blurb in REVIEW_QUEUES:
        tags = (tag,) if isinstance(tag, str) else tuple(tag)
        written.append(
            writer.write_workbook(
                filename,
                [Sheet(sheet_name, queue_columns(),
                       iter_queue_rows(database, tags=tags),
                       note=f"{blurb} {DISCLAIMER}")],
            )
        )

    written.append(
        writer.write_workbook(
            "Processing_Errors.xlsx",
            [Sheet("Processing Errors", error_columns(), iter_error_rows(database),
                   note="Every file that did not complete cleanly. Re-run "
                        "`wri retry-failed` after addressing the cause.")],
        )
    )

    written.append(
        writer.write_markdown(
            "Final_Run_Summary.md",
            build_final_summary(config, database, stats, source, output_dir),
        )
    )

    database.audit("phase3_reports", phase=PHASE, target=str(output_dir),
                   outcome="completed", detail={"files": [p.name for p in written]})
    return written


def build_final_summary(
    config: Config,
    database: Database,
    stats: Dict[str, Any],
    source: Path,
    output_dir: Path,
) -> str:
    """Render the final run summary (aggregates only)."""
    phase1 = stats.get("phase1", {})
    phase2 = stats.get("phase2", {})
    phase3 = stats.get("phase3", {})

    def dict_table(data: Dict[str, Any], head: str, limit: int = 20) -> str:
        if not data:
            return "_None recorded._"
        lines = [f"| {head} | Documents |", "| --- | ---: |"]
        for key, value in sorted(data.items(), key=lambda kv: -kv[1])[:limit]:
            lines.append(f"| `{key}` | {value:,} |")
        return "\n".join(lines)

    total_docs = phase3.get("documents_with_metadata", 0) or 1
    manual = phase3.get("documents_flagged_manual_review", 0)

    return f"""# Final Run Summary -- Derived Document Index

**Generated:** {datetime.now(timezone.utc).isoformat(timespec="seconds")}
**Application:** {APP_NAME} {APP_VERSION}
**Source folder (read-only):** `{source}`
**Derived index folder:** `{output_dir}`

> **DERIVED REVIEW METADATA.** Every value in every report was derived by
> software from the produced PDFs. None of it is original or native document
> metadata. The production included no CSV, DAT, OPT or native-file index, so
> none was available.

---

## Collection

| Measure | Value |
| --- | ---: |
| Total files inventoried | {phase1.get('total_files', 0):,} |
| PDF files | {phase1.get('pdf_files', 0):,} |
| Total storage | {format_bytes(phase1.get('total_bytes', 0))} |
| Pages audited | {phase2.get('pages_audited', 0):,} |
| Documents with derived metadata | {phase3.get('documents_with_metadata', 0):,} |

## Bates confidence

{dict_table(phase3.get('bates_confidence_counts', {}), 'Confidence')}

`observed_on_page` is the strongest evidence available. `calculated` values
assume one Bates number per page starting at the filename Bates; that
assumption has not been independently verified.

## Document types

{dict_table(phase3.get('document_type_counts', {}), 'Type')}

Types are rule-based classifications with confidence scores. Documents below
the configured confidence threshold are reported as `unknown` rather than
guessed.

## Issue tags

{dict_table(phase3.get('documents_per_issue_tag', {}), 'Tag')}

**Issue tags are screening tools only.** A tag means a configured term
appeared in the text. It is not a legal conclusion, a relevance determination,
or a privilege call.

## Duplicates

| Measure | Value |
| --- | ---: |
| Exact (byte-identical) duplicate groups | {phase1.get('exact_duplicate_groups', 0):,} |
| Identical normalised-text groups | {phase3.get('normalized_text_duplicate_groups', 0):,} |
| Near-duplicate groups | {phase3.get('near_duplicate_groups', 0):,} |

## Families

| Measure | Value |
| --- | ---: |
| Possible parent/attachment relationships inferred | {phase3.get('family_relationships_inferred', 0):,} |

**Every family relationship is an inference.** Each row in
`13_Document_Family_Inferences.xlsx` states the signals that produced it.

## Quality

| Measure | Value |
| --- | ---: |
| Documents flagged for manual review | {manual:,} ({100 * manual / total_docs:.1f}%) |
| Extraction failures | {phase2.get('extraction_failures', 0):,} |
| Pages still needing OCR | {phase2.get('pages_needing_ocr', 0):,} |
| Encrypted PDFs (not opened) | {phase1.get('encrypted_pdfs', 0):,} |
| Corrupt or unreadable files | {phase1.get('corrupt_or_unreadable', 0):,} |
| Cloud placeholders not downloaded | {phase1.get('cloud_placeholders', 0):,} |

---

## Accuracy and what this does not establish

No claim of perfect accuracy is made. Accuracy was not measured against a
human-verified gold standard except where a pilot accuracy figure has been
recorded and reported separately.

This index does **not** establish:

* that any document is relevant, privileged, responsive or admissible;
* that any Bates gap represents a withheld or missing document;
* that any inferred family relationship is correct;
* that a high priority score indicates malpractice, breach or liability.

Run `wri qc-sample` and inspect the sampled rows before relying on the index.

---

## Reports produced

| File | Contents |
| --- | --- |
| `09_Derived_Document_Index.xlsx` / `.csv` | Master index, one row per document |
| `10_Bates_Gap_and_Overlap_Report.xlsx` | Gaps and overlaps across derived ranges |
| `11_Blank_and_Extraction_Failure_Report.xlsx` | Blank-heavy and failed documents |
| `12_Duplicate_Groups.xlsx` | All three duplicate passes |
| `13_Document_Family_Inferences.xlsx` | Inferred parent/attachment relationships |
| `14_Issue_Tag_Index.xlsx` | Every issue-tag hit with page and count |
| `15_Priority_Review_Queue.xlsx` | Whole production, priority-ordered |
| `16`-`20_*_Review_Queue.xlsx` | Tag-specific review queues |
| `Processing_Errors.xlsx` | Everything that did not complete cleanly |
| `Final_Run_Summary.md` | This document |
| `wilson_rode_index.sqlite` | Processing database with FTS5 text search |
"""
