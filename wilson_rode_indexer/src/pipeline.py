"""Phase 2 and Phase 3 drivers.

Phase 2 audits page conditions and extracts text.  Phase 3 derives review
metadata, tags issues, detects duplicates, infers families and scores
priority.  Both are resumable and stream their work.
"""

from __future__ import annotations

import random
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple

from .bates import (
    BatesParser,
    CONF_UNKNOWN as BATES_CONF_UNKNOWN,
    SOURCE_NONE,
    build_range,
)
from .config import Config
from .database import (
    Database,
    EXTRACT_FAILED,
    OCR_COMPLETED,
    OCR_FAILED,
    OCR_REQUIRED,
    OCR_SKIPPED,
    STATUS_METADATA_DONE,
    STATUS_PAGES_DONE,
)
from .document_family import infer_families, load_candidates, persist_relations
from .duplicates import (
    KIND_NEAR,
    KIND_TEXT,
    TextNormalizer,
    build_fingerprint,
    exact_binary_pairs,
    group_exact_text,
    group_lookup,
    group_near_duplicates,
    persist_groups,
)
from .issue_tags import IssueTagger
from .logging_setup import get_logger
from .metadata_extract import DocumentClassifier, EmailParser, derive_metadata
from .pdf_extract import (
    COND_APPARENT_BLANK,
    COND_BATES_ONLY,
    COND_IMAGE_ONLY,
    ExtractionThresholds,
    extract_document,
    ocr_available,
    ocr_cache_path,
    persist_extraction,
    run_ocr,
    summarize_document_condition,
)
from .priority import PriorityScorer

log = get_logger("pipeline")

PHASE2 = "phase2"
PHASE3 = "phase3"


# ===========================================================================
# Phase 2 -- pilot sampling
# ===========================================================================
@dataclass
class PilotSample:
    """A stratified pilot sample plus a record of what could not be filled."""

    file_ids: List[int] = field(default_factory=list)
    strata: Dict[str, List[int]] = field(default_factory=dict)
    shortfalls: Dict[str, int] = field(default_factory=dict)

    @property
    def size(self) -> int:
        """Number of distinct documents in the sample."""
        return len(self.file_ids)


#: SQL fragments defining each pilot stratum.  Each must select ``file_id``.
_STRATUM_SQL: Dict[str, str] = {
    "low_bates": (
        "SELECT file_id FROM files WHERE is_pdf=1 AND filename_bates_num IS NOT NULL "
        "AND is_corrupt=0 ORDER BY filename_bates_num ASC LIMIT ?"
    ),
    "high_bates": (
        "SELECT file_id FROM files WHERE is_pdf=1 AND filename_bates_num IS NOT NULL "
        "AND is_corrupt=0 ORDER BY filename_bates_num DESC LIMIT ?"
    ),
    "small_files": (
        "SELECT file_id FROM files WHERE is_pdf=1 AND is_corrupt=0 AND file_size>0 "
        "ORDER BY file_size ASC LIMIT ?"
    ),
    "large_files": (
        "SELECT file_id FROM files WHERE is_pdf=1 AND is_corrupt=0 "
        "ORDER BY file_size DESC LIMIT ?"
    ),
    "single_page": (
        "SELECT file_id FROM files WHERE is_pdf=1 AND page_count=1 AND is_corrupt=0 "
        "ORDER BY RANDOM() LIMIT ?"
    ),
    "multi_page": (
        "SELECT file_id FROM files WHERE is_pdf=1 AND page_count>1 AND is_corrupt=0 "
        "ORDER BY page_count DESC LIMIT ?"
    ),
    # Bytes-per-page is a good cheap proxy: text-only PDFs are small per page,
    # scanned images are large per page.
    "suspected_searchable": (
        "SELECT file_id FROM files WHERE is_pdf=1 AND is_corrupt=0 AND page_count>0 "
        "AND (file_size / page_count) < 60000 ORDER BY RANDOM() LIMIT ?"
    ),
    "suspected_image_only": (
        "SELECT file_id FROM files WHERE is_pdf=1 AND is_corrupt=0 AND page_count>0 "
        "AND (file_size / page_count) > 150000 ORDER BY RANDOM() LIMIT ?"
    ),
    "suspected_blank": (
        "SELECT file_id FROM files WHERE is_pdf=1 AND is_corrupt=0 AND page_count>0 "
        "AND (file_size / page_count) < 6000 ORDER BY RANDOM() LIMIT ?"
    ),
    "exact_duplicates": (
        "SELECT file_id FROM files WHERE is_pdf=1 AND exact_dup_group IS NOT NULL "
        "AND is_corrupt=0 ORDER BY exact_dup_group LIMIT ?"
    ),
    "malformed_names": (
        "SELECT file_id FROM files WHERE is_pdf=1 AND filename_compliant=0 "
        "AND is_corrupt=0 ORDER BY RANDOM() LIMIT ?"
    ),
}


