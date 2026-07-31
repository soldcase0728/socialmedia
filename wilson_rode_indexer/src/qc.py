"""Quality-control sampling.

Produces a reproducible, stratified sample for human inspection after each
phase.  The sample is the only honest way to state how accurate the derived
metadata is, so the workbook it produces contains a blank verdict column for
the reviewer to fill in and a place to record the resulting accuracy.

The random seed is fixed in ``config.yaml`` so a sample can be regenerated and
audited.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from .config import Config
from .database import Database
from .logging_setup import get_logger
from .reports import CALCULATED, Column, INFERRED, OBSERVED, ReportWriter, Sheet

log = get_logger("qc")


@dataclass
class QcStratum:
    """One QC stratum: a label, the SQL that finds candidates, and a quota."""

    name: str
    sql: str
    quota: int
    what_to_check: str
    rows: List[Dict[str, Any]] = field(default_factory=list)


def _strata(config: Config) -> List[QcStratum]:
    """Build the configured QC strata."""
    settings = config.section("qc")
    return [
        QcStratum(
            "high_priority",
            "SELECT d.file_id FROM documents d ORDER BY d.priority_score DESC "
            "LIMIT ?",
            int(settings.get("high_priority", 50)),
            "Open the document. Does the derived type, date, sender and "
            "subject match what you see? Do the issue tags make sense?",
        ),
        QcStratum(
            "low_priority",
            "SELECT d.file_id FROM documents d WHERE d.priority_score IS NOT NULL "
            "ORDER BY d.priority_score ASC LIMIT ?",
            int(settings.get("low_priority", 50)),
            "Confirm the document really is low-value. A misclassified "
            "document buried at low priority is the costliest failure mode.",
        ),
        QcStratum(
            "ocr",
            "SELECT DISTINCT p.file_id FROM pages p WHERE p.ocr_status IN "
            "('completed','required','failed') ORDER BY RANDOM() LIMIT ?",
            int(settings.get("ocr", 25)),
            "Compare the OCR text against the page image. Is the text usable "
            "for searching, or did OCR mangle it?",
        ),
        QcStratum(
            "blank_candidates",
            "SELECT DISTINCT p.file_id FROM pages p WHERE p.page_condition IN "
            "('apparent_blank','bates_only') ORDER BY RANDOM() LIMIT ?",
            int(settings.get("blank_candidates", 25)),
            "Open the flagged page. Is it genuinely blank, a Bates-only "
            "backside, a separator, or a failed export?",
        ),
        QcStratum(
            "family_inferences",
            "SELECT DISTINCT fa.child_file_id AS file_id FROM families fa "
            "ORDER BY RANDOM() LIMIT ?",
            int(settings.get("family_inferences", 25)),
            "Open the parent and the child. Is the child actually an "
            "attachment of that e-mail?",
        ),
        QcStratum(
            "near_duplicates",
            "SELECT DISTINCT m.file_id FROM duplicate_members m "
            "WHERE m.group_kind = 'near_duplicate' ORDER BY RANDOM() LIMIT ?",
            int(settings.get("near_duplicates", 25)),
            "Compare against the other members of the group. Are they really "
            "near duplicates, or is one an unrelated document?",
        ),
    ]


def qc_columns() -> List[Column]:
    """Columns for the QC workbook."""
    return [
        Column("stratum", "QC Stratum", provenance=CALCULATED,
               description="Which sampling category this row came from."),
        Column("what_to_check", "What to Check", width=56, wrap=True,
               provenance=CALCULATED,
               description="The specific question this row is meant to answer."),
        Column("begin_bates", "Begin Bates", provenance=CALCULATED,
               description="Document's begin Bates."),
        Column("filename", "Filename", provenance=OBSERVED,
               description="Source file name."),
        Column("document_type", "Derived Document Type", provenance=INFERRED,
               description="What the classifier decided."),
        Column("doc_type_confidence", "Type Confidence", provenance=CALCULATED,
               number_format="0.000", description="0-1 classifier confidence."),
        Column("document_date", "Derived Date", provenance=INFERRED,
               description="Apparent date derived from the text."),
        Column("email_from", "Derived From", provenance=OBSERVED,
               description="Sender parsed from the header block."),
        Column("subject_or_title", "Derived Subject or Title", width=40,
               wrap=True, provenance=OBSERVED,
               description="Subject, or a title derived from the text."),
        Column("issue_tags", "Issue Tags", width=36, wrap=True,
               provenance=CALCULATED, description="Screening tags that matched."),
        Column("priority_score", "Priority Score", provenance=CALCULATED,
               number_format="0.00", description="Review-ordering score."),
        Column("bates_confidence", "Bates Confidence", provenance=CALCULATED,
               description="How the Bates range was established."),
        Column("verdict", "REVIEWER: Correct? (Yes / No / Partly)",
               provenance=OBSERVED,
               description="TO BE FILLED IN BY A HUMAN. Leave blank until "
                           "reviewed."),
        Column("reviewer_notes", "REVIEWER: Notes", width=48, wrap=True,
               provenance=OBSERVED,
               description="TO BE FILLED IN BY A HUMAN. What was wrong, if "
                           "anything."),
        Column("abs_path", "Local File Link", width=48, wrap=True,
               provenance=OBSERVED, hyperlink_from="abs_path",
               description="Clickable link to the local source PDF."),
    ]


def build_qc_sample(config: Config, database: Database) -> List[Dict[str, Any]]:
    """Select the QC sample and return its rows.

    Documents already chosen for an earlier stratum are not chosen again, so
    the sample covers as many distinct documents as the collection allows.
    """
    seed = int(config.get("qc", "random_seed", default=20260731))
    random.seed(seed)
    database.execute("SELECT 1")  # ensure the connection is live

    chosen: set[int] = set()
    rows: List[Dict[str, Any]] = []
    for stratum in _strata(config):
        candidates = database.query(stratum.sql, (stratum.quota * 4,))
        picked = 0
        for candidate in candidates:
            if picked >= stratum.quota:
                break
            file_id = candidate["file_id"]
            if file_id in chosen:
                continue
            detail = database.query_one(
                "SELECT d.*, f.filename, f.abs_path FROM documents d "
                "JOIN files f ON f.file_id = d.file_id WHERE d.file_id = ?",
                (file_id,),
            )
            if detail is None:
                continue
            chosen.add(file_id)
            picked += 1
            rows.append(
                {
                    "stratum": stratum.name,
                    "what_to_check": stratum.what_to_check,
                    "begin_bates": detail["begin_bates"],
                    "filename": detail["filename"],
                    "document_type": detail["document_type"],
                    "doc_type_confidence": detail["doc_type_confidence"],
                    "document_date": detail["document_date"],
                    "email_from": detail["email_from"] or detail["author"],
                    "subject_or_title": detail["email_subject"] or detail["title"],
                    "issue_tags": detail["issue_tags"],
                    "priority_score": detail["priority_score"],
                    "bates_confidence": detail["bates_confidence"],
                    "verdict": None,
                    "reviewer_notes": None,
                    "abs_path": detail["abs_path"],
                }
            )
        if picked < stratum.quota:
            log.warning(
                "QC stratum %r short by %d document(s); the collection did not "
                "contain enough matching documents",
                stratum.name, stratum.quota - picked,
            )
    log.info("QC sample: %d document(s) across %d strata", len(rows),
             len({r['stratum'] for r in rows}))
    return rows


def generate_qc_workbook(
    config: Config, database: Database, output_dir: Path, source: Path
) -> Path:
    """Write the QC sample workbook and return its path."""
    rows = build_qc_sample(config, database)
    writer = ReportWriter(
        output_dir, source_root=source, settings=config.section("reports"),
        run_stats=database.get_stats(),
    )
    seed = int(config.get("qc", "random_seed", default=20260731))
    note = (
        "QUALITY-CONTROL SAMPLE. Open each document and fill in the two "
        "REVIEWER columns. Accuracy is only knowable once this is done -- the "
        f"tool makes no accuracy claim on its own. Sampling seed: {seed} "
        "(fixed, so this sample is reproducible and auditable)."
    )
    path = writer.write_workbook(
        "QC_Sample.xlsx",
        [
            Sheet("QC Sample", qc_columns(), iter(rows), note=note),
            Sheet("How to Score This", _instruction_columns(),
                  iter(_instruction_rows()),
                  note="Fill in the sheet, then compute accuracy per stratum."),
        ],
    )
    database.audit("qc_sample", target=str(path), outcome="completed",
                   detail={"rows": len(rows), "seed": seed})
    return path


def _instruction_columns() -> List[Column]:
    """Columns for the QC instruction sheet."""
    return [
        Column("step", "Step", provenance=CALCULATED, description="Order of work."),
        Column("action", "Action", width=90, wrap=True, provenance=CALCULATED,
               description="What to do."),
    ]


def _instruction_rows() -> List[Dict[str, Any]]:
    """Instruction rows explaining how to score the QC sample."""
    return [
        {"step": 1, "action": "Open each row's source PDF using the link in the "
                              "last column. The file opens read-only; nothing "
                              "you do in a viewer changes the index."},
        {"step": 2, "action": "Read the 'What to Check' column. It states the "
                              "specific question that row was sampled to "
                              "answer."},
        {"step": 3, "action": "Enter Yes, No, or Partly in the verdict column. "
                              "Use Partly when some derived fields are right "
                              "and others are wrong."},
        {"step": 4, "action": "In the notes column, record which specific field "
                              "was wrong. 'Date wrong, it is the fax date not "
                              "the letter date' is useful; 'bad' is not."},
        {"step": 5, "action": "Compute accuracy per stratum: count of Yes "
                              "divided by count of reviewed rows. Report that "
                              "figure. Do not report an accuracy figure that "
                              "was not measured this way."},
        {"step": 6, "action": "If a stratum scores poorly, adjust the relevant "
                              "section of config.yaml (classification rules, "
                              "thresholds, issue terms) and re-run that phase. "
                              "The run is resumable and re-scoring is cheap."},
    ]
