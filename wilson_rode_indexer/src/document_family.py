"""Document-family inference: possible parent emails and their attachments.

Nothing here is native metadata.  This production has no load file, so there
is no authoritative family table; every relationship below is *inferred* from
observable signals and is reported with the reason it was inferred and how
confident the inference is.

Signals used
------------
* consecutive Bates ranges (an attachment normally follows its email)
* the parent email's own ``Attachments:`` header
* filenames referenced in the email body
* matching dates
* matching subjects
* explicit separator / placeholder pages

Confidence
----------
``confirmed``
    The parent's attachment list names the child and the Bates ranges are
    consecutive.  This is the strongest signal available without a load file
    and still remains an inference.
``probable``
    Two independent signals agree.
``possible``
    A single signal fired.
``unknown``
    Recorded only when a relationship is asserted with no supporting signal,
    which this module never does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .database import Database
from .logging_setup import get_logger

log = get_logger("family")

REL_ATTACHMENT = "possible_attachment_of"
REL_PARENT = "possible_parent_email_of"
REL_SAME_FAMILY = "possible_same_family"

CONF_CONFIRMED = "confirmed"
CONF_PROBABLE = "probable"
CONF_POSSIBLE = "possible"
CONF_UNKNOWN = "unknown"

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SUBJECT_PREFIX_RE = re.compile(r"^\s*(?:re|fw|fwd|aw|tr)\s*:\s*", re.IGNORECASE)


@dataclass
class FamilyCandidate:
    """A document in Bates order, with the fields family inference needs."""

    file_id: int
    filename: str
    begin_bates: Optional[int]
    end_bates: Optional[int]
    document_type: Optional[str]
    document_date: Optional[str]
    subject: Optional[str]
    attachment_names: List[str] = field(default_factory=list)
    page_count: Optional[int] = None
    begin_bates_str: Optional[str] = None
    end_bates_str: Optional[str] = None

    @property
    def is_email(self) -> bool:
        """Whether this document was classified as an email or email chain."""
        return (self.document_type or "") in ("email", "email_chain")


@dataclass
class FamilyRelation:
    """One inferred parent/child relationship."""

    parent_file_id: int
    child_file_id: int
    parent_bates: Optional[str]
    child_bates: Optional[str]
    relationship: str
    confidence: str
    reason: str

    def to_row(self) -> Dict[str, object]:
        """Convert to the dictionary shape :mod:`src.database` expects."""
        return {
            "parent_file_id": self.parent_file_id,
            "child_file_id": self.child_file_id,
            "parent_bates": self.parent_bates,
            "child_bates": self.child_bates,
            "relationship": self.relationship,
            "confidence": self.confidence,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def normalize_filename(name: str) -> str:
    """Reduce a filename to a comparable key (lowercase, alphanumerics only)."""
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return _NON_ALNUM_RE.sub("", stem.lower())


def normalize_subject(subject: Optional[str]) -> Optional[str]:
    """Strip ``Re:``/``Fwd:`` prefixes and normalise whitespace."""
    if not subject:
        return None
    cleaned = subject
    for _ in range(5):
        stripped = _SUBJECT_PREFIX_RE.sub("", cleaned)
        if stripped == cleaned:
            break
        cleaned = stripped
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned or None


def _dates_match(left: Optional[str], right: Optional[str]) -> bool:
    """Whether two ISO date strings refer to the same day."""
    return bool(left and right and left[:10] == right[:10])


# ---------------------------------------------------------------------------
# inference
# ---------------------------------------------------------------------------
def infer_families(
    candidates: Sequence[FamilyCandidate],
    *,
    max_children_per_email: int = 25,
    max_bates_gap: int = 1,
) -> List[FamilyRelation]:
    """Infer parent/child relationships across a Bates-ordered production.

    The scan is linear in Bates order: for each email, the documents that
    immediately follow it are considered as possible attachments until a
    signal says the family has ended (another email begins, or the Bates
    numbers stop being consecutive).  No pairwise comparison across the whole
    production is performed.

    Parameters
    ----------
    candidates:
        Documents to consider.  Only those with a numeric begin Bates take
        part in Bates-adjacency reasoning.
    max_children_per_email:
        Safety cap on how many following documents one email may claim.
    max_bates_gap:
        Allowed gap between a parent's end Bates and a child's begin Bates.
        ``1`` means strictly consecutive.

    Returns
    -------
    list of FamilyRelation
        Every relationship carries the reason it was inferred.  Nothing is
        presented as native metadata.
    """
    ordered = sorted(
        [c for c in candidates if c.begin_bates is not None],
        key=lambda c: (c.begin_bates, c.end_bates or c.begin_bates),
    )
    relations: List[FamilyRelation] = []
    if not ordered:
        return relations

    attachment_index: Dict[str, List[FamilyCandidate]] = {}
    for candidate in ordered:
        attachment_index.setdefault(normalize_filename(candidate.filename), []).append(
            candidate
        )

    for index, parent in enumerate(ordered):
        if not parent.is_email:
            continue

        parent_attachment_keys = {
            normalize_filename(name) for name in parent.attachment_names if name
        }
        parent_subject = normalize_subject(parent.subject)
        cursor = parent.end_bates or parent.begin_bates
        claimed = 0

        for child in ordered[index + 1 : index + 1 + max_children_per_email]:
            if child.begin_bates is None or cursor is None:
                break
            gap = child.begin_bates - cursor
            consecutive = 0 < gap <= max_bates_gap

            named_by_parent = bool(parent_attachment_keys) and (
                normalize_filename(child.filename) in parent_attachment_keys
                or (child.subject
                    and normalize_filename(child.subject) in parent_attachment_keys)
            )
            # Bates adjacency is a necessary condition. Matching dates or
            # subjects alone are far too weak: an entire day's production
            # would otherwise collapse into one family. The single exception
            # is a child the parent's own attachment list names.
            if not consecutive and not named_by_parent:
                break

            signals: List[str] = []
            if consecutive:
                signals.append(
                    f"child begins at {child.begin_bates_str or child.begin_bates}, "
                    f"immediately after the email's end Bates "
                    f"{parent.end_bates_str or cursor}"
                )
            if parent_attachment_keys and normalize_filename(child.filename) in (
                parent_attachment_keys
            ):
                signals.append(
                    "the email's Attachments header names a file matching the "
                    "child's filename"
                )
            if parent_attachment_keys and child.subject and normalize_filename(
                child.subject
            ) in parent_attachment_keys:
                signals.append(
                    "the email's Attachments header names a file matching the "
                    "child's derived title"
                )
            if _dates_match(parent.document_date, child.document_date):
                signals.append("parent and child carry the same apparent date")
            child_subject = normalize_subject(child.subject)
            if parent_subject and child_subject and parent_subject == child_subject:
                signals.append("parent and child share the same normalised subject")

            if child.is_email and not consecutive:
                break
            if child.is_email and consecutive and not parent_attachment_keys:
                # A consecutive email is far more likely the next document in
                # the production than an attachment of this one.
                break
            if not signals:
                break

            confidence = _confidence_for(signals, consecutive, parent_attachment_keys,
                                         child)
            relations.append(
                FamilyRelation(
                    parent_file_id=parent.file_id,
                    child_file_id=child.file_id,
                    parent_bates=parent.begin_bates_str,
                    child_bates=child.begin_bates_str,
                    relationship=REL_ATTACHMENT,
                    confidence=confidence,
                    reason="INFERRED (not native metadata): " + "; ".join(signals),
                )
            )
            claimed += 1
            cursor = child.end_bates or child.begin_bates
            if claimed >= max_children_per_email:
                break

    log.info("Inferred %d possible family relationship(s)", len(relations))
    return relations


def _confidence_for(
    signals: Sequence[str],
    consecutive: bool,
    parent_attachment_keys: Iterable[str],
    child: FamilyCandidate,
) -> str:
    """Grade a relationship from the signals that supported it."""
    named = any("Attachments header" in signal for signal in signals)
    if named and consecutive:
        return CONF_CONFIRMED
    if len(signals) >= 2:
        return CONF_PROBABLE
    if signals:
        return CONF_POSSIBLE
    return CONF_UNKNOWN


# ---------------------------------------------------------------------------
# database glue
# ---------------------------------------------------------------------------
def load_candidates(database: Database) -> List[FamilyCandidate]:
    """Load Phase 3 documents in the shape family inference needs."""
    rows = database.query(
        """
        SELECT d.file_id, f.filename, d.begin_bates_num, d.end_bates_num,
               d.begin_bates, d.end_bates, d.document_type, d.document_date,
               d.email_subject, d.title, d.attachment_names, d.page_count
        FROM documents d JOIN files f ON f.file_id = d.file_id
        ORDER BY d.begin_bates_num, f.filename
        """
    )
    candidates: List[FamilyCandidate] = []
    for row in rows:
        names = [
            part.strip()
            for part in (row["attachment_names"] or "").split(";")
            if part.strip()
        ]
        candidates.append(
            FamilyCandidate(
                file_id=row["file_id"],
                filename=row["filename"],
                begin_bates=row["begin_bates_num"],
                end_bates=row["end_bates_num"],
                begin_bates_str=row["begin_bates"],
                end_bates_str=row["end_bates"],
                document_type=row["document_type"],
                document_date=row["document_date"],
                subject=row["email_subject"] or row["title"],
                attachment_names=names,
                page_count=row["page_count"],
            )
        )
    return candidates


def persist_relations(database: Database, relations: Sequence[FamilyRelation]) -> None:
    """Write inferred relationships and back-fill the document family columns."""
    database.execute("DELETE FROM families")
    for relation in relations:
        database.add_family(relation.to_row())

    parents: Dict[int, str] = {}
    children: Dict[int, List[str]] = {}
    confidences: Dict[int, str] = {}
    for relation in relations:
        if relation.parent_bates:
            parents[relation.child_file_id] = relation.parent_bates
        confidences[relation.child_file_id] = relation.confidence
        if relation.child_bates:
            children.setdefault(relation.parent_file_id, []).append(relation.child_bates)

    with database.transaction() as conn:
        for file_id, parent_bates in parents.items():
            conn.execute(
                "UPDATE documents SET parent_bates = ?, family_confidence = ? "
                "WHERE file_id = ?",
                (parent_bates, confidences.get(file_id, CONF_POSSIBLE), file_id),
            )
        for file_id, child_bates in children.items():
            conn.execute(
                "UPDATE documents SET attachment_bates = ? WHERE file_id = ?",
                ("; ".join(child_bates), file_id),
            )
    log.info("Persisted %d family relationship(s)", len(relations))
