"""Phase 1 -- structural inventory.

Phase 1 deliberately does **not** read substantive document content.  It walks
the read-only source folder, records structural facts about every file, hashes
each one, and safely probes PDFs for page count and encryption.

Everything here is either *observed* (size, timestamps, filename) or
*calculated* (SHA-256, page count, duplicate groups).  Nothing is inferred.
"""

from __future__ import annotations

import fnmatch
import hashlib
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple

from .bates import BatesParser
from .config import Config, FolderCandidate
from .database import (
    Database,
    EXTRACT_NOT_ATTEMPTED,
    OCR_NOT_REQUIRED,
    STATUS_ERROR,
    STATUS_INVENTORIED,
    STATUS_PLACEHOLDER,
    utc_now,
)
from .logging_setup import get_logger
from .version import APP_VERSION

log = get_logger("inventory")

PHASE = "phase1"


# ---------------------------------------------------------------------------
# folder location
# ---------------------------------------------------------------------------
def find_source_folders(config: Config, name: Optional[str] = None) -> List[FolderCandidate]:
    """Search the configured roots for directories matching the source name.

    The search is bounded by ``paths.search_max_depth`` and never follows
    symlinks, so a recursive Drive alias cannot send it into a loop.

    Returns
    -------
    list of FolderCandidate
        Every match, with a cheap size summary so the operator can tell a real
        production folder from an empty shortcut.  Never modifies anything.
    """
    target = name or config.source_folder_name()
    max_depth = int(config.get("paths", "search_max_depth", default=6))
    candidates: List[FolderCandidate] = []
    seen: set[str] = set()

    for root in config.search_roots():
        log.info("Searching for %r under %s", target, root)
        for directory in _walk_for_name(root, target, max_depth):
            resolved = str(directory)
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(_summarize_folder(directory))
    return candidates


def _walk_for_name(root: Path, target: str, max_depth: int) -> Iterator[Path]:
    """Yield directories named ``target`` beneath ``root``, depth-limited."""
    root_depth = len(root.parts)
    try:
        walker = os.walk(root, followlinks=False, onerror=lambda _e: None)
        for dirpath, dirnames, _filenames in walker:
            current = Path(dirpath)
            if len(current.parts) - root_depth >= max_depth:
                dirnames[:] = []
                continue
            # Skip system noise that can be enormous and is never the target.
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") or d.lower() == target.lower()
            ]
            for name in list(dirnames):
                if name == target:
                    yield current / name
    except (PermissionError, OSError) as exc:  # pragma: no cover - environmental
        log.warning("Could not search %s: %s", root, exc)


def _summarize_folder(directory: Path, limit: int = 200_000) -> FolderCandidate:
    """Count files/PDFs/bytes in a candidate folder without reading contents."""
    files = pdfs = 0
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(directory, followlinks=False):
            for filename in filenames:
                files += 1
                if filename.lower().endswith(".pdf"):
                    pdfs += 1
                try:
                    total += (Path(dirpath) / filename).stat().st_size
                except OSError:
                    pass
                if files >= limit:
                    return FolderCandidate(directory, files, pdfs, total)
    except OSError as exc:  # pragma: no cover - environmental
        log.warning("Could not summarize %s: %s", directory, exc)
    return FolderCandidate(directory, files, pdfs, total)


# ---------------------------------------------------------------------------
# read-only enforcement
# ---------------------------------------------------------------------------
class ReadOnlySourceError(RuntimeError):
    """Raised when an operation would write to the read-only source folder."""


def assert_read_only(source: Path, candidate: Path) -> None:
    """Raise if ``candidate`` lies inside the read-only ``source`` folder.

    Every function in this package that opens a file for writing routes
    through this check.  It is the programmatic expression of safeguard #1:
    the source production is never renamed, moved, altered, annotated, OCRed
    in place, combined or deleted.
    """
    try:
        resolved_source = Path(source).resolve()
        resolved_candidate = Path(candidate).resolve()
    except OSError as exc:  # pragma: no cover - defensive
        raise ReadOnlySourceError(f"Could not resolve path: {exc}") from exc
    if resolved_candidate == resolved_source:
        raise ReadOnlySourceError(f"Refusing to write to the source folder: {candidate}")
    try:
        resolved_candidate.relative_to(resolved_source)
    except ValueError:
        return
    raise ReadOnlySourceError(
        f"Refusing to write inside the read-only source folder: {candidate}"
    )


