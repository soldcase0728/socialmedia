"""Tests for page-count extraction, resume behaviour and family inference.

Every PDF used here is synthesised inside a temporary directory by the
``make_pdf`` fixture.  No real document is read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.database import (
    STATUS_INVENTORIED,
    STATUS_METADATA_DONE,
    STATUS_PAGES_DONE,
)
from src.document_family import (
    FamilyCandidate,
    infer_families,
    normalize_filename,
    normalize_subject,
)
from src.inventory import probe_pdf, run_phase1
from src.pdf_extract import (
    COND_APPARENT_BLANK,
    COND_SEARCHABLE,
    ExtractionThresholds,
    extract_document,
)
from src.bates import BatesParser


class TestPageCountExtraction:
    """Page counts read from real (synthetic) PDFs."""

    @pytest.mark.parametrize("page_count", [1, 2, 5, 12])
    def test_reads_the_correct_page_count(self, tmp_path, make_pdf, page_count):
        path = make_pdf(tmp_path / "doc.pdf", [f"page {i}" for i in range(page_count)])
        pages, encrypted, corrupt, _error = probe_pdf(path)
        assert pages == page_count
        assert encrypted is False and corrupt is False

    def test_blank_pages_still_count(self, tmp_path, make_pdf):
        path = make_pdf(tmp_path / "blank.pdf", [None, None, None])
        assert probe_pdf(path)[0] == 3

    def test_a_non_pdf_is_reported_as_corrupt(self, tmp_path):
        path = tmp_path / "not_a.pdf"
        path.write_bytes(b"this is plainly not a PDF file")
        pages, _encrypted, corrupt, error = probe_pdf(path)
        assert pages is None and corrupt is True and error


class TestTextExtraction:
    """Per-page extraction and condition classification."""

    def test_extracts_text_and_marks_pages_searchable(self, tmp_path, make_pdf):
        path = make_pdf(
            tmp_path / "doc.pdf",
            ["This page has a good deal of readable body text on it."],
        )
        result = extract_document(path, 1, BatesParser(), ExtractionThresholds())
        assert len(result.pages) == 1
        assert result.pages[0].page_condition == COND_SEARCHABLE
        assert result.pages[0].char_count > 20

    def test_detects_an_empty_page(self, tmp_path, make_pdf):
        path = make_pdf(tmp_path / "blank.pdf", [None])
        result = extract_document(path, 1, BatesParser(), ExtractionThresholds())
        assert result.pages[0].page_condition == COND_APPARENT_BLANK

    def test_reads_a_bates_stamp_from_the_footer(self, tmp_path, make_pdf):
        path = make_pdf(tmp_path / "stamped.pdf", ["Body text here."], bates_start=42)
        result = extract_document(path, 1, BatesParser(), ExtractionThresholds())
        assert result.pages[0].observed_bates_num == 42

    def test_can_extract_a_page_subset(self, tmp_path, make_pdf):
        path = make_pdf(tmp_path / "long.pdf", [f"page {i} text" for i in range(10)])
        result = extract_document(
            path, 1, BatesParser(), ExtractionThresholds(), page_numbers=[1, 2, 10]
        )
        assert [p.page_number for p in result.pages] == [1, 2, 10]

    def test_a_missing_file_fails_without_raising(self, tmp_path):
        result = extract_document(
            tmp_path / "absent.pdf", 1, BatesParser(), ExtractionThresholds()
        )
        assert result.extraction_status == "failed"
        assert result.error_message


class TestResumeBehaviour:
    """A run must skip completed work and pick up changes."""

    def test_second_run_skips_unchanged_files(self, configured):
        config, database, source, _output = configured
        first = run_phase1(config, database, source, workers=1, progress=False)
        assert first.processed > 0

        second = run_phase1(config, database, source, workers=1, progress=False)
        assert second.processed == 0
        assert second.skipped_unchanged == first.processed

    def test_force_reprocesses_everything(self, configured):
        config, database, source, _output = configured
        first = run_phase1(config, database, source, workers=1, progress=False)
        forced = run_phase1(config, database, source, workers=1, progress=False,
                            force=True)
        assert forced.processed == first.processed

    def test_a_changed_file_is_reprocessed(self, configured, make_pdf):
        config, database, source, _output = configured
        run_phase1(config, database, source, workers=1, progress=False)

        target = source / "WILSONRODE000001-null.pdf"
        make_pdf(target, ["Replaced content that is materially different."],
                 bates_start=1)
        again = run_phase1(config, database, source, workers=1, progress=False)
        assert again.processed == 1

    def test_a_new_file_is_picked_up(self, configured, make_pdf):
        config, database, source, _output = configured
        run_phase1(config, database, source, workers=1, progress=False)
        make_pdf(source / "WILSONRODE000099-null.pdf", ["A newly added document."],
                 bates_start=99)
        again = run_phase1(config, database, source, workers=1, progress=False)
        assert again.processed == 1

    def test_needs_processing_respects_size_and_mtime(self, database):
        database.upsert_file(
            {
                "abs_path": "/x/a.pdf", "rel_path": "a.pdf", "filename": "a.pdf",
                "file_size": 100, "modified_ts": "2026-01-01T00:00:00+00:00",
                "sha256": "deadbeef", "processing_status": STATUS_INVENTORIED,
            }
        )
        assert not database.needs_processing("/x/a.pdf", 100,
                                             "2026-01-01T00:00:00+00:00")
        assert database.needs_processing("/x/a.pdf", 101,
                                         "2026-01-01T00:00:00+00:00")
        assert database.needs_processing("/x/a.pdf", 100,
                                         "2026-02-01T00:00:00+00:00")
        assert database.needs_processing("/x/new.pdf", 1, "2026-01-01T00:00:00+00:00")

    def test_errored_files_are_always_retried(self, database):
        database.upsert_file(
            {
                "abs_path": "/x/b.pdf", "rel_path": "b.pdf", "filename": "b.pdf",
                "file_size": 10, "modified_ts": "2026-01-01T00:00:00+00:00",
                "sha256": "abc", "processing_status": "error",
            }
        )
        assert database.needs_processing("/x/b.pdf", 10, "2026-01-01T00:00:00+00:00")

    def test_duplicate_detection_survives_a_rerun(self, configured):
        config, database, source, _output = configured
        run_phase1(config, database, source, workers=1, progress=False)
        first = database.scalar(
            "SELECT COUNT(*) FROM files WHERE exact_dup_group IS NOT NULL"
        )
        run_phase1(config, database, source, workers=1, progress=False)
        second = database.scalar(
            "SELECT COUNT(*) FROM files WHERE exact_dup_group IS NOT NULL"
        )
        assert first == second > 0


class TestFamilyInference:
    """Parent-email / attachment inference."""

    @staticmethod
    def _email(file_id, begin, end, *, attachments=(), subject="Topic",
               date="2019-03-04"):
        return FamilyCandidate(
            file_id=file_id, filename=f"WILSONRODE{begin:06d}-null.pdf",
            begin_bates=begin, end_bates=end, document_type="email",
            document_date=date, subject=subject, attachment_names=list(attachments),
            begin_bates_str=f"WILSONRODE{begin:06d}",
            end_bates_str=f"WILSONRODE{end:06d}",
        )

    @staticmethod
    def _attachment(file_id, begin, end, *, filename=None, subject="Agreement",
                    date="2019-03-04", doc_type="contract"):
        name = filename or f"WILSONRODE{begin:06d}-null.pdf"
        return FamilyCandidate(
            file_id=file_id, filename=name, begin_bates=begin, end_bates=end,
            document_type=doc_type, document_date=date, subject=subject,
            begin_bates_str=f"WILSONRODE{begin:06d}",
            end_bates_str=f"WILSONRODE{end:06d}",
        )

    def test_consecutive_document_is_a_possible_attachment(self):
        relations = infer_families([
            self._email(1, 10, 10),
            self._attachment(2, 11, 13),
        ])
        assert len(relations) == 1
        assert relations[0].parent_file_id == 1
        assert relations[0].child_file_id == 2
        assert relations[0].confidence in ("probable", "possible")

    def test_named_attachment_and_adjacency_is_confirmed(self):
        relations = infer_families([
            self._email(1, 10, 10, attachments=["Agreement_Draft.pdf"]),
            self._attachment(2, 11, 13, filename="Agreement_Draft.pdf"),
        ])
        assert relations[0].confidence == "confirmed"
        assert "Attachments header" in relations[0].reason

    def test_every_reason_is_labelled_as_an_inference(self):
        relations = infer_families([
            self._email(1, 10, 10),
            self._attachment(2, 11, 12),
        ])
        assert all(r.reason.startswith("INFERRED") for r in relations)
        assert all("possible" in r.relationship for r in relations)

    def test_a_bates_gap_breaks_the_family(self):
        relations = infer_families([
            self._email(1, 10, 10),
            self._attachment(2, 50, 52),
        ])
        assert relations == []

    def test_a_following_email_is_not_claimed_as_an_attachment(self):
        relations = infer_families([
            self._email(1, 10, 10, subject="First"),
            self._email(2, 11, 11, subject="Second"),
        ])
        assert relations == []

    def test_non_email_documents_do_not_become_parents(self):
        relations = infer_families([
            self._attachment(1, 10, 10),
            self._attachment(2, 11, 12),
        ])
        assert relations == []

    def test_multiple_attachments_are_all_claimed(self):
        relations = infer_families([
            self._email(1, 10, 10),
            self._attachment(2, 11, 12),
            self._attachment(3, 13, 14),
        ])
        assert len(relations) == 2

    def test_documents_without_bates_are_ignored(self):
        candidate = self._attachment(9, 1, 1)
        candidate.begin_bates = None
        assert infer_families([candidate]) == []

    def test_filename_normalisation(self):
        assert normalize_filename("Agreement_Draft.pdf") == "agreementdraft"
        assert normalize_filename("agreement draft.PDF") == "agreementdraft"

    def test_subject_normalisation_strips_reply_prefixes(self):
        assert normalize_subject("RE: FW: Commission agreement") == (
            "commission agreement"
        )
        assert normalize_subject(None) is None


class TestDatabaseState:
    """State transitions recorded by the database."""

    def test_phase1_marks_files_inventoried(self, configured):
        config, database, source, _output = configured
        run_phase1(config, database, source, workers=1, progress=False)
        statuses = {
            row["processing_status"]
            for row in database.query("SELECT processing_status FROM files")
        }
        assert STATUS_INVENTORIED in statuses

    def test_audit_log_records_the_run(self, configured):
        config, database, source, _output = configured
        run_phase1(config, database, source, workers=1, progress=False)
        operations = {
            row["operation"]
            for row in database.query("SELECT operation FROM audit_log")
        }
        assert "phase1_start" in operations
        assert "phase1_complete" in operations

    def test_statistics_are_recorded(self, configured):
        config, database, source, _output = configured
        run_phase1(config, database, source, workers=1, progress=False)
        stats = database.get_stats("phase1")
        assert stats["total_files"] > 0
        assert stats["pdf_files"] > 0
        assert "preliminary_filename_gap_count" in stats

    def test_fts_index_is_available(self, database):
        file_id = database.upsert_file(
            {"abs_path": "/x/a.pdf", "rel_path": "a.pdf", "filename": "a.pdf",
             "file_size": 1, "sha256": "x"}
        )
        database.store_page_text(
            file_id, [(1, "the statute of frauds bars the claim")]
        )
        rows = database.search_text("statute")
        assert len(rows) == 1
        assert rows[0]["filename"] == "a.pdf"
        assert rows[0]["page_number"] == 1

    def test_page_text_requires_a_known_file(self, database):
        """The foreign key stops orphaned text accumulating in the index."""
        import sqlite3

        with pytest.raises(sqlite3.IntegrityError):
            database.store_page_text(9999, [(1, "text for a file that does not exist")])