def select_pilot_sample(config: Config, database: Database) -> PilotSample:
    """Select a stratified pilot sample covering the required document kinds.

    Each stratum is filled as far as the collection allows.  Strata that could
    not be filled are recorded in ``shortfalls`` and reported, so the pilot
    never silently under-covers a category.
    """
    strata_config = config.get("pilot", "strata") or {}
    target = int(config.get("pilot", "target_size", default=200))
    seed = int(config.get("qc", "random_seed", default=20260731))
    rng = random.Random(seed)

    sample = PilotSample()
    chosen: Set[int] = set()
    for name, quota in strata_config.items():
        sql = _STRATUM_SQL.get(name)
        if sql is None:
            log.warning("Unknown pilot stratum %r in config; skipping", name)
            continue
        wanted = int(quota)
        rows = database.query(sql, (wanted * 3,))
        picked: List[int] = []
        for row in rows:
            if row["file_id"] not in chosen:
                picked.append(row["file_id"])
                chosen.add(row["file_id"])
            if len(picked) >= wanted:
                break
        sample.strata[name] = picked
        if len(picked) < wanted:
            sample.shortfalls[name] = wanted - len(picked)

    # Top up with a random draw if the strata under-filled the target.
    if len(chosen) < target:
        extra = database.query(
            "SELECT file_id FROM files WHERE is_pdf=1 AND is_corrupt=0 "
            "ORDER BY RANDOM() LIMIT ?",
            (target * 2,),
        )
        for row in extra:
            if len(chosen) >= target:
                break
            if row["file_id"] not in chosen:
                chosen.add(row["file_id"])
                sample.strata.setdefault("random_topup", []).append(row["file_id"])

    sample.file_ids = sorted(chosen)
    log.info(
        "Pilot sample: %d document(s) across %d stratum/strata (%d shortfall(s))",
        sample.size, len(sample.strata), len(sample.shortfalls),
    )
    for name, missing in sample.shortfalls.items():
        log.warning("Pilot stratum %r short by %d document(s)", name, missing)
    return sample


# ===========================================================================
# Phase 2 -- extraction driver
# ===========================================================================
@dataclass
class Phase2Result:
    """Aggregate counters returned by :func:`run_phase2`."""

    documents: int = 0
    pages: int = 0
    failures: int = 0
    ocr_required: int = 0
    ocr_completed: int = 0
    ocr_failed: int = 0
    skipped: int = 0


def _extract_worker(
    abs_path: str,
    file_id: int,
    bates_kwargs: Dict[str, Any],
    threshold_kwargs: Dict[str, Any],
):
    """Process-pool entry point for one document."""
    parser = BatesParser(**bates_kwargs)
    thresholds = ExtractionThresholds(**threshold_kwargs)
    return extract_document(Path(abs_path), file_id, parser, thresholds)