# ---------------------------------------------------------------------------
# per-file structural facts
# ---------------------------------------------------------------------------
@dataclass
class ProbeResult:
    """Structural facts gathered about a single file."""

    abs_path: str
    rel_path: str
    filename: str
    extension: str
    file_size: int
    created_ts: Optional[str]
    modified_ts: Optional[str]
    sha256: Optional[str] = None
    page_count: Optional[int] = None
    is_pdf: bool = False
    is_encrypted: bool = False
    is_corrupt: bool = False
    is_placeholder: bool = False
    error_message: Optional[str] = None
    notes: List[str] = field(default_factory=list)

    def to_row(self) -> Dict[str, Any]:
        """Convert to a ``files`` table row (Bates fields added by the caller)."""
        status = STATUS_INVENTORIED
        if self.is_placeholder:
            status = STATUS_PLACEHOLDER
        elif self.is_corrupt or (self.error_message and self.sha256 is None):
            status = STATUS_ERROR
        return {
            "abs_path": self.abs_path,
            "rel_path": self.rel_path,
            "filename": self.filename,
            "extension": self.extension,
            "file_size": self.file_size,
            "created_ts": self.created_ts,
            "modified_ts": self.modified_ts,
            "sha256": self.sha256,
            "page_count": self.page_count,
            "is_pdf": int(self.is_pdf),
            "is_encrypted": int(self.is_encrypted),
            "is_corrupt": int(self.is_corrupt),
            "is_placeholder": int(self.is_placeholder),
            "processing_status": status,
            "extraction_status": EXTRACT_NOT_ATTEMPTED,
            "ocr_status": OCR_NOT_REQUIRED,
            "last_processed_ts": utc_now(),
            "error_message": self.error_message,
            "app_version": APP_VERSION,
            "notes": "; ".join(self.notes) if self.notes else None,
        }


def _iso(timestamp: Optional[float]) -> Optional[str]:
    """Convert an epoch timestamp to an ISO-8601 UTC string."""
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat(
            timespec="seconds"
        )
    except (OverflowError, OSError, ValueError):  # pragma: no cover - defensive
        return None


def sha256_file(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    """Stream a file through SHA-256 without loading it into memory."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def looks_like_placeholder(
    path: Path, size: int, *, max_stub_bytes: int, placeholder_extensions: Sequence[str]
) -> bool:
    """Heuristically detect a Google Drive cloud placeholder.

    A placeholder is a stub left on disk for a file that has not been
    downloaded yet.  Treating one as corrupt would permanently poison the
    index, so they are detected, logged and retried instead.
    """
    if path.suffix.lower() in {e.lower() for e in placeholder_extensions}:
        return True
    if size == 0:
        return True
    if path.suffix.lower() == ".pdf" and size <= max_stub_bytes:
        try:
            with open(path, "rb") as handle:
                header = handle.read(5)
            return header != b"%PDF-"
        except OSError:
            return True
    return False


def probe_pdf(path: Path) -> Tuple[Optional[int], bool, bool, Optional[str]]:
    """Safely read a PDF's page count and encryption flag.

    The file is opened read-only and closed immediately.  No content is
    extracted, decoded or printed.

    Returns
    -------
    tuple
        ``(page_count, is_encrypted, is_corrupt, error_message)``.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover - dependency documented in README
        return None, False, False, "PyMuPDF is not installed"

    document = None
    try:
        document = fitz.open(str(path))
        encrypted = bool(document.needs_pass)
        if encrypted:
            # An encrypted document may still report its page count; try, but
            # never attempt to guess or crack a password.
            try:
                pages = document.page_count
            except Exception:
                pages = None
            return pages, True, False, "password-protected"
        return document.page_count, False, False, None
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        # Fall back to pypdf, which tolerates some files MuPDF rejects.
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path), strict=False)
            if reader.is_encrypted:
                return None, True, False, "password-protected"
            return len(reader.pages), False, False, f"recovered by pypdf ({message})"
        except Exception as fallback_exc:
            return (
                None,
                False,
                True,
                f"{message}; pypdf: {type(fallback_exc).__name__}: {fallback_exc}",
            )
    finally:
        if document is not None:
            try:
                document.close()
            except Exception:  # pragma: no cover - defensive
                pass


