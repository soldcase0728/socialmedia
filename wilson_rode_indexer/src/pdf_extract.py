"""Phase 2 -- per-page text extraction and page-condition audit.

Native text extraction is always attempted first.  OCR is a last resort, is
opt-in, and always writes to a cache inside the derived-index folder: the
source PDF is opened read-only and is never modified, annotated, or OCRed in
place.

Extracted text is stored in SQLite (and its FTS5 index) and is never printed
to the terminal or written into an Excel report.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .bates import BatesParser
from .config import Config
from .database import (
    Database,
    EXTRACT_ENCRYPTED,
    EXTRACT_FAILED,
    EXTRACT_OK,
    EXTRACT_PARTIAL,
    OCR_COMPLETED,
    OCR_FAILED,
    OCR_NOT_REQUIRED,
    OCR_REQUIRED,
    OCR_SKIPPED,
    STATUS_ERROR,
    STATUS_PAGES_DONE,
)
from .logging_setup import get_logger

log = get_logger("pdf_extract")

PHASE = "phase2"

# ---------------------------------------------------------------------------
# page-condition vocabulary
# ---------------------------------------------------------------------------
COND_SEARCHABLE = "searchable"
COND_IMAGE_ONLY = "image_only"
COND_OCR_REQUIRED = "ocr_required"
COND_OCR_COMPLETED = "ocr_completed"
COND_APPARENT_BLANK = "apparent_blank"
COND_BATES_ONLY = "bates_only"
COND_CORRUPT = "corrupt"
COND_UNCERTAIN = "uncertain"

# blank / Bates-only subtypes
SUB_TRULY_BLANK = "truly_blank_candidate"
SUB_BATES_ONLY = "bates_stamp_only"
SUB_SEPARATOR = "possible_separator_page"
SUB_FAILED_EXPORT = "possible_failed_export"
SUB_UNCERTAIN = "uncertain"

#: Short phrases that mark a deliberate separator/placeholder page.
_SEPARATOR_MARKERS = (
    "this page intentionally left blank",
    "intentionally left blank",
    "page intentionally blank",
    "separator page",
    "attachment separator",
    "document separator",
    "placeholder",
    "redacted",
    "withheld",
    "non-printable",
    "nonprintable",
    "file not converted",
    "unable to convert",
    "conversion failed",
    "no preview available",
)


@dataclass
class PageAudit:
    """Condition audit for a single page.

    ``text`` is carried alongside the audit for storage but is never surfaced
    to the terminal or the reports.
    """

    page_number: int
    char_count: int = 0
    word_count: int = 0
    has_text_layer: bool = False
    image_count: int = 0
    image_coverage: float = 0.0
    width: Optional[float] = None
    height: Optional[float] = None
    page_condition: str = COND_UNCERTAIN
    blank_subtype: Optional[str] = None
    observed_bates: Optional[str] = None
    observed_bates_num: Optional[int] = None
    ocr_status: str = OCR_NOT_REQUIRED
    ocr_cache_path: Optional[str] = None
    error_message: Optional[str] = None
    text: str = ""

    def to_row(self, file_id: int) -> Dict[str, Any]:
        """Convert to a ``pages`` table row (text excluded)."""
        return {
            "file_id": file_id,
            "page_number": self.page_number,
            "char_count": self.char_count,
            "word_count": self.word_count,
            "has_text_layer": int(self.has_text_layer),
            "image_count": self.image_count,
            "image_coverage": round(self.image_coverage, 4),
            "width": self.width,
            "height": self.height,
            "page_condition": self.page_condition,
            "blank_subtype": self.blank_subtype,
            "observed_bates": self.observed_bates,
            "observed_bates_num": self.observed_bates_num,
            "ocr_status": self.ocr_status,
            "ocr_cache_path": self.ocr_cache_path,
            "error_message": self.error_message,
        }


@dataclass
class DocumentExtraction:
    """Result of extracting one PDF."""

    file_id: int
    abs_path: str
    pages: List[PageAudit] = field(default_factory=list)
    extraction_status: str = EXTRACT_OK
    error_message: Optional[str] = None

    @property
    def total_chars(self) -> int:
        """Total characters extracted across all pages."""
        return sum(page.char_count for page in self.pages)

    @property
    def ocr_required_pages(self) -> List[int]:
        """Page numbers still awaiting OCR."""
        return [p.page_number for p in self.pages if p.ocr_status == OCR_REQUIRED]


# ---------------------------------------------------------------------------
# thresholds
# ---------------------------------------------------------------------------
@dataclass
class ExtractionThresholds:
    """Tunable thresholds governing page classification."""

    min_chars_for_text_layer: int = 25
    blank_char_threshold: int = 5
    bates_only_extra_chars: int = 20
    image_coverage_threshold: float = 0.05
    footer_fraction: float = 0.18
    max_chars_per_page_stored: int = 200_000

    @classmethod
    def from_config(cls, config: Config) -> "ExtractionThresholds":
        """Build thresholds from configuration."""
        return cls(
            min_chars_for_text_layer=int(
                config.get("extraction", "min_chars_for_text_layer", default=25)
            ),
            blank_char_threshold=int(
                config.get("extraction", "blank_char_threshold", default=5)
            ),
            bates_only_extra_chars=int(
                config.get("extraction", "bates_only_extra_chars", default=20)
            ),
            image_coverage_threshold=float(
                config.get("extraction", "image_coverage_threshold", default=0.05)
            ),
            footer_fraction=float(config.get("bates", "footer_fraction", default=0.18)),
            max_chars_per_page_stored=int(
                config.get("extraction", "max_chars_per_page_stored", default=200_000)
            ),
        )


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------
def extract_document(
    path: Path,
    file_id: int,
    parser: BatesParser,
    thresholds: ExtractionThresholds,
    *,
    page_numbers: Optional[Sequence[int]] = None,
) -> DocumentExtraction:
    """Extract text and audit page condition for one PDF.

    The PDF is opened read-only.  Nothing is written back to it under any
    circumstance.

    Parameters
    ----------
    path:
        Absolute path to the source PDF.
    file_id:
        Database identifier, carried through to the result.
    parser:
        Bates parser used to detect stamps in the extracted text.
    thresholds:
        Classification thresholds.
    page_numbers:
        Optional 1-based subset of pages to process.  Used when only the head
        and tail of a long document are needed.

    Returns
    -------
    DocumentExtraction
        Per-page audits and an overall extraction status.  Failures are
        recorded rather than raised.
    """
    result = DocumentExtraction(file_id=file_id, abs_path=str(path))
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover - dependency documented in README
        result.extraction_status = EXTRACT_FAILED
        result.error_message = "PyMuPDF is not installed"
        return result

    document = None
    try:
        document = fitz.open(str(path))
        if document.needs_pass:
            result.extraction_status = EXTRACT_ENCRYPTED
            result.error_message = "password-protected; not opened"
            return result

        total = document.page_count
        targets = (
            [n for n in page_numbers if 1 <= n <= total]
            if page_numbers is not None
            else list(range(1, total + 1))
        )
        failures = 0
        for number in targets:
            try:
                audit = _audit_page(document[number - 1], number, parser, thresholds)
            except Exception as exc:
                failures += 1
                audit = PageAudit(
                    page_number=number,
                    page_condition=COND_CORRUPT,
                    error_message=f"{type(exc).__name__}: {exc}",
                )
            result.pages.append(audit)

        if failures == 0:
            result.extraction_status = EXTRACT_OK
        elif failures < len(targets):
            result.extraction_status = EXTRACT_PARTIAL
            result.error_message = f"{failures} of {len(targets)} pages failed"
        else:
            result.extraction_status = EXTRACT_FAILED
            result.error_message = "no page could be read"
    except Exception as exc:
        result.extraction_status = EXTRACT_FAILED
        result.error_message = f"{type(exc).__name__}: {exc}"
    finally:
        if document is not None:
            try:
                document.close()
            except Exception:  # pragma: no cover - defensive
                pass
    return result


def _audit_page(
    page, number: int, parser: BatesParser, thresholds: ExtractionThresholds
) -> PageAudit:
    """Classify a single :class:`fitz.Page`."""
    text = page.get_text("text") or ""
    stripped = text.strip()
    words = stripped.split()
    rect = page.rect
    page_area = float(rect.width * rect.height) or 1.0

    image_count, image_area = _image_metrics(page)
    coverage = min(1.0, image_area / page_area) if page_area else 0.0

    audit = PageAudit(
        page_number=number,
        char_count=len(stripped),
        word_count=len(words),
        has_text_layer=len(stripped) >= thresholds.min_chars_for_text_layer,
        image_count=image_count,
        image_coverage=coverage,
        width=round(float(rect.width), 2),
        height=round(float(rect.height), 2),
        text=text[: thresholds.max_chars_per_page_stored],
    )

    footer_text = _footer_text(page, thresholds.footer_fraction)
    stamp = parser.find_on_page(text, footer_text)
    if stamp is not None:
        audit.observed_bates = stamp.normalized
        audit.observed_bates_num = stamp.number

    classify_page(audit, thresholds)
    return audit


def _image_metrics(page) -> Tuple[int, float]:
    """Return ``(image_count, total_image_area)`` for a page.

    Overlapping images are counted separately; the caller clamps coverage to
    1.0, so an over-count cannot produce a nonsensical fraction.
    """
    count = 0
    area = 0.0
    try:
        infos = page.get_image_info()
    except Exception:  # pragma: no cover - older PyMuPDF
        infos = []
    for info in infos or []:
        count += 1
        bbox = info.get("bbox")
        if bbox and len(bbox) == 4:
            width = abs(float(bbox[2]) - float(bbox[0]))
            height = abs(float(bbox[3]) - float(bbox[1]))
            area += width * height
    if not count:
        try:
            count = len(page.get_images(full=True) or [])
        except Exception:  # pragma: no cover - defensive
            count = 0
    return count, area


def _footer_text(page, fraction: float) -> str:
    """Return text from the bottom ``fraction`` of a page."""
    try:
        rect = page.rect
        clip = type(rect)(
            rect.x0, rect.y1 - (rect.height * max(0.02, min(0.5, fraction))),
            rect.x1, rect.y1,
        )
        return page.get_text("text", clip=clip) or ""
    except Exception:  # pragma: no cover - defensive
        return ""


def classify_page(audit: PageAudit, thresholds: ExtractionThresholds) -> PageAudit:
    """Assign ``page_condition`` and ``blank_subtype`` to a page audit.

    The decision order is deliberate:

    1. A page with a usable amount of text is ``searchable``.
    2. A page whose only text is its Bates stamp is ``bates_only``.
    3. A page with essentially no text but meaningful image content is
       ``image_only`` and becomes an OCR candidate.
    4. A page with neither text nor images is an ``apparent_blank``.
    5. Anything that does not fit is ``uncertain`` -- never guessed.
    """
    text_lower = audit.text.strip().lower()
    stamp_length = len(audit.observed_bates or "")
    bates_only_ceiling = stamp_length + thresholds.bates_only_extra_chars

    if audit.page_condition == COND_CORRUPT:
        return audit

    separator_hit = any(marker in text_lower for marker in _SEPARATOR_MARKERS)

    if audit.observed_bates and audit.char_count <= bates_only_ceiling:
        audit.page_condition = COND_BATES_ONLY
        audit.blank_subtype = SUB_SEPARATOR if separator_hit else SUB_BATES_ONLY
        return audit

    if audit.char_count >= thresholds.min_chars_for_text_layer:
        audit.has_text_layer = True
        audit.page_condition = COND_SEARCHABLE
        if separator_hit and audit.char_count < 200:
            audit.blank_subtype = SUB_SEPARATOR
        return audit

    if audit.image_coverage >= thresholds.image_coverage_threshold or (
        audit.image_count > 0 and audit.char_count < thresholds.min_chars_for_text_layer
    ):
        audit.has_text_layer = False
        audit.page_condition = COND_IMAGE_ONLY
        audit.ocr_status = OCR_REQUIRED
        return audit

    if audit.char_count <= thresholds.blank_char_threshold and audit.image_count == 0:
        audit.page_condition = COND_APPARENT_BLANK
        if separator_hit:
            audit.blank_subtype = SUB_SEPARATOR
        elif audit.char_count == 0 and audit.image_count == 0:
            audit.blank_subtype = SUB_TRULY_BLANK
        else:
            audit.blank_subtype = SUB_UNCERTAIN
        return audit

    # Small amount of text, no images: not confidently anything.
    audit.page_condition = COND_UNCERTAIN
    audit.blank_subtype = SUB_FAILED_EXPORT if audit.char_count == 0 else SUB_UNCERTAIN
    return audit


# ---------------------------------------------------------------------------
# OCR (cache-only, never in place)
# ---------------------------------------------------------------------------
class OcrUnavailableError(RuntimeError):
    """Raised when OCR is requested but no local engine is installed."""


def ocr_available(engine: str = "ocrmypdf") -> bool:
    """Whether the configured local OCR engine is on ``PATH``."""
    return shutil.which(engine) is not None


def ocr_cache_path(cache_dir: Path, source: Path, sha256: Optional[str]) -> Path:
    """Return the cache location for a source PDF's OCR derivative.

    The path is keyed on the file's SHA-256 (falling back to a hash of the
    absolute path) so the cache survives renames and never collides.
    """
    key = sha256 or hashlib.sha256(str(source).encode("utf-8")).hexdigest()
    return Path(cache_dir) / key[:2] / f"{key}.ocr.pdf"


def run_ocr(
    source: Path,
    destination: Path,
    *,
    engine: str = "ocrmypdf",
    language: str = "eng",
    timeout: int = 300,
    source_root: Optional[Path] = None,
) -> Tuple[bool, Optional[str]]:
    """OCR ``source`` into ``destination``, leaving ``source`` untouched.

    The source PDF is copied to a temporary file first and the OCR engine is
    pointed at the copy, so an engine bug cannot write back into the
    production folder.  ``--skip-text`` is passed so existing text layers are
    preserved rather than replaced.

    Returns
    -------
    tuple
        ``(success, error_message)``.
    """
    from .inventory import assert_read_only

    if source_root is not None:
        assert_read_only(source_root, destination)

    if not ocr_available(engine):
        return False, f"{engine} is not installed or not on PATH"

    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return True, "cached"

    with tempfile.TemporaryDirectory(prefix="wri_ocr_") as tmpdir:
        staged = Path(tmpdir) / "input.pdf"
        staged_out = Path(tmpdir) / "output.pdf"
        try:
            shutil.copy2(source, staged)
        except OSError as exc:
            return False, f"could not stage source copy: {exc}"

        if engine == "ocrmypdf":
            command = [
                "ocrmypdf", "--skip-text", "--quiet", "--language", language,
                "--output-type", "pdf", str(staged), str(staged_out),
            ]
        else:
            command = [
                "tesseract", str(staged), str(staged_out.with_suffix("")),
                "-l", language, "pdf",
            ]

        try:
            completed = subprocess.run(
                command, capture_output=True, timeout=timeout, check=False
            )
        except subprocess.TimeoutExpired:
            return False, f"OCR timed out after {timeout}s"
        except OSError as exc:  # pragma: no cover - environmental
            return False, f"could not launch {engine}: {exc}"

        if completed.returncode not in (0, 6):  # 6 = ocrmypdf "already has text"
            # stderr can echo document text; record only the exit code.
            return False, f"{engine} exited with code {completed.returncode}"
        if not staged_out.exists():
            return False, f"{engine} produced no output"
        try:
            shutil.move(str(staged_out), str(destination))
        except OSError as exc:
            return False, f"could not move OCR output into cache: {exc}"
    return True, None


def cache_size_bytes(cache_dir: Path) -> int:
    """Total bytes currently held in the OCR cache."""
    total = 0
    if not Path(cache_dir).is_dir():
        return 0
    for dirpath, _dirnames, filenames in os.walk(cache_dir):
        for name in filenames:
            try:
                total += (Path(dirpath) / name).stat().st_size
            except OSError:  # pragma: no cover - defensive
                pass
    return total


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------
def persist_extraction(
    database: Database,
    extraction: DocumentExtraction,
    thresholds: ExtractionThresholds,
    *,
    store_text: bool = True,
) -> None:
    """Write a document's page audits and text to the database.

    Text goes to ``page_text``/``page_text_fts`` only.  The caller's terminal
    and every Excel report remain free of document content.
    """
    database.replace_pages(
        extraction.file_id, [page.to_row(extraction.file_id) for page in extraction.pages]
    )
    if store_text:
        database.store_page_text(
            extraction.file_id,
            [(page.page_number, page.text) for page in extraction.pages],
            max_chars=thresholds.max_chars_per_page_stored,
        )

    status = (
        STATUS_ERROR
        if extraction.extraction_status == EXTRACT_FAILED
        else STATUS_PAGES_DONE
    )
    ocr_status = OCR_NOT_REQUIRED
    if any(page.ocr_status == OCR_REQUIRED for page in extraction.pages):
        ocr_status = OCR_REQUIRED
    elif any(page.ocr_status == OCR_COMPLETED for page in extraction.pages):
        ocr_status = OCR_COMPLETED
    elif any(page.ocr_status == OCR_FAILED for page in extraction.pages):
        ocr_status = OCR_FAILED
    elif any(page.ocr_status == OCR_SKIPPED for page in extraction.pages):
        ocr_status = OCR_SKIPPED

    database.set_file_status(
        extraction.file_id,
        processing_status=status,
        extraction_status=extraction.extraction_status,
        ocr_status=ocr_status,
        error_message=extraction.error_message,
    )


def summarize_document_condition(pages: Sequence[PageAudit]) -> Dict[str, Any]:
    """Roll per-page conditions up to a document-level summary."""
    if not pages:
        return {
            "searchable_status": "unknown",
            "apparent_blank_status": "unknown",
            "pages_audited": 0,
        }
    conditions = [page.page_condition for page in pages]
    searchable = sum(1 for c in conditions if c == COND_SEARCHABLE)
    image_only = sum(1 for c in conditions if c == COND_IMAGE_ONLY)
    blank = sum(1 for c in conditions if c == COND_APPARENT_BLANK)
    bates_only = sum(1 for c in conditions if c == COND_BATES_ONLY)
    total = len(conditions)

    if searchable == total:
        searchable_status = "fully_searchable"
    elif searchable == 0 and image_only > 0:
        searchable_status = "no_text_layer"
    elif searchable > 0:
        searchable_status = "partially_searchable"
    else:
        searchable_status = "no_text_layer"

    if blank + bates_only == total:
        blank_status = "all_pages_blank_or_bates_only"
    elif blank + bates_only > 0:
        blank_status = "some_pages_blank_or_bates_only"
    else:
        blank_status = "no_blank_pages_detected"

    return {
        "searchable_status": searchable_status,
        "apparent_blank_status": blank_status,
        "pages_audited": total,
        "pages_searchable": searchable,
        "pages_image_only": image_only,
        "pages_blank": blank,
        "pages_bates_only": bates_only,
        "pages_corrupt": sum(1 for c in conditions if c == COND_CORRUPT),
        "pages_uncertain": sum(1 for c in conditions if c == COND_UNCERTAIN),
    }