def run_phase2(
    config: Config,
    database: Database,
    source: Path,
    output_dir: Path,
    *,
    file_ids: Optional[Sequence[int]] = None,
    workers: Optional[int] = None,
    force: bool = False,
    enable_ocr: Optional[bool] = None,
    progress: bool = True,
) -> Phase2Result:
    """Extract text and audit page conditions.

    Parameters
    ----------
    file_ids:
        Restrict processing to these documents (the pilot sample).  ``None``
        processes every PDF.
    force:
        Re-extract documents already marked as done.
    enable_ocr:
        Override ``ocr.enabled``.  OCR always writes to the cache inside the
        derived-index folder and never touches the source.

    Returns
    -------
    Phase2Result
        Counters only.  No document text is returned, logged or printed.
    """
    thresholds = ExtractionThresholds.from_config(config)
    parser = BatesParser.from_config(config)
    worker_count = workers or config.worker_count()
    checkpoint = int(config.get("performance", "checkpoint_every", default=250))
    ocr_enabled = config.ocr_enabled() if enable_ocr is None else enable_ocr
    ocr_cfg = config.section("ocr")
    cache_dir = Path(output_dir) / str(ocr_cfg.get("cache_dirname", "ocr_cache"))

    bates_kwargs = dict(
        filename_regex=config.get("bates", "filename_regex"),
        page_regex=config.get("bates", "page_regex"),
        prefix=config.get("bates", "prefix", default="WILSONRODE"),
        pad_width=int(config.get("bates", "pad_width", default=6)),
        filename_pattern=config.get("bates", "filename_pattern"),
    )
    threshold_kwargs = dict(
        min_chars_for_text_layer=thresholds.min_chars_for_text_layer,
        blank_char_threshold=thresholds.blank_char_threshold,
        bates_only_extra_chars=thresholds.bates_only_extra_chars,
        image_coverage_threshold=thresholds.image_coverage_threshold,
        footer_fraction=thresholds.footer_fraction,
        max_chars_per_page_stored=thresholds.max_chars_per_page_stored,
    )

    targets = _phase2_targets(database, file_ids, force)
    result = Phase2Result()
    database.audit(
        "phase2_start",
        phase=PHASE2,
        target=str(source),
        outcome="started",
        detail={"documents": len(targets), "workers": worker_count,
                "ocr_enabled": ocr_enabled, "pilot": file_ids is not None},
    )
    log.info("Phase 2 starting: %d document(s), workers=%d, OCR=%s",
             len(targets), worker_count, "on" if ocr_enabled else "off")
    if not targets:
        log.info("Nothing to do; all requested documents are already extracted")
        return result

    if ocr_enabled and not ocr_available(str(ocr_cfg.get("engine", "ocrmypdf"))):
        log.warning(
            "OCR is enabled in config but %r is not installed; pages needing OCR "
            "will be reported as 'ocr_required' instead",
            ocr_cfg.get("engine", "ocrmypdf"),
        )
        ocr_enabled = False

    bar = _progress_bar(len(targets), "Phase 2 extraction", progress)
    processed_since_checkpoint = 0
    try:
        if worker_count > 1 and len(targets) > 1:
            with ProcessPoolExecutor(max_workers=worker_count) as pool:
                futures = {
                    pool.submit(_extract_worker, path, fid, bates_kwargs,
                                threshold_kwargs): (fid, path)
                    for fid, path in targets
                }
                for future in as_completed(futures):
                    fid, path = futures[future]
                    extraction = _safe_result(future, fid, path)
                    _finish_document(database, extraction, thresholds, result)
                    if bar is not None:
                        bar.update(1)
                    processed_since_checkpoint += 1
                    if processed_since_checkpoint >= checkpoint:
                        processed_since_checkpoint = 0
                        log.info("Checkpoint: %d document(s) extracted", result.documents)
        else:
            for fid, path in targets:
                extraction = _extract_worker(path, fid, bates_kwargs, threshold_kwargs)
                _finish_document(database, extraction, thresholds, result)
                if bar is not None:
                    bar.update(1)
    finally:
        if bar is not None:
            bar.close()

    if ocr_enabled:
        _run_ocr_pass(config, database, source, cache_dir, parser, thresholds, result,
                      progress=progress)

    _record_phase2_stats(database, result, file_ids is not None)
    log.info(
        "Phase 2 complete: %d document(s), %d page(s), %d failure(s), "
        "%d page(s) needing OCR",
        result.documents, result.pages, result.failures, result.ocr_required,
    )
    return result