def probe_file(
    path_str: str,
    source_str: str,
    *,
    pdf_extensions: Sequence[str],
    hash_chunk_bytes: int,
    placeholder_enabled: bool,
    max_stub_bytes: int,
    placeholder_extensions: Sequence[str],
    retries: int,
    backoff_seconds: Sequence[float],
) -> ProbeResult:
    """Gather all Phase 1 facts about one file.

    This function is the unit of work handed to the process pool.  It takes
    and returns only primitives so it can be pickled cheaply, and it never
    raises: failures are recorded on the result.
    """
    path = Path(path_str)
    source = Path(source_str)
    try:
        rel = str(path.relative_to(source))
    except ValueError:  # pragma: no cover - defensive
        rel = path.name

    try:
        stat = path.stat()
    except OSError as exc:
        return ProbeResult(
            abs_path=str(path),
            rel_path=rel,
            filename=path.name,
            extension=path.suffix.lower(),
            file_size=0,
            created_ts=None,
            modified_ts=None,
            is_corrupt=True,
            error_message=f"stat failed: {type(exc).__name__}: {exc}",
        )

    created = getattr(stat, "st_birthtime", None)
    result = ProbeResult(
        abs_path=str(path),
        rel_path=rel,
        filename=path.name,
        extension=path.suffix.lower(),
        file_size=stat.st_size,
        created_ts=_iso(created) if created else None,
        modified_ts=_iso(stat.st_mtime),
        is_pdf=path.suffix.lower() in {e.lower() for e in pdf_extensions},
    )

    if placeholder_enabled and looks_like_placeholder(
        path,
        stat.st_size,
        max_stub_bytes=max_stub_bytes,
        placeholder_extensions=placeholder_extensions,
    ):
        # Retry with backoff: Drive may be mid-download.
        for attempt, delay in enumerate(list(backoff_seconds)[:retries], start=1):
            time.sleep(delay)
            try:
                stat = path.stat()
            except OSError:
                break
            if not looks_like_placeholder(
                path,
                stat.st_size,
                max_stub_bytes=max_stub_bytes,
                placeholder_extensions=placeholder_extensions,
            ):
                result.file_size = stat.st_size
                result.modified_ts = _iso(stat.st_mtime)
                result.notes.append(f"downloaded after {attempt} retry attempt(s)")
                break
        else:
            result.is_placeholder = True
            result.error_message = (
                "appears to be a cloud placeholder that is not fully downloaded"
            )
            result.notes.append(
                "Not treated as corrupt. Use Finder > 'Make available offline' "
                "and re-run to index this file."
            )
            return result

        if looks_like_placeholder(
            path,
            result.file_size,
            max_stub_bytes=max_stub_bytes,
            placeholder_extensions=placeholder_extensions,
        ):
            result.is_placeholder = True
            result.error_message = (
                "appears to be a cloud placeholder that is not fully downloaded"
            )
            return result

    try:
        result.sha256 = sha256_file(path, hash_chunk_bytes)
    except OSError as exc:
        result.is_corrupt = True
        result.error_message = f"hash failed: {type(exc).__name__}: {exc}"
        return result

    if result.is_pdf:
        pages, encrypted, corrupt, message = probe_pdf(path)
        result.page_count = pages
        result.is_encrypted = encrypted
        result.is_corrupt = corrupt
        if message:
            result.error_message = message
    return result


# ---------------------------------------------------------------------------
# walking
# ---------------------------------------------------------------------------
def iter_source_files(source: Path, ignore_globs: Sequence[str]) -> Iterator[Path]:
    """Yield every file beneath ``source``, honouring the ignore list.

    Symlinks are not followed.  The walk is streaming: the full file list is
    never materialised, which matters for tens of thousands of documents.
    """
    patterns = list(ignore_globs or [])
    for dirpath, dirnames, filenames in os.walk(source, followlinks=False):
        dirnames[:] = [
            d for d in dirnames
            if not _matches_any(str(Path(dirpath, d).relative_to(source)) + "/", patterns)
            and not _matches_any(d, patterns)
        ]
        for filename in filenames:
            path = Path(dirpath) / filename
            try:
                rel = str(path.relative_to(source))
            except ValueError:  # pragma: no cover - defensive
                rel = filename
            if _matches_any(filename, patterns) or _matches_any(rel, patterns):
                continue
            yield path


