"""Excel, CSV and Markdown report generation.

Every workbook produced here follows the same conventions:

* the header row is frozen and carries an autofilter;
* column widths are computed from the data, within configured bounds;
* long free-text columns wrap;
* a **Data Dictionary** tab explains every column and labels it *observed*,
  *calculated* or *inferred*;
* a **Methodology and Limitations** tab states plainly what the numbers do and
  do not mean;
* a **Run Statistics** tab records the run that produced the file;
* meaning is never carried by colour alone -- any highlight is accompanied by
  a text value in its own column.

No workbook contains extracted document text.  Text lives in the SQLite FTS5
index only.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .logging_setup import get_logger
from .version import APP_NAME, APP_VERSION

log = get_logger("reports")

#: Field-provenance vocabulary used by every Data Dictionary tab.
OBSERVED = "Observed"
CALCULATED = "Calculated"
INFERRED = "Inferred"

DERIVED_METADATA_NOTICE = (
    "DERIVED REVIEW METADATA. Every value in this workbook was derived by "
    "software from the produced PDF files themselves. None of it is original "
    "or native document metadata, and none of it comes from a load file, DAT, "
    "OPT, CSV or native-file index, because the production did not include "
    "one. Values labelled Inferred are software guesses supported by the "
    "stated reason and must be verified before being relied upon."
)


@dataclass
class Column:
    """One column in a report worksheet."""

    key: str
    header: str
    width: Optional[int] = None
    wrap: bool = False
    provenance: str = CALCULATED
    description: str = ""
    number_format: Optional[str] = None
    hyperlink_from: Optional[str] = None

    def value_of(self, row: Dict[str, Any]) -> Any:
        """Return this column's value from a row mapping."""
        return row.get(self.key)


@dataclass
class Sheet:
    """A worksheet: columns plus a row iterable."""

    name: str
    columns: List[Column]
    rows: Iterable[Dict[str, Any]]
    freeze: str = "A2"
    autofilter: bool = True
    note: Optional[str] = None