def _phase2_targets(
    database: Database, file_ids: Optional[Sequence[int]], force: bool
) -> List[Tuple[int, str]]:
    """Resolve the list of ``(file_id, abs_path)`` pairs Phase 2 should process."""
    clauses = ["is_pdf = 1", "is_corrupt = 0", "is_encrypted = 0", "is_placeholder = 0"]
    params: List[Any] = []
    if file_ids is not None:
        if not file_ids:
            return []
        clauses.append(f"file_id IN ({','.join('?' * len(file_ids))})")
        params.extend(file_ids)
    if not force:
        clauses.append(
            "processing_status NOT IN ('pages_done', 'metadata_done')"
        )
    rows = database.query(
        f"SELECT file_id, abs_path FROM files WHERE {' AND '.join(clauses)} "
        "ORDER BY filename_bates_num, filename",
        params,
    )
    return [(row["file_id"], row["abs_path"]) for row in rows]


def _safe_result(future, file_id: int, path: str):
    """Unwrap an extraction future, converting a crash into a failed result."""
    from .pdf_extract import DocumentExtraction

    try:
        return future.result()
    except Exception as exc:  # pragma: no cover - worker crash path
        log.error("Extraction worker failed for file_id=%s: %s", file_id,
                  type(exc).__name__)
        return DocumentExtraction(
            file_id=file_id,
            abs_path=path,
            extraction_status=EXTRACT_FAILED,
            error_message=f"worker error: {type(exc).__name__}: {exc}",
        )


def _finish_document(
    database: Database, extraction, thresholds: ExtractionThresholds,
    result: Phase2Result,
) -> None:
    """Persist one extraction and update counters."""
    persist_extraction(database, extraction, thresholds)
    result.documents += 1
    result.pages += len(extraction.pages)
    if extraction.extraction_status == EXTRACT_FAILED:
        result.failures += 1
    result.ocr_required += len(extraction.ocr_required_pages)


def _run_ocr_pass(
    config: Config,
    database: Database,
    source: Path,
    cache_dir: Path,
    parser: BatesParser,
    thresholds: ExtractionThresholds,
    result: Phase2Result,
    *,
    progress: bool,
) -> None:
    """OCR documents that need it, writing derivatives to the cache only."""
    from .inventory import assert_read_only

    assert_read_only(source, cache_dir)
    ocr_cfg = config.section("ocr")
    engine = str(ocr_cfg.get("engine", "ocrmypdf"))
    language = str(ocr_cfg.get("language", "eng"))
    timeout = int(ocr_cfg.get("timeout_seconds", 300))
    max_cache_bytes = int(float(ocr_cfg.get("max_cache_gb", 20)) * (1024**3))

    rows = database.query(
        "SELECT DISTINCT f.file_id, f.abs_path, f.sha256 FROM files f "
        "JOIN pages p ON p.file_id = f.file_id "
        "WHERE p.ocr_status = ? ORDER BY f.filename_bates_num",
        (OCR_REQUIRED,),
    )
    if not rows:
        return

    from .pdf_extract import cache_size_bytes

    log.info("OCR pass: %d document(s) contain pages needing OCR", len(rows))
    bar = _progress_bar(len(rows), "Phase 2 OCR", progress)
    try:
        for row in rows:
            if cache_size_bytes(cache_dir) >= max_cache_bytes:
                log.warning(
                    "OCR cache has reached the configured limit of %.1f GiB; "
                    "remaining documents stay marked 'ocr_required'",
                    max_cache_bytes / (1024**3),
                )
                break
            destination = ocr_cache_path(cache_dir, Path(row["abs_path"]), row["sha256"])
            success, message = run_ocr(
                Path(row["abs_path"]), destination, engine=engine, language=language,
                timeout=timeout, source_root=source,
            )
            if success:
                extraction = extract_document(destination, row["file_id"], parser,
                                              thresholds)
                for page in extraction.pages:
                    page.ocr_status = OCR_COMPLETED
                    page.ocr_cache_path = str(destination)
                persist_extraction(database, extraction, thresholds)
                result.ocr_completed += 1
                database.audit("ocr_completed", phase=PHASE2,
                               target=row["abs_path"], outcome="ok",
                               detail={"cache": str(destination)})
            else:
                result.ocr_failed += 1
                database.execute(
                    "UPDATE pages SET ocr_status = ?, error_message = ? "
                    "WHERE file_id = ? AND ocr_status = ?",
                    (OCR_FAILED, message, row["file_id"], OCR_REQUIRED),
                )
                database.audit("ocr_failed", phase=PHASE2, target=row["abs_path"],
                               outcome="error", detail=message)
            if bar is not None:
                bar.update(1)
    finally:
        if bar is not None:
            bar.close()