def _matches_any(value: str, patterns: Sequence[str]) -> bool:
    """Return ``True`` when ``value`` matches any glob in ``patterns``."""
    return any(fnmatch.fnmatch(value, pattern) for pattern in patterns)


# ---------------------------------------------------------------------------
# phase 1 driver
# ---------------------------------------------------------------------------
@dataclass
class Phase1Result:
    """Aggregate counters returned by :func:`run_phase1`."""

    scanned: int = 0
    processed: int = 0
    skipped_unchanged: int = 0
    errors: int = 0
    placeholders: int = 0
    pdfs: int = 0
    total_bytes: int = 0


def run_phase1(
    config: Config,
    database: Database,
    source: Path,
    *,
    workers: Optional[int] = None,
    limit: Optional[int] = None,
    force: bool = False,
    progress: bool = True,
) -> Phase1Result:
    """Run the structural inventory over the whole source folder.

    The run is resumable: a file already recorded as inventoried whose size
    and modification timestamp are unchanged is skipped unless ``force`` is
    set.  Work is committed in batches so an interruption loses at most one
    batch.

    Parameters
    ----------
    config, database, source:
        Configuration, open database, and the read-only production folder.
    workers:
        Process-pool size.  Defaults to the conservative configured value.
    limit:
        Stop after this many *new* files (used for smoke tests).
    force:
        Re-probe every file even if unchanged.
    progress:
        Show a progress bar when :mod:`tqdm` is available.

    Returns
    -------
    Phase1Result
        Aggregate counters only -- never document content.
    """
    inventory_cfg = config.section("inventory")
    placeholder_cfg = config.section("cloud_placeholder")
    worker_count = workers or config.worker_count()
    checkpoint_every = int(config.get("performance", "checkpoint_every", default=250))

    probe_kwargs = dict(
        pdf_extensions=inventory_cfg.get("pdf_extensions", [".pdf"]),
        hash_chunk_bytes=int(inventory_cfg.get("hash_chunk_bytes", 1024 * 1024)),
        placeholder_enabled=bool(placeholder_cfg.get("enabled", True)),
        max_stub_bytes=int(placeholder_cfg.get("max_stub_bytes", 1024)),
        placeholder_extensions=placeholder_cfg.get("placeholder_extensions", []),
        retries=int(placeholder_cfg.get("retries", 4)),
        backoff_seconds=placeholder_cfg.get("backoff_seconds", [2, 4, 8, 16]),
    )

    parser = BatesParser.from_config(config)
    result = Phase1Result()
    database.audit(
        "phase1_start",
        phase=PHASE,
        target=str(source),
        outcome="started",
        detail={"workers": worker_count, "force": force},
    )
    log.info("Phase 1 starting: source=%s workers=%d", source, worker_count)

    pending: List[Path] = []
    for path in iter_source_files(source, inventory_cfg.get("ignore_globs", [])):
        result.scanned += 1
        if limit is not None and len(pending) >= limit:
            break
        if not force:
            try:
                stat = path.stat()
            except OSError:
                pending.append(path)
                continue
            if not database.needs_processing(
                str(path), stat.st_size, _iso(stat.st_mtime) or ""
            ):
                result.skipped_unchanged += 1
                continue
        pending.append(path)

    log.info(
        "Discovered %d files; %d already current and skipped; %d to process",
        result.scanned, result.skipped_unchanged, len(pending),
    )

    if not pending:
        _finalize_phase1(config, database, source, result)
        return result

    bar = _make_progress_bar(len(pending), "Phase 1 inventory", progress)
    batch: List[Tuple[ProbeResult, Dict[str, Any]]] = []

    def flush(rows: List[Tuple[ProbeResult, Dict[str, Any]]]) -> None:
        """Persist a batch of probe results."""
        for probe, extra in rows:
            row = probe.to_row()
            row.update(extra)
            database.upsert_file(row)
        rows.clear()

    try:
        if worker_count > 1 and len(pending) > 1:
            with ProcessPoolExecutor(max_workers=worker_count) as pool:
                futures = {
                    pool.submit(probe_file, str(path), str(source), **probe_kwargs): path
                    for path in pending
                }
                for future in as_completed(futures):
                    probe = _collect(future, futures[future], source)
                    batch.append((probe, _bates_fields(parser, probe)))
                    _tally(result, probe)
                    if bar is not None:
                        bar.update(1)
                    if len(batch) >= checkpoint_every:
                        flush(batch)
        else:
            for path in pending:
                probe = probe_file(str(path), str(source), **probe_kwargs)
                batch.append((probe, _bates_fields(parser, probe)))
                _tally(result, probe)
                if bar is not None:
                    bar.update(1)
                if len(batch) >= checkpoint_every:
                    flush(batch)
    finally:
        flush(batch)
        if bar is not None:
            bar.close()

    _mark_duplicate_filenames(database)
    _assign_exact_duplicate_groups(database)
    _finalize_phase1(config, database, source, result)
    return result