# ---------------------------------------------------------------------------
# workbook writing
# ---------------------------------------------------------------------------
class ReportWriter:
    """Writes workbooks with the house conventions applied.

    Parameters
    ----------
    output_dir:
        Directory every report is written to (the derived-index folder).
    source_root:
        The read-only production folder.  Passed only so the writer can assert
        it is never writing inside it.
    settings:
        The ``reports`` section of ``config.yaml``.
    run_stats:
        Statistics rendered on the Run Statistics tab.
    """

    def __init__(
        self,
        output_dir: Path,
        *,
        source_root: Optional[Path] = None,
        settings: Optional[Dict[str, Any]] = None,
        run_stats: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.source_root = Path(source_root) if source_root else None
        self.settings = settings or {}
        self.run_stats = run_stats or {}
        self.min_width = int(self.settings.get("min_column_width", 10))
        self.max_width = int(self.settings.get("max_column_width", 60))
        self.hyperlinks_enabled = bool(self.settings.get("hyperlinks", True))
        self.max_hyperlinks = int(self.settings.get("max_hyperlinks", 60000))
        self.max_cell_chars = int(self.settings.get("max_cell_chars", 3000))

    # ------------------------------------------------------------------
    def _target(self, filename: str) -> Path:
        """Resolve an output path, refusing to write into the source folder."""
        path = self.output_dir / filename
        if self.source_root is not None:
            from .inventory import assert_read_only

            assert_read_only(self.source_root, path)
        return path

    # ------------------------------------------------------------------
    def write_workbook(
        self,
        filename: str,
        sheets: Sequence[Sheet],
        *,
        methodology: Optional[Sequence[str]] = None,
        limitations: Optional[Sequence[str]] = None,
        include_standard_tabs: bool = True,
    ) -> Path:
        """Write a workbook and return its path.

        Data sheets are written first, followed by the three standard tabs.
        Rows are consumed lazily, so a sheet backed by a database cursor never
        materialises the whole production in memory.
        """
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        path = self._target(filename)
        workbook = Workbook()
        workbook.remove(workbook.active)

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill("solid", fgColor="1F3864")
        header_align = Alignment(vertical="center", wrap_text=True)
        wrap_align = Alignment(vertical="top", wrap_text=True)
        top_align = Alignment(vertical="top")
        link_font = Font(color="0563C1", underline="single")

        total_rows = 0
        for sheet in sheets:
            worksheet = workbook.create_sheet(_safe_sheet_name(sheet.name))
            start_row = 1
            if sheet.note:
                worksheet.cell(row=1, column=1, value=sheet.note).alignment = wrap_align
                worksheet.cell(row=1, column=1).font = Font(italic=True, size=9)
                worksheet.merge_cells(
                    start_row=1, start_column=1, end_row=1,
                    end_column=max(1, len(sheet.columns)),
                )
                worksheet.row_dimensions[1].height = 30
                start_row = 2

            for index, column in enumerate(sheet.columns, start=1):
                cell = worksheet.cell(row=start_row, column=index, value=column.header)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_align

            widths = [len(column.header) + 2 for column in sheet.columns]
            hyperlink_budget = self.max_hyperlinks
            row_index = start_row

            for row in sheet.rows:
                row_index += 1
                total_rows += 1
                for column_index, column in enumerate(sheet.columns, start=1):
                    value = _coerce(column.value_of(row), self.max_cell_chars)
                    cell = worksheet.cell(row=row_index, column=column_index, value=value)
                    cell.alignment = wrap_align if column.wrap else top_align
                    if column.number_format:
                        cell.number_format = column.number_format
                    if (
                        column.hyperlink_from
                        and self.hyperlinks_enabled
                        and hyperlink_budget > 0
                    ):
                        target = row.get(column.hyperlink_from)
                        if target:
                            try:
                                cell.hyperlink = Path(str(target)).as_uri()
                                cell.font = link_font
                                hyperlink_budget -= 1
                            except (ValueError, OSError):
                                pass
                    if value is not None:
                        widths[column_index - 1] = max(
                            widths[column_index - 1], min(len(str(value)) + 2, self.max_width)
                        )

            for index, width in enumerate(widths, start=1):
                worksheet.column_dimensions[get_column_letter(index)].width = max(
                    self.min_width, min(self.max_width, width)
                )

            if sheet.freeze:
                worksheet.freeze_panes = (
                    sheet.freeze if start_row == 1 else f"A{start_row + 1}"
                )
            if sheet.autofilter and row_index > start_row:
                worksheet.auto_filter.ref = (
                    f"A{start_row}:{get_column_letter(len(sheet.columns))}{row_index}"
                )

        if include_standard_tabs:
            self._write_data_dictionary(workbook, sheets)
            self._write_methodology(workbook, methodology, limitations)
            self._write_run_statistics(workbook)

        workbook.save(path)
        log.info("Wrote %s (%d data row(s))", path.name, total_rows)
        return path

    # ------------------------------------------------------------------
    def _write_data_dictionary(self, workbook, sheets: Sequence[Sheet]) -> None:
        """Add the Data Dictionary tab describing every column."""
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        worksheet = workbook.create_sheet("Data Dictionary")
        worksheet.cell(row=1, column=1, value=DERIVED_METADATA_NOTICE)
        worksheet.cell(row=1, column=1).alignment = Alignment(wrap_text=True,
                                                              vertical="top")
        worksheet.cell(row=1, column=1).font = Font(bold=True, size=10)
        worksheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)
        worksheet.row_dimensions[1].height = 60

        headers = ["Worksheet", "Column", "Data class", "What it means",
                   "How to read it"]
        for index, header in enumerate(headers, start=1):
            cell = worksheet.cell(row=3, column=index, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F3864")

        guidance = {
            OBSERVED: "Read directly from the file or its page content. "
                      "Strongest evidence available here.",
            CALCULATED: "Computed deterministically from the file (hashing, "
                        "counting, arithmetic). Reproducible.",
            INFERRED: "A software inference supported by a stated reason. "
                      "Verify before relying on it.",
        }

        row_index = 4
        for sheet in sheets:
            for column in sheet.columns:
                worksheet.cell(row=row_index, column=1, value=sheet.name)
                worksheet.cell(row=row_index, column=2, value=column.header)
                worksheet.cell(row=row_index, column=3, value=column.provenance)
                worksheet.cell(row=row_index, column=4, value=column.description)
                worksheet.cell(row=row_index, column=5,
                               value=guidance.get(column.provenance, ""))
                for col in (4, 5):
                    worksheet.cell(row=row_index, column=col).alignment = Alignment(
                        wrap_text=True, vertical="top"
                    )
                row_index += 1

        for index, width in enumerate((22, 30, 14, 62, 52), start=1):
            worksheet.column_dimensions[get_column_letter(index)].width = width
        worksheet.freeze_panes = "A4"
        if row_index > 4:
            worksheet.auto_filter.ref = f"A3:E{row_index - 1}"

    # ------------------------------------------------------------------
    def _write_methodology(
        self,
        workbook,
        methodology: Optional[Sequence[str]],
        limitations: Optional[Sequence[str]],
    ) -> None:
        """Add the Methodology and Limitations tab."""
        from openpyxl.styles import Alignment, Font
        from openpyxl.utils import get_column_letter

        worksheet = workbook.create_sheet("Methodology and Limitations")
        worksheet.column_dimensions[get_column_letter(1)].width = 118

        lines: List[Tuple[str, str]] = [("heading", "Methodology")]
        lines += [("body", text) for text in (methodology or DEFAULT_METHODOLOGY)]
        lines.append(("heading", "Limitations"))
        lines += [("body", text) for text in (limitations or DEFAULT_LIMITATIONS)]
        lines.append(("heading", "Derived versus native metadata"))
        lines.append(("body", DERIVED_METADATA_NOTICE))

        row_index = 1
        for kind, text in lines:
            cell = worksheet.cell(row=row_index, column=1, value=text)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if kind == "heading":
                cell.font = Font(bold=True, size=12)
                worksheet.row_dimensions[row_index].height = 22
            else:
                worksheet.row_dimensions[row_index].height = max(
                    16, 14 * (1 + len(text) // 110)
                )
            row_index += 2 if kind == "heading" else 1

    # ------------------------------------------------------------------
    def _write_run_statistics(self, workbook) -> None:
        """Add the Run Statistics tab."""
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        worksheet = workbook.create_sheet("Run Statistics")
        for index, header in enumerate(("Phase", "Statistic", "Value"), start=1):
            cell = worksheet.cell(row=1, column=index, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F3864")

        row_index = 2
        base = {
            "application": APP_NAME,
            "application_version": APP_VERSION,
            "report_generated_utc": datetime.now(timezone.utc).isoformat(
                timespec="seconds"
            ),
        }
        for key, value in base.items():
            worksheet.cell(row=row_index, column=1, value="run")
            worksheet.cell(row=row_index, column=2, value=key)
            worksheet.cell(row=row_index, column=3, value=str(value))
            row_index += 1

        for phase, stats in sorted(self.run_stats.items()):
            if not isinstance(stats, dict):
                stats = {"value": stats}
            for key, value in sorted(stats.items()):
                worksheet.cell(row=row_index, column=1, value=str(phase))
                worksheet.cell(row=row_index, column=2, value=str(key))
                rendered = (
                    json.dumps(value, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else str(value)
                )
                cell = worksheet.cell(row=row_index, column=3,
                                      value=rendered[: self.max_cell_chars])
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                row_index += 1

        for index, width in enumerate((16, 42, 76), start=1):
            worksheet.column_dimensions[get_column_letter(index)].width = width
        worksheet.freeze_panes = "A2"
        if row_index > 2:
            worksheet.auto_filter.ref = f"A1:C{row_index - 1}"

    # ------------------------------------------------------------------
    def write_csv(
        self, filename: str, columns: Sequence[Column], rows: Iterable[Dict[str, Any]]
    ) -> Path:
        """Write a CSV companion to a workbook sheet."""
        path = self._target(filename)
        count = 0
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle, quoting=csv.QUOTE_MINIMAL)
            writer.writerow([column.header for column in columns])
            for row in rows:
                writer.writerow(
                    [_csv_value(column.value_of(row)) for column in columns]
                )
                count += 1
        log.info("Wrote %s (%d row(s))", path.name, count)
        return path

    def write_markdown(self, filename: str, content: str) -> Path:
        """Write a Markdown summary document."""
        path = self._target(filename)
        path.write_text(content, encoding="utf-8")
        log.info("Wrote %s", path.name)
        return path


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _safe_sheet_name(name: str) -> str:
    """Return a worksheet name Excel will accept."""
    cleaned = "".join(ch for ch in name if ch not in "[]:*?/\\")
    return (cleaned or "Sheet")[:31]


def _coerce(value: Any, max_chars: int) -> Any:
    """Convert a Python value into something Excel can store."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, (list, tuple, set)):
        value = "; ".join(str(item) for item in value)
    elif isinstance(value, dict):
        value = json.dumps(value, sort_keys=True)
    text = str(value)
    # Excel treats a leading =, +, - or @ as a formula; neutralise it.
    if text[:1] in ("=", "+", "@"):
        text = "'" + text
    return text[:max_chars]


def _csv_value(value: Any) -> Any:
    """Convert a Python value for CSV output."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return value


def format_bytes(total: int) -> str:
    """Human-readable byte count."""
    size = float(total or 0)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:,.2f} {unit}" if unit != "B" else f"{int(size):,} B"
        size /= 1024
    return f"{size:,.2f} TiB"  # pragma: no cover - unreachable


# ---------------------------------------------------------------------------
# standard narrative text
# ---------------------------------------------------------------------------
DEFAULT_METHODOLOGY: Tuple[str, ...] = (
    "All processing was performed locally. No document content was sent to any "
    "external API, cloud OCR service, hosted AI service, or remote database.",
    "The source production folder was treated as read-only for the entire run. "
    "No source file was renamed, moved, altered, annotated, OCRed in place, "
    "combined, or deleted. Every generated file was written to a separate "
    "derived-index folder outside the production.",
    "Phase 1 recorded structural facts only: filename, path, size, timestamps, "
    "SHA-256 hash, PDF page count, encryption state, and readability. It did "
    "not read substantive document content.",
    "Phase 2 attempted native PDF text extraction page by page and classified "
    "each page's condition. OCR, where used, ran locally and wrote only to a "
    "cache inside the derived-index folder.",
    "Phase 3 derived review metadata using deterministic regular expressions "
    "and rule-based parsing. No language model was used for extraction or "
    "classification.",
    "Duplicate detection ran in three passes: SHA-256 for exact binary copies, "
    "a hash of normalised text for identical text in different renderings, and "
    "SimHash fingerprints indexed with locality-sensitive hashing for near "
    "duplicates. No all-pairs comparison was performed.",
    "Extracted text is stored only in the local SQLite database and its FTS5 "
    "search index. It is not present in any workbook or CSV produced by this "
    "tool.",
)

DEFAULT_LIMITATIONS: Tuple[str, ...] = (
    "This tool produces DERIVED metadata. The production did not include a "
    "CSV, DAT, OPT, or native-file index, so no native metadata was available "
    "and none is reported.",
    "Bates numbers parsed from filenames are weaker evidence than Bates stamps "
    "observed on a page. Each row states which source was used and how "
    "confident the derivation is.",
    "Bates gaps derived from filenames alone are PRELIMINARY. A single PDF in "
    "this production may contain several Bates-numbered pages, so a numeric "
    "jump between filenames does not by itself establish a missing document.",
    "Document-type classification is rule-based and reports a confidence "
    "score. Documents scoring below the configured threshold are reported as "
    "'unknown' rather than guessed.",
    "Family (parent email / attachment) relationships are INFERRED from Bates "
    "adjacency, attachment lists, dates and subjects. They are not native "
    "family metadata and each carries the reason it was inferred.",
    "Issue tags are keyword screening hits. They are not legal conclusions, "
    "relevance determinations, or privilege calls.",
    "Priority scores order review work. A high score does not prove "
    "malpractice, breach, or liability.",
    "Pages with no extractable text may be image-only, genuinely blank, "
    "separator pages, or failed exports. The audit distinguishes these where "
    "the evidence allows and reports 'uncertain' where it does not.",
    "Accuracy has not been measured against a human-verified gold standard "
    "except where a pilot accuracy figure is reported. No claim of perfect "
    "accuracy is made or implied.",
    "Encrypted or password-protected PDFs were not opened and carry no derived "
    "content metadata.",
)