def _record_phase2_stats(database: Database, result: Phase2Result, pilot: bool) -> None:
    """Record Phase 2 aggregate statistics."""
    conditions = {
        row["page_condition"]: row["n"]
        for row in database.query(
            "SELECT page_condition, COUNT(*) AS n FROM pages GROUP BY page_condition"
        )
    }
    subtypes = {
        (row["blank_subtype"] or "(none)"): row["n"]
        for row in database.query(
            "SELECT blank_subtype, COUNT(*) AS n FROM pages "
            "WHERE blank_subtype IS NOT NULL GROUP BY blank_subtype"
        )
    }
    stats = {
        "mode": "pilot" if pilot else "full",
        "documents_processed": result.documents,
        "pages_audited": result.pages,
        "extraction_failures": result.failures,
        "pages_needing_ocr": result.ocr_required,
        "documents_ocr_completed": result.ocr_completed,
        "documents_ocr_failed": result.ocr_failed,
        "page_condition_counts": conditions,
        "blank_subtype_counts": subtypes,
        "pages_with_observed_bates": database.scalar(
            "SELECT COUNT(*) FROM pages WHERE observed_bates IS NOT NULL"
        ),
        "documents_with_any_text": database.scalar(
            "SELECT COUNT(DISTINCT file_id) FROM pages WHERE char_count > 0"
        ),
    }
    database.set_stats(PHASE2, stats)
    database.audit("phase2_complete", phase=PHASE2, outcome="completed", detail=stats)


# ===========================================================================
# Phase 3 -- derived metadata
# ===========================================================================
@dataclass
class Phase3Result:
    """Aggregate counters returned by :func:`run_phase3`."""

    documents: int = 0
    tagged: int = 0
    manual_review: int = 0
    families: int = 0
    text_dup_groups: int = 0
    near_dup_groups: int = 0


