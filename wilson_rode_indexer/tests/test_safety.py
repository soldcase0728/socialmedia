"""Tests for the read-only source guarantee and the no-content-in-terminal rule.

These are the safety tests.  If any of them fails, the tool must not be run
against a real production.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest

from src.config import Config, ConfigError
from src.inventory import ReadOnlySourceError, assert_read_only, sha256_file
from src.logging_setup import ContentGuard, setup_logging


class TestReadOnlyGuard:
    """`assert_read_only` is the programmatic expression of safeguard #1."""

    def test_rejects_a_path_inside_the_source(self, tmp_path):
        source = tmp_path / "Wilson-Rode File"
        source.mkdir()
        with pytest.raises(ReadOnlySourceError):
            assert_read_only(source, source / "output.xlsx")

    def test_rejects_a_deeply_nested_path(self, tmp_path):
        source = tmp_path / "Wilson-Rode File"
        (source / "a" / "b").mkdir(parents=True)
        with pytest.raises(ReadOnlySourceError):
            assert_read_only(source, source / "a" / "b" / "index.sqlite")

    def test_rejects_the_source_folder_itself(self, tmp_path):
        source = tmp_path / "Wilson-Rode File"
        source.mkdir()
        with pytest.raises(ReadOnlySourceError):
            assert_read_only(source, source)

    def test_allows_a_sibling_folder(self, tmp_path):
        source = tmp_path / "Wilson-Rode File"
        source.mkdir()
        sibling = tmp_path / "Wilson_Rode_Derived_Index"
        assert_read_only(source, sibling / "01_File_Inventory.xlsx")

    def test_config_refuses_an_output_inside_the_source(self, tmp_path, project_root):
        import yaml

        source = tmp_path / "Wilson-Rode File"
        source.mkdir()
        raw = yaml.safe_load((project_root / "config.yaml").read_text(encoding="utf-8"))
        raw["paths"]["source_folder"] = str(source)
        raw["paths"]["output_folder"] = str(source / "derived")
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")

        config = Config.load(path)
        with pytest.raises(ConfigError, match="Refusing to write inside"):
            config.resolve_output_folder(config.resolve_source_folder())

    def test_default_output_is_a_sibling_of_the_source(self, configured):
        config, _database, source, output = configured
        assert output.parent == source.parent
        assert source not in output.parents


class TestSourceIsNotModified:
    """A full Phase 1 run must leave every source byte and timestamp intact."""

    @staticmethod
    def _snapshot(root: Path):
        """Record path, size, mtime and digest for every file under ``root``."""
        return {
            str(path.relative_to(root)): (
                path.stat().st_size,
                path.stat().st_mtime_ns,
                sha256_file(path),
            )
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def test_phase1_leaves_the_source_untouched(self, configured):
        from src.inventory import run_phase1

        config, database, source, _output = configured
        before = self._snapshot(source)
        run_phase1(config, database, source, workers=1, progress=False)
        after = self._snapshot(source)
        assert before == after, "Phase 1 modified the read-only source folder"

    def test_phase1_writes_nothing_into_the_source(self, configured):
        from src.inventory import run_phase1

        config, database, source, _output = configured
        names_before = {str(p.relative_to(source)) for p in source.rglob("*")}
        run_phase1(config, database, source, workers=1, progress=False)
        names_after = {str(p.relative_to(source)) for p in source.rglob("*")}
        assert names_before == names_after

    def test_reports_write_only_to_the_output_folder(self, configured):
        from src.inventory import run_phase1
        from src.phase1_reports import generate_phase1_reports

        config, database, source, output = configured
        run_phase1(config, database, source, workers=1, progress=False)
        written = generate_phase1_reports(config, database, output, source)
        assert written
        for path in written:
            assert output in path.parents or path.parent == output
            with pytest.raises(ValueError):
                path.relative_to(source)


class TestNoDocumentTextInTerminal:
    """The console filter is structural, not advisory."""

    @staticmethod
    def _record(message: str) -> logging.LogRecord:
        return logging.LogRecord(
            "wri.test", logging.INFO, __file__, 1, message, (), None
        )

    def test_ordinary_progress_messages_pass_through(self):
        record = self._record("Processed 250 files")
        ContentGuard().filter(record)
        assert record.getMessage() == "Processed 250 files"

    def test_email_headers_are_suppressed(self):
        record = self._record("From: John Wilson <jwilson@example.com>")
        ContentGuard().filter(record)
        assert "jwilson@example.com" not in record.getMessage()
        assert "suppressed" in record.getMessage()

    def test_bare_email_addresses_are_suppressed(self):
        record = self._record("contacted prode@example.com about the matter")
        ContentGuard().filter(record)
        assert "prode@example.com" not in record.getMessage()

    def test_long_messages_are_suppressed(self):
        record = self._record("x" * 5000)
        ContentGuard().filter(record)
        assert len(record.getMessage()) < 500
        assert "suppressed" in record.getMessage()

    def test_explicitly_safe_records_pass(self):
        record = self._record("From: this is a deliberate test string")
        record.safe = True
        assert ContentGuard().filter(record) is True
        assert "deliberate test string" in record.getMessage()

    def test_filter_is_installed_on_every_handler(self, tmp_path):
        logger = setup_logging(tmp_path / "logs")
        assert logger.handlers
        for handler in logger.handlers:
            assert any(isinstance(f, ContentGuard) for f in handler.filters)

    def test_log_file_contains_no_document_text(self, tmp_path):
        logger = setup_logging(tmp_path / "logs")
        logger.info("From: secret@example.com Subject: confidential matter")
        for handler in logger.handlers:
            handler.flush()
        contents = (tmp_path / "logs" / "wilson_rode_indexer.log").read_text(
            encoding="utf-8"
        )
        assert "secret@example.com" not in contents


class TestNoTextInReports:
    """Extracted text must never reach a workbook or CSV."""

    def test_inventory_columns_carry_no_text_field(self):
        from src.phase1_reports import inventory_columns

        keys = {column.key for column in inventory_columns()}
        assert "text" not in keys
        assert not any("text" == key for key in keys)

    def test_master_index_columns_carry_no_text_field(self):
        from src.phase3_reports import master_columns

        keys = {column.key for column in master_columns()}
        assert "text" not in keys
        assert "page_text" not in keys

    def test_issue_locator_is_withheld_from_excel_by_default(self, config):
        from src.phase3_reports import issue_columns

        redact = config.get("issue_tag_options", "redact_context_in_excel",
                            default=True)
        assert redact is True
        keys = {column.key for column in issue_columns(include_locator=not redact)}
        assert "locator" not in keys
