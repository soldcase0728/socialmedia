"""SQLite processing-state database.

This database is the authoritative record of the run.  Reports are always
regenerated *from* it, never the other way round, which is what makes the
pipeline resumable: a phase can be interrupted at any point and restarted, and
completed work is skipped.

Tables
------
``files``
    One row per file discovered in the source folder (Phase 1).  Carries the
    processing/extraction/OCR state machine.
``pages``
    One row per PDF page (Phase 2): condition, character counts, image
    coverage, and any Bates stamp observed on the page.
``documents``
    One row per document (Phase 3): the derived review metadata.
``issue_hits``
    One row per issue-tag hit, with page number and a short locator.
``families``
    Inferred parent/child (email/attachment) relationships.
``duplicate_members``
    Membership of exact, normalised-text and near-duplicate groups.
``page_text`` / ``page_text_fts``
    Extracted text plus an FTS5 index for local searching.  Text lives here
    and *only* here -- it is never written into an Excel report.
``audit_log``
    Append-only record of every operation performed.
``run_stats``
    Key/value statistics per phase, used by the report tabs.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

from .logging_setup import get_logger
from .version import APP_VERSION, SCHEMA_VERSION

log = get_logger("database")

DB_FILENAME = "wilson_rode_index.sqlite"

# ---------------------------------------------------------------------------
# processing status vocabulary
# ---------------------------------------------------------------------------
STATUS_PENDING = "pending"
STATUS_INVENTORIED = "inventoried"
STATUS_PAGES_DONE = "pages_done"
STATUS_METADATA_DONE = "metadata_done"
STATUS_ERROR = "error"
STATUS_PLACEHOLDER = "cloud_placeholder"
STATUS_SKIPPED = "skipped"

EXTRACT_NOT_ATTEMPTED = "not_attempted"
EXTRACT_OK = "ok"
EXTRACT_PARTIAL = "partial"
EXTRACT_FAILED = "failed"
EXTRACT_ENCRYPTED = "encrypted"

OCR_NOT_REQUIRED = "not_required"
OCR_REQUIRED = "required"
OCR_COMPLETED = "completed"
OCR_FAILED = "failed"
OCR_SKIPPED = "skipped"

SCHEMA_STATEMENTS: Sequence[str] = (
    """
    CREATE TABLE IF NOT EXISTS meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS files (
        file_id             INTEGER PRIMARY KEY AUTOINCREMENT,
        abs_path            TEXT NOT NULL UNIQUE,
        rel_path            TEXT NOT NULL,
        filename            TEXT NOT NULL,
        extension           TEXT,
        file_size           INTEGER,
        created_ts          TEXT,
        modified_ts         TEXT,
        sha256              TEXT,
        page_count          INTEGER,
        is_pdf              INTEGER NOT NULL DEFAULT 0,
        is_encrypted        INTEGER NOT NULL DEFAULT 0,
        is_corrupt          INTEGER NOT NULL DEFAULT 0,
        is_placeholder      INTEGER NOT NULL DEFAULT 0,
        filename_bates      TEXT,
        filename_bates_num  INTEGER,
        filename_compliant  INTEGER NOT NULL DEFAULT 0,
        duplicate_filename  INTEGER NOT NULL DEFAULT 0,
        exact_dup_group     TEXT,
        processing_status   TEXT NOT NULL DEFAULT 'pending',
        extraction_status   TEXT NOT NULL DEFAULT 'not_attempted',
        ocr_status          TEXT NOT NULL DEFAULT 'not_required',
        last_processed_ts   TEXT,
        error_message       TEXT,
        app_version         TEXT,
        notes               TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_files_sha ON files(sha256)",
    "CREATE INDEX IF NOT EXISTS idx_files_status ON files(processing_status)",
    "CREATE INDEX IF NOT EXISTS idx_files_bates ON files(filename_bates_num)",
    "CREATE INDEX IF NOT EXISTS idx_files_name ON files(filename)",
    """
    CREATE TABLE IF NOT EXISTS pages (
        page_row_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id           INTEGER NOT NULL,
        page_number       INTEGER NOT NULL,
        char_count        INTEGER NOT NULL DEFAULT 0,
        word_count        INTEGER NOT NULL DEFAULT 0,
        has_text_layer    INTEGER NOT NULL DEFAULT 0,
        image_count       INTEGER NOT NULL DEFAULT 0,
        image_coverage    REAL NOT NULL DEFAULT 0.0,
        width             REAL,
        height            REAL,
        page_condition    TEXT NOT NULL DEFAULT 'uncertain',
        blank_subtype     TEXT,
        observed_bates    TEXT,
        observed_bates_num INTEGER,
        ocr_status        TEXT NOT NULL DEFAULT 'not_required',
        ocr_cache_path    TEXT,
        error_message     TEXT,
        app_version       TEXT,
        UNIQUE(file_id, page_number),
        FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pages_file ON pages(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_pages_cond ON pages(page_condition)",
    """
    CREATE TABLE IF NOT EXISTS page_text (
        file_id     INTEGER NOT NULL,
        page_number INTEGER NOT NULL,
        text        TEXT NOT NULL,
        PRIMARY KEY(file_id, page_number),
        FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS page_text_fts USING fts5(
        text,
        file_id UNINDEXED,
        page_number UNINDEXED,
        tokenize = 'unicode61'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        file_id                 INTEGER PRIMARY KEY,
        begin_bates             TEXT,
        end_bates               TEXT,
        begin_bates_num         INTEGER,
        end_bates_num           INTEGER,
        bates_source            TEXT,
        bates_confidence        TEXT,
        page_count              INTEGER,
        document_date           TEXT,
        date_confidence         TEXT,
        date_source             TEXT,
        email_sent_date         TEXT,
        email_from              TEXT,
        email_to                TEXT,
        email_cc                TEXT,
        email_bcc               TEXT,
        email_subject           TEXT,
        embedded_message_count  INTEGER,
        earliest_message_date   TEXT,
        latest_message_date     TEXT,
        author                  TEXT,
        title                   TEXT,
        court_name              TEXT,
        case_number             TEXT,
        filing_date             TEXT,
        filing_party            TEXT,
        invoice_date            TEXT,
        vendor                  TEXT,
        invoice_amount          TEXT,
        document_type           TEXT,
        doc_type_confidence     REAL,
        attachment_names        TEXT,
        parent_bates            TEXT,
        attachment_bates        TEXT,
        family_confidence       TEXT,
        custodian               TEXT,
        custodian_source        TEXT,
        searchable_status       TEXT,
        ocr_status              TEXT,
        apparent_blank_status   TEXT,
        exact_dup_group         TEXT,
        text_dup_group          TEXT,
        near_dup_group          TEXT,
        normalized_text_sha256  TEXT,
        simhash                 TEXT,
        issue_tags              TEXT,
        priority_score          REAL,
        priority_explanation    TEXT,
        extraction_confidence   TEXT,
        manual_review_required  INTEGER NOT NULL DEFAULT 0,
        processing_notes        TEXT,
        last_processed_ts       TEXT,
        app_version             TEXT,
        FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_docs_begin ON documents(begin_bates_num)",
    "CREATE INDEX IF NOT EXISTS idx_docs_type ON documents(document_type)",
    "CREATE INDEX IF NOT EXISTS idx_docs_priority ON documents(priority_score)",
    """
    CREATE TABLE IF NOT EXISTS issue_hits (
        hit_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id      INTEGER NOT NULL,
        tag          TEXT NOT NULL,
        term         TEXT NOT NULL,
        page_number  INTEGER,
        hit_count    INTEGER NOT NULL DEFAULT 1,
        locator      TEXT,
        FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hits_file ON issue_hits(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_hits_tag ON issue_hits(tag)",
    """
    CREATE TABLE IF NOT EXISTS families (
        family_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        parent_file_id  INTEGER,
        child_file_id   INTEGER,
        parent_bates    TEXT,
        child_bates     TEXT,
        relationship    TEXT NOT NULL,
        confidence      TEXT NOT NULL,
        reason          TEXT NOT NULL,
        app_version     TEXT,
        UNIQUE(parent_file_id, child_file_id, relationship)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_fam_parent ON families(parent_file_id)",
    "CREATE INDEX IF NOT EXISTS idx_fam_child ON families(child_file_id)",
    """
    CREATE TABLE IF NOT EXISTS duplicate_members (
        member_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id    TEXT NOT NULL,
        group_kind  TEXT NOT NULL,
        file_id     INTEGER NOT NULL,
        similarity  REAL,
        relation    TEXT,
        UNIQUE(group_id, group_kind, file_id),
        FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_dupm_file ON duplicate_members(file_id)",
    "CREATE INDEX IF NOT EXISTS idx_dupm_group ON duplicate_members(group_kind, group_id)",
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        audit_id    INTEGER PRIMARY KEY AUTOINCREMENT,
        ts          TEXT NOT NULL,
        phase       TEXT,
        operation   TEXT NOT NULL,
        target      TEXT,
        outcome     TEXT,
        detail      TEXT,
        app_version TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_phase ON audit_log(phase)",
    """
    CREATE TABLE IF NOT EXISTS run_stats (
        phase       TEXT NOT NULL,
        key         TEXT NOT NULL,
        value       TEXT,
        recorded_ts TEXT NOT NULL,
        PRIMARY KEY(phase, key)
    )
    """,
)


def utc_now() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class FileRecord:
    """A row from ``files`` in the form the pipeline passes around."""

    file_id: int
    abs_path: str
    rel_path: str
    filename: str
    file_size: int
    modified_ts: Optional[str]
    sha256: Optional[str]
    page_count: Optional[int]
    is_pdf: bool
    processing_status: str
    extraction_status: str
    ocr_status: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "FileRecord":
        """Build a record from a ``sqlite3.Row``."""
        return cls(
            file_id=row["file_id"],
            abs_path=row["abs_path"],
            rel_path=row["rel_path"],
            filename=row["filename"],
            file_size=row["file_size"] or 0,
            modified_ts=row["modified_ts"],
            sha256=row["sha256"],
            page_count=row["page_count"],
            is_pdf=bool(row["is_pdf"]),
            processing_status=row["processing_status"],
            extraction_status=row["extraction_status"],
            ocr_status=row["ocr_status"],
        )


class Database:
    """Thin, thread-safe wrapper around the processing-state SQLite database.

    The wrapper deliberately exposes SQL-shaped helpers rather than an ORM:
    the queries are the specification, and keeping them visible makes the
    derived-metadata provenance auditable.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), timeout=60.0,
                                     check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._configure()
        self._create_schema()

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def _configure(self) -> None:
        """Apply pragmas suited to a long, resumable, single-host run."""
        cur = self._conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA busy_timeout=60000")
        cur.close()

    def _create_schema(self) -> None:
        """Create tables and verify the schema version."""
        with self._lock, self._conn:
            for statement in SCHEMA_STATEMENTS:
                self._conn.execute(statement)
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
                self._conn.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES('created_ts', ?)",
                    (utc_now(),),
                )
            elif int(row["value"]) != SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database {self.path} uses schema version {row['value']}, "
                    f"but this build expects {SCHEMA_VERSION}.  Start a new "
                    "derived-index folder rather than mixing schema versions."
                )
            self._conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('app_version', ?)",
                (APP_VERSION,),
            )

    def close(self) -> None:
        """Flush and close the connection."""
        with self._lock:
            try:
                self._conn.commit()
            finally:
                self._conn.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Context manager yielding the connection inside a transaction."""
        with self._lock:
            with self._conn:
                yield self._conn

    # ------------------------------------------------------------------
    # generic query helpers
    # ------------------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Execute a statement and return the cursor."""
        with self._lock:
            return self._conn.execute(sql, params)

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        """Execute a statement for many parameter sets inside one transaction."""
        with self._lock, self._conn:
            self._conn.executemany(sql, rows)

    def query(self, sql: str, params: Sequence[Any] = ()) -> List[sqlite3.Row]:
        """Run a SELECT and return all rows."""
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[sqlite3.Row]:
        """Run a SELECT and return the first row, or ``None``."""
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def iter_query(
        self, sql: str, params: Sequence[Any] = (), batch: int = 500
    ) -> Iterator[sqlite3.Row]:
        """Stream rows without materialising the whole result set."""
        with self._lock:
            cursor = self._conn.execute(sql, params)
        try:
            while True:
                with self._lock:
                    rows = cursor.fetchmany(batch)
                if not rows:
                    return
                for row in rows:
                    yield row
        finally:
            cursor.close()

    def scalar(self, sql: str, params: Sequence[Any] = (), default: Any = 0) -> Any:
        """Run a SELECT returning a single value."""
        row = self.query_one(sql, params)
        if row is None or row[0] is None:
            return default
        return row[0]

    # ------------------------------------------------------------------
    # files
    # ------------------------------------------------------------------
    def upsert_file(self, record: Dict[str, Any]) -> int:
        """Insert or update a ``files`` row keyed on ``abs_path``.

        Returns
        -------
        int
            The ``file_id`` of the inserted or updated row.
        """
        record = dict(record)
        record.setdefault("app_version", APP_VERSION)
        columns = list(record.keys())
        placeholders = ", ".join("?" for _ in columns)
        assignments = ", ".join(f"{c}=excluded.{c}" for c in columns if c != "abs_path")
        sql = (
            f"INSERT INTO files ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(abs_path) DO UPDATE SET {assignments}"
        )
        with self._lock, self._conn:
            self._conn.execute(sql, [record[c] for c in columns])
            row = self._conn.execute(
                "SELECT file_id FROM files WHERE abs_path = ?", (record["abs_path"],)
            ).fetchone()
        return int(row["file_id"])

    def get_file_by_path(self, abs_path: str) -> Optional[sqlite3.Row]:
        """Return the ``files`` row for an absolute path."""
        return self.query_one("SELECT * FROM files WHERE abs_path = ?", (abs_path,))

    def needs_processing(
        self, abs_path: str, file_size: int, modified_ts: str
    ) -> bool:
        """Decide whether a file must be (re)processed.

        A file is skipped only when it is already recorded as successfully
        inventoried *and* its size and modification timestamp are unchanged.
        Any change to either attribute invalidates the cached work.
        """
        row = self.get_file_by_path(abs_path)
        if row is None:
            return True
        if row["processing_status"] in (STATUS_PENDING, STATUS_ERROR,
                                        STATUS_PLACEHOLDER):
            return True
        if (row["file_size"] or -1) != file_size:
            return True
        if (row["modified_ts"] or "") != modified_ts:
            return True
        if not row["sha256"]:
            return True
        return False

    def set_file_status(
        self,
        file_id: int,
        *,
        processing_status: Optional[str] = None,
        extraction_status: Optional[str] = None,
        ocr_status: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update the state machine columns for one file."""
        fields: List[str] = ["last_processed_ts = ?", "app_version = ?"]
        params: List[Any] = [utc_now(), APP_VERSION]
        for column, value in (
            ("processing_status", processing_status),
            ("extraction_status", extraction_status),
            ("ocr_status", ocr_status),
            ("error_message", error_message),
        ):
            if value is not None:
                fields.append(f"{column} = ?")
                params.append(value)
        params.append(file_id)
        with self._lock, self._conn:
            self._conn.execute(
                f"UPDATE files SET {', '.join(fields)} WHERE file_id = ?", params
            )

    def iter_files(
        self,
        *,
        pdf_only: bool = False,
        statuses: Optional[Sequence[str]] = None,
        file_ids: Optional[Sequence[int]] = None,
    ) -> Iterator[sqlite3.Row]:
        """Stream ``files`` rows matching simple filters."""
        clauses: List[str] = []
        params: List[Any] = []
        if pdf_only:
            clauses.append("is_pdf = 1")
        if statuses:
            clauses.append(f"processing_status IN ({','.join('?' * len(statuses))})")
            params.extend(statuses)
        if file_ids:
            clauses.append(f"file_id IN ({','.join('?' * len(file_ids))})")
            params.extend(file_ids)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        yield from self.iter_query(
            f"SELECT * FROM files {where} ORDER BY filename_bates_num, filename",
            params,
        )

    # ------------------------------------------------------------------
    # pages and text
    # ------------------------------------------------------------------
    def replace_pages(self, file_id: int, pages: Sequence[Dict[str, Any]]) -> None:
        """Replace all ``pages`` rows for a file (idempotent re-processing)."""
        if not pages:
            return
        columns = [
            "file_id", "page_number", "char_count", "word_count", "has_text_layer",
            "image_count", "image_coverage", "width", "height", "page_condition",
            "blank_subtype", "observed_bates", "observed_bates_num", "ocr_status",
            "ocr_cache_path", "error_message", "app_version",
        ]
        rows = [
            tuple(page.get(column, None) if column != "app_version" else APP_VERSION
                  for column in columns)
            for page in pages
        ]
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM pages WHERE file_id = ?", (file_id,))
            self._conn.executemany(
                f"INSERT INTO pages ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' * len(columns))})",
                rows,
            )

    def store_page_text(
        self, file_id: int, texts: Sequence[tuple], max_chars: int = 200_000
    ) -> None:
        """Persist page text and refresh the FTS index for one file.

        Parameters
        ----------
        texts:
            Sequence of ``(page_number, text)`` pairs.
        max_chars:
            Per-page truncation limit, keeping the index bounded.
        """
        payload = [
            (file_id, int(number), (text or "")[:max_chars]) for number, text in texts
        ]
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM page_text WHERE file_id = ?", (file_id,))
            self._conn.execute(
                "DELETE FROM page_text_fts WHERE file_id = ?", (file_id,)
            )
            if payload:
                self._conn.executemany(
                    "INSERT INTO page_text(file_id, page_number, text) "
                    "VALUES (?, ?, ?)",
                    payload,
                )
                self._conn.executemany(
                    "INSERT INTO page_text_fts(text, file_id, page_number) "
                    "VALUES (?, ?, ?)",
                    [(text, fid, num) for fid, num, text in payload],
                )

    def get_page_texts(self, file_id: int) -> List[tuple]:
        """Return ``(page_number, text)`` pairs for a file, ordered by page."""
        rows = self.query(
            "SELECT page_number, text FROM page_text WHERE file_id = ? "
            "ORDER BY page_number",
            (file_id,),
        )
        return [(row["page_number"], row["text"]) for row in rows]

    def search_text(self, expression: str, limit: int = 50) -> List[sqlite3.Row]:
        """Run an FTS5 query.  Returns file/page identifiers, never text."""
        return self.query(
            "SELECT f.file_id, f.filename, f.rel_path, t.page_number "
            "FROM page_text_fts t JOIN files f ON f.file_id = t.file_id "
            "WHERE page_text_fts MATCH ? ORDER BY rank LIMIT ?",
            (expression, limit),
        )

    # ------------------------------------------------------------------
    # documents
    # ------------------------------------------------------------------
    def upsert_document(self, record: Dict[str, Any]) -> None:
        """Insert or update a ``documents`` row keyed on ``file_id``."""
        record = dict(record)
        record["app_version"] = APP_VERSION
        record["last_processed_ts"] = utc_now()
        columns = list(record.keys())
        placeholders = ", ".join("?" for _ in columns)
        assignments = ", ".join(f"{c}=excluded.{c}" for c in columns if c != "file_id")
        with self._lock, self._conn:
            self._conn.execute(
                f"INSERT INTO documents ({', '.join(columns)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT(file_id) DO UPDATE SET {assignments}",
                [record[c] for c in columns],
            )

    # ------------------------------------------------------------------
    # issue hits, families, duplicates
    # ------------------------------------------------------------------
    def replace_issue_hits(self, file_id: int, hits: Sequence[Dict[str, Any]]) -> None:
        """Replace all issue-tag hits for a file."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM issue_hits WHERE file_id = ?", (file_id,))
            if hits:
                self._conn.executemany(
                    "INSERT INTO issue_hits(file_id, tag, term, page_number, "
                    "hit_count, locator) VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (
                            file_id,
                            hit["tag"],
                            hit["term"],
                            hit.get("page_number"),
                            hit.get("hit_count", 1),
                            hit.get("locator"),
                        )
                        for hit in hits
                    ],
                )

    def add_family(self, relation: Dict[str, Any]) -> None:
        """Record one inferred family relationship (idempotent)."""
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO families(parent_file_id, child_file_id, "
                "parent_bates, child_bates, relationship, confidence, reason, "
                "app_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    relation.get("parent_file_id"),
                    relation.get("child_file_id"),
                    relation.get("parent_bates"),
                    relation.get("child_bates"),
                    relation["relationship"],
                    relation["confidence"],
                    relation["reason"],
                    APP_VERSION,
                ),
            )

    def clear_duplicate_groups(self, kind: str) -> None:
        """Remove all membership rows for one duplicate-group kind."""
        with self._lock, self._conn:
            self._conn.execute(
                "DELETE FROM duplicate_members WHERE group_kind = ?", (kind,)
            )

    def add_duplicate_members(
        self, kind: str, members: Sequence[Dict[str, Any]]
    ) -> None:
        """Bulk-insert duplicate-group membership rows."""
        if not members:
            return
        with self._lock, self._conn:
            self._conn.executemany(
                "INSERT OR REPLACE INTO duplicate_members(group_id, group_kind, "
                "file_id, similarity, relation) VALUES (?, ?, ?, ?, ?)",
                [
                    (
                        member["group_id"],
                        kind,
                        member["file_id"],
                        member.get("similarity"),
                        member.get("relation"),
                    )
                    for member in members
                ],
            )

    # ------------------------------------------------------------------
    # audit and statistics
    # ------------------------------------------------------------------
    def audit(
        self,
        operation: str,
        *,
        phase: Optional[str] = None,
        target: Optional[str] = None,
        outcome: Optional[str] = None,
        detail: Optional[Any] = None,
    ) -> None:
        """Append an entry to the audit log.

        ``detail`` may be any JSON-serialisable object.  It must never contain
        document text; callers pass counts, paths and reasons only.
        """
        if detail is not None and not isinstance(detail, str):
            detail = json.dumps(detail, default=str, sort_keys=True)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO audit_log(ts, phase, operation, target, outcome, "
                "detail, app_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (utc_now(), phase, operation, target, outcome, detail, APP_VERSION),
            )

    def set_stat(self, phase: str, key: str, value: Any) -> None:
        """Record one run statistic."""
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO run_stats(phase, key, value, recorded_ts) "
                "VALUES (?, ?, ?, ?)",
                (phase, key, json.dumps(value, default=str), utc_now()),
            )

    def set_stats(self, phase: str, stats: Dict[str, Any]) -> None:
        """Record many run statistics at once."""
        for key, value in stats.items():
            self.set_stat(phase, key, value)

    def get_stats(self, phase: Optional[str] = None) -> Dict[str, Any]:
        """Return recorded statistics, optionally filtered by phase."""
        if phase:
            rows = self.query(
                "SELECT key, value FROM run_stats WHERE phase = ? ORDER BY key",
                (phase,),
            )
            return {row["key"]: json.loads(row["value"]) for row in rows}
        rows = self.query("SELECT phase, key, value FROM run_stats ORDER BY phase, key")
        out: Dict[str, Any] = {}
        for row in rows:
            out.setdefault(row["phase"], {})[row["key"]] = json.loads(row["value"])
        return out


def open_database(output_folder: Path) -> Database:
    """Open (creating if needed) the processing database in the output folder."""
    return Database(Path(output_folder) / DB_FILENAME)