def run_phase3(
    config: Config,
    database: Database,
    source: Path,
    *,
    file_ids: Optional[Sequence[int]] = None,
    force: bool = False,
    progress: bool = True,
) -> Phase3Result:
    """Derive review metadata for every extracted document.

    Metadata extraction reads the first ``extraction.head_pages`` pages and the
    last ``extraction.tail_pages`` pages first, expanding to the full document
    only when that sample yields nothing usable.

    Returns
    -------
    Phase3Result
        Counters only.
    """
    classifier = DocumentClassifier(config)
    email_parser = EmailParser(config)
    tagger = IssueTagger.from_config(config)
    scorer = PriorityScorer(config)
    parser = BatesParser.from_config(config)
    normalizer = TextNormalizer.from_config(config)

    head = int(config.get("extraction", "head_pages", default=3))
    tail = int(config.get("extraction", "tail_pages", default=1))
    dup_cfg = config.section("duplicates")

    targets = _phase3_targets(database, file_ids, force)
    result = Phase3Result()
    database.audit("phase3_start", phase=PHASE3, target=str(source),
                   outcome="started", detail={"documents": len(targets)})
    log.info("Phase 3 starting: %d document(s)", len(targets))
    if not targets:
        log.info("Nothing to do; all requested documents already have metadata")
        return result

    fingerprints = []
    bar = _progress_bar(len(targets), "Phase 3 metadata", progress)
    try:
        for row in targets:
            file_id = row["file_id"]
            pages = database.get_page_texts(file_id)
            sampled = _sample_pages(pages, head, tail)
            sample_text = "\n".join(text for _n, text in sampled)
            full_text = "\n".join(text for _n, text in pages)

            metadata = derive_metadata(
                sample_text if sample_text.strip() else full_text,
                config=config,
                classifier=classifier,
                email_parser=email_parser,
                page_count=row["page_count"],
            )
            if not sample_text.strip() and full_text.strip():
                metadata.processing_notes.append(
                    "head/tail sample was empty; full document text was used"
                )

            tag_summary = tagger.tag_pages(pages)
            database.replace_issue_hits(
                file_id, [hit.to_row() for hit in tag_summary.hits]
            )
            if tag_summary.tags:
                result.tagged += 1

            bates_range = _derive_bates(database, parser, row)
            condition = _document_condition(database, file_id)
            fingerprint = build_fingerprint(
                file_id, full_text, normalizer,
                bits=int(dup_cfg.get("simhash_bits", 64)),
                shingle_size=int(dup_cfg.get("simhash_shingle_size", 4)),
                document_type=metadata.document_type,
                subject=metadata.email_subject,
            )
            fingerprints.append(fingerprint)

            matched_terms = [
                term for terms in tag_summary.terms_by_tag.values() for term in terms
            ]
            priority = scorer.score(
                tags=tag_summary.tags,
                tag_hit_counts=tag_summary.hit_counts,
                matched_terms=matched_terms,
                participants=[metadata.email_from, metadata.email_to,
                              metadata.email_cc, metadata.author, metadata.title],
                document_date=metadata.document_date,
                is_duplicate=bool(row["exact_dup_group"]),
                manual_review_required=metadata.manual_review_required,
            )

            notes = list(metadata.processing_notes) + list(bates_range.notes)
            database.upsert_document(
                {
                    "file_id": file_id,
                    "begin_bates": bates_range.begin_str,
                    "end_bates": bates_range.end_str,
                    "begin_bates_num": bates_range.begin_num,
                    "end_bates_num": bates_range.end_num,
                    "bates_source": bates_range.source,
                    "bates_confidence": bates_range.confidence,
                    "page_count": row["page_count"],
                    "document_date": metadata.document_date,
                    "date_confidence": metadata.date_confidence,
                    "date_source": metadata.date_source,
                    "email_sent_date": metadata.email_sent_date,
                    "email_from": metadata.email_from,
                    "email_to": metadata.email_to,
                    "email_cc": metadata.email_cc,
                    "email_bcc": metadata.email_bcc,
                    "email_subject": metadata.email_subject,
                    "embedded_message_count": metadata.embedded_message_count,
                    "earliest_message_date": metadata.earliest_message_date,
                    "latest_message_date": metadata.latest_message_date,
                    "author": metadata.author,
                    "title": metadata.title,
                    "court_name": metadata.court_name,
                    "case_number": metadata.case_number,
                    "filing_date": metadata.filing_date,
                    "filing_party": metadata.filing_party,
                    "invoice_date": metadata.invoice_date,
                    "vendor": metadata.vendor,
                    "invoice_amount": metadata.invoice_amount,
                    "document_type": metadata.document_type,
                    "doc_type_confidence": metadata.doc_type_confidence,
                    "attachment_names": metadata.attachment_names,
                    "custodian": metadata.custodian,
                    "custodian_source": metadata.custodian_source,
                    "searchable_status": condition["searchable_status"],
                    "ocr_status": row["ocr_status"],
                    "apparent_blank_status": condition["apparent_blank_status"],
                    "exact_dup_group": row["exact_dup_group"],
                    "normalized_text_sha256": fingerprint.normalized_sha,
                    "simhash": f"{fingerprint.fingerprint:016x}",
                    "issue_tags": tag_summary.summary_string(),
                    "priority_score": priority.score,
                    "priority_explanation": priority.explanation(),
                    "extraction_confidence": metadata.extraction_confidence,
                    "manual_review_required": int(metadata.manual_review_required),
                    "processing_notes": "; ".join(notes) if notes else None,
                }
            )
            database.set_file_status(file_id, processing_status=STATUS_METADATA_DONE)

            result.documents += 1
            if metadata.manual_review_required:
                result.manual_review += 1
            if bar is not None:
                bar.update(1)
    finally:
        if bar is not None:
            bar.close()

    # Duplicate passes 2 and 3 need the whole corpus, so they run once at the end.
    log.info("Detecting normalised-text and near duplicates")
    text_groups = group_exact_text(
        fingerprints, min_chars=int(dup_cfg.get("min_chars", 200))
    )
    persist_groups(database, text_groups, KIND_TEXT)
    result.text_dup_groups = len(text_groups)

    exclude = exact_binary_pairs(database)
    near_groups = group_near_duplicates(
        fingerprints,
        bits=int(dup_cfg.get("simhash_bits", 64)),
        bands=int(dup_cfg.get("simhash_bands", 8)),
        max_distance=int(dup_cfg.get("near_duplicate_max_distance", 3)),
        confirm_similarity=float(dup_cfg.get("confirm_similarity", 88)),
        min_chars=int(dup_cfg.get("min_chars", 200)),
        max_pairs_per_bucket=int(dup_cfg.get("max_pairs_per_bucket", 5000)),
        exclude_pairs=exclude,
    )
    persist_groups(database, near_groups, KIND_NEAR)
    result.near_dup_groups = len(near_groups)
    _write_dup_columns(database)

    log.info("Inferring document families")
    relations = infer_families(load_candidates(database))
    persist_relations(database, relations)
    result.families = len(relations)

    _record_phase3_stats(database, result)
    log.info(
        "Phase 3 complete: %d document(s), %d tagged, %d flagged for manual "
        "review, %d family inference(s)",
        result.documents, result.tagged, result.manual_review, result.families,
    )
    return result