def _collect(future, path: Path, source: Path) -> ProbeResult:
    """Unwrap a worker future, converting a crash into a recorded error."""
    try:
        return future.result()
    except Exception as exc:  # pragma: no cover - worker crash path
        log.error("Worker failed for %s: %s", path.name, type(exc).__name__)
        try:
            rel = str(path.relative_to(source))
        except ValueError:
            rel = path.name
        return ProbeResult(
            abs_path=str(path),
            rel_path=rel,
            filename=path.name,
            extension=path.suffix.lower(),
            file_size=0,
            created_ts=None,
            modified_ts=None,
            is_corrupt=True,
            error_message=f"worker error: {type(exc).__name__}: {exc}",
        )


def _bates_fields(parser: BatesParser, probe: ProbeResult) -> Dict[str, Any]:
    """Derive the filename-Bates columns for a probed file."""
    bates = parser.parse_filename(probe.filename)
    return {
        "filename_bates": bates.normalized if bates else None,
        "filename_bates_num": bates.number if bates else None,
        "filename_compliant": int(parser.is_filename_compliant(probe.filename)),
    }


def _tally(result: Phase1Result, probe: ProbeResult) -> None:
    """Update aggregate counters from one probe result."""
    result.processed += 1
    result.total_bytes += probe.file_size
    if probe.is_pdf:
        result.pdfs += 1
    if probe.is_placeholder:
        result.placeholders += 1
    elif probe.is_corrupt:
        result.errors += 1


def _make_progress_bar(total: int, description: str, enabled: bool):
    """Return a tqdm bar, or ``None`` when unavailable or disabled."""
    if not enabled:
        return None
    try:
        from tqdm import tqdm
    except ImportError:  # pragma: no cover - optional dependency
        return None
    return tqdm(total=total, desc=description, unit="file", dynamic_ncols=True)


def _mark_duplicate_filenames(database: Database) -> None:
    """Flag files whose basename occurs more than once in the production."""
    database.execute("UPDATE files SET duplicate_filename = 0")
    with database.transaction() as conn:
        conn.execute(
            """
            UPDATE files SET duplicate_filename = 1
            WHERE filename IN (
                SELECT filename FROM files GROUP BY filename HAVING COUNT(*) > 1
            )
            """
        )


def _assign_exact_duplicate_groups(database: Database) -> None:
    """Group files that share a SHA-256 digest.

    The group identifier is the digest prefix, which makes the grouping
    self-verifying: anyone can re-hash a file and confirm its group.
    """
    database.execute("UPDATE files SET exact_dup_group = NULL")
    with database.transaction() as conn:
        conn.execute(
            """
            UPDATE files SET exact_dup_group = 'SHA-' || substr(sha256, 1, 12)
            WHERE sha256 IS NOT NULL AND sha256 IN (
                SELECT sha256 FROM files
                WHERE sha256 IS NOT NULL
                GROUP BY sha256 HAVING COUNT(*) > 1
            )
            """
        )
    rows = database.query(
        "SELECT exact_dup_group AS gid, file_id FROM files "
        "WHERE exact_dup_group IS NOT NULL"
    )
    database.clear_duplicate_groups("exact_binary")
    database.add_duplicate_members(
        "exact_binary",
        [
            {"group_id": row["gid"], "file_id": row["file_id"],
             "similarity": 100.0, "relation": "exact_binary_duplicate"}
            for row in rows
        ],
    )