def _phase3_targets(
    database: Database, file_ids: Optional[Sequence[int]], force: bool
):
    """Resolve the documents Phase 3 should process."""
    clauses = ["f.is_pdf = 1", "f.processing_status IN ('pages_done', 'metadata_done')"]
    params: List[Any] = []
    if file_ids is not None:
        if not file_ids:
            return []
        clauses.append(f"f.file_id IN ({','.join('?' * len(file_ids))})")
        params.extend(file_ids)
    if not force:
        clauses.append("f.processing_status != 'metadata_done'")
    return database.query(
        f"SELECT f.* FROM files f WHERE {' AND '.join(clauses)} "
        "ORDER BY f.filename_bates_num, f.filename",
        params,
    )


def _sample_pages(
    pages: Sequence[Tuple[int, str]], head: int, tail: int
) -> List[Tuple[int, str]]:
    """Return the first ``head`` and last ``tail`` pages, de-duplicated."""
    if not pages:
        return []
    if len(pages) <= head + tail:
        return list(pages)
    selected = list(pages[:head])
    seen = {number for number, _text in selected}
    for entry in pages[-tail:] if tail else []:
        if entry[0] not in seen:
            selected.append(entry)
    return selected


def _derive_bates(database: Database, parser: BatesParser, row):
    """Build a document's Bates range from filename and observed page stamps."""
    page_rows = database.query(
        "SELECT observed_bates_num FROM pages WHERE file_id = ? ORDER BY page_number",
        (row["file_id"],),
    )
    observed = [
        parser.make(r["observed_bates_num"]) if r["observed_bates_num"] is not None
        else None
        for r in page_rows
    ]
    filename_bates = (
        parser.make(row["filename_bates_num"])
        if row["filename_bates_num"] is not None
        else None
    )
    return build_range(
        parser,
        filename_bates=filename_bates,
        observed=observed,
        page_count=row["page_count"],
    )