def _finalize_phase1(
    config: Config, database: Database, source: Path, result: Phase1Result
) -> None:
    """Record Phase 1 statistics and close out the audit entry."""
    stats = collect_phase1_stats(config, database, source)
    database.set_stats(PHASE, stats)
    database.audit(
        "phase1_complete",
        phase=PHASE,
        target=str(source),
        outcome="completed",
        detail={
            "scanned": result.scanned,
            "processed": result.processed,
            "skipped_unchanged": result.skipped_unchanged,
            "errors": result.errors,
            "placeholders": result.placeholders,
        },
    )
    log.info(
        "Phase 1 complete: %d processed, %d skipped, %d errors, %d placeholders",
        result.processed, result.skipped_unchanged, result.errors, result.placeholders,
    )


def collect_phase1_stats(
    config: Config, database: Database, source: Path
) -> Dict[str, Any]:
    """Compute the aggregate statistics reported at the end of Phase 1."""
    from .bates import find_filename_gaps, summarize_numbers

    total_files = database.scalar("SELECT COUNT(*) FROM files")
    pdf_files = database.scalar("SELECT COUNT(*) FROM files WHERE is_pdf = 1")
    total_bytes = database.scalar("SELECT COALESCE(SUM(file_size), 0) FROM files")
    encrypted = database.scalar("SELECT COUNT(*) FROM files WHERE is_encrypted = 1")
    corrupt = database.scalar("SELECT COUNT(*) FROM files WHERE is_corrupt = 1")
    placeholders = database.scalar("SELECT COUNT(*) FROM files WHERE is_placeholder = 1")
    non_compliant = database.scalar(
        "SELECT COUNT(*) FROM files WHERE is_pdf = 1 AND filename_compliant = 0"
    )
    missing_bates = database.scalar(
        "SELECT COUNT(*) FROM files WHERE filename_bates_num IS NULL"
    )
    dup_filenames = database.scalar(
        "SELECT COUNT(*) FROM files WHERE duplicate_filename = 1"
    )
    dup_groups = database.scalar(
        "SELECT COUNT(DISTINCT exact_dup_group) FROM files "
        "WHERE exact_dup_group IS NOT NULL"
    )
    dup_files = database.scalar(
        "SELECT COUNT(*) FROM files WHERE exact_dup_group IS NOT NULL"
    )

    numbers = [
        row["filename_bates_num"]
        for row in database.query(
            "SELECT filename_bates_num FROM files WHERE filename_bates_num IS NOT NULL"
        )
    ]
    bates_summary = summarize_numbers(numbers)
    gaps = find_filename_gaps(numbers, preliminary=True)

    distribution: Dict[str, int] = {}
    for row in database.query(
        "SELECT page_count, COUNT(*) AS n FROM files WHERE is_pdf = 1 "
        "GROUP BY page_count ORDER BY page_count"
    ):
        key = "unknown" if row["page_count"] is None else str(row["page_count"])
        distribution[key] = row["n"]

    extensions: Dict[str, int] = {
        (row["extension"] or "(none)"): row["n"]
        for row in database.query(
            "SELECT extension, COUNT(*) AS n FROM files GROUP BY extension "
            "ORDER BY n DESC"
        )
    }

    return {
        "source_folder": str(source),
        "total_files": total_files,
        "pdf_files": pdf_files,
        "non_pdf_files": total_files - pdf_files,
        "total_bytes": total_bytes,
        "total_gib": round(total_bytes / (1024**3), 3),
        "encrypted_pdfs": encrypted,
        "corrupt_or_unreadable": corrupt,
        "cloud_placeholders": placeholders,
        "filename_non_compliant_pdfs": non_compliant,
        "files_without_filename_bates": missing_bates,
        "files_with_duplicate_filenames": dup_filenames,
        "exact_duplicate_groups": dup_groups,
        "files_in_exact_duplicate_groups": dup_files,
        "bates_min": bates_summary["min"],
        "bates_max": bates_summary["max"],
        "bates_distinct": bates_summary["distinct"],
        "bates_span": bates_summary["span"],
        "preliminary_filename_gap_count": len(gaps),
        "preliminary_missing_bates_numbers": sum(g.missing_count for g in gaps),
        "page_count_distribution": distribution,
        "extension_distribution": extensions,
        "total_pages_observed": database.scalar(
            "SELECT COALESCE(SUM(page_count), 0) FROM files WHERE is_pdf = 1"
        ),
        "app_version": APP_VERSION,
        "completed_ts": utc_now(),
    }