def _document_condition(database: Database, file_id: int) -> Dict[str, Any]:
    """Roll page conditions up to document level using database counts."""
    rows = database.query(
        "SELECT page_condition, COUNT(*) AS n FROM pages WHERE file_id = ? "
        "GROUP BY page_condition",
        (file_id,),
    )
    counts = {row["page_condition"]: row["n"] for row in rows}
    total = sum(counts.values())
    if not total:
        return {"searchable_status": "unknown", "apparent_blank_status": "unknown"}

    searchable = counts.get("searchable", 0)
    blank_like = counts.get(COND_APPARENT_BLANK, 0) + counts.get(COND_BATES_ONLY, 0)
    if searchable == total:
        searchable_status = "fully_searchable"
    elif searchable:
        searchable_status = "partially_searchable"
    elif counts.get(COND_IMAGE_ONLY, 0):
        searchable_status = "no_text_layer"
    else:
        searchable_status = "no_text_layer"

    if blank_like == total:
        blank_status = "all_pages_blank_or_bates_only"
    elif blank_like:
        blank_status = "some_pages_blank_or_bates_only"
    else:
        blank_status = "no_blank_pages_detected"
    return {
        "searchable_status": searchable_status,
        "apparent_blank_status": blank_status,
    }


def _write_dup_columns(database: Database) -> None:
    """Copy duplicate-group membership onto the ``documents`` rows."""
    text_map = group_lookup(database, KIND_TEXT)
    near_map = group_lookup(database, KIND_NEAR)
    with database.transaction() as conn:
        conn.execute("UPDATE documents SET text_dup_group = NULL, near_dup_group = NULL")
        for file_id, group_id in text_map.items():
            conn.execute(
                "UPDATE documents SET text_dup_group = ? WHERE file_id = ?",
                (group_id, file_id),
            )
        for file_id, group_id in near_map.items():
            conn.execute(
                "UPDATE documents SET near_dup_group = ? WHERE file_id = ?",
                (group_id, file_id),
            )


def _record_phase3_stats(database: Database, result: Phase3Result) -> None:
    """Record Phase 3 aggregate statistics."""
    types = {
        row["document_type"]: row["n"]
        for row in database.query(
            "SELECT document_type, COUNT(*) AS n FROM documents "
            "GROUP BY document_type ORDER BY n DESC"
        )
    }
    tags = {
        row["tag"]: row["n"]
        for row in database.query(
            "SELECT tag, COUNT(DISTINCT file_id) AS n FROM issue_hits "
            "GROUP BY tag ORDER BY n DESC"
        )
    }
    confidences = {
        row["bates_confidence"]: row["n"]
        for row in database.query(
            "SELECT bates_confidence, COUNT(*) AS n FROM documents "
            "GROUP BY bates_confidence"
        )
    }
    stats = {
        "documents_with_metadata": result.documents,
        "documents_with_issue_tags": result.tagged,
        "documents_flagged_manual_review": result.manual_review,
        "family_relationships_inferred": result.families,
        "normalized_text_duplicate_groups": result.text_dup_groups,
        "near_duplicate_groups": result.near_dup_groups,
        "document_type_counts": types,
        "documents_per_issue_tag": tags,
        "bates_confidence_counts": confidences,
        "median_priority_score": database.scalar(
            "SELECT AVG(priority_score) FROM documents", default=0
        ),
    }
    database.set_stats(PHASE3, stats)
    database.audit("phase3_complete", phase=PHASE3, outcome="completed", detail=stats)


# ---------------------------------------------------------------------------
def _progress_bar(total: int, description: str, enabled: bool):
    """Return a tqdm bar, or ``None``."""
    if not enabled:
        return None
    try:
        from tqdm import tqdm
    except ImportError:  # pragma: no cover - optional dependency
        return None
    return tqdm(total=total, desc=description, unit="doc", dynamic_ncols=True)
