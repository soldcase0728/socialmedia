"""Duplicate and near-duplicate detection.

Three independent passes, none of which performs an O(n^2) comparison across
the production:

1. **Exact binary** -- grouping by SHA-256.  Bucketed by hash, so linear.
2. **Exact normalised text** -- grouping by SHA-256 of normalised text.  Also
   linear.  Catches the same document re-rendered by a different PDF writer.
3. **Near duplicate** -- 64-bit SimHash fingerprints indexed with LSH banding.
   Only documents sharing a band signature are ever compared, and each
   candidate pair is confirmed with a token-set similarity check.

The relationship vocabulary distinguishes the reasons two documents look
alike, because "duplicate" means different things to a reviewer.
"""

from __future__ import annotations

import hashlib
import itertools
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .config import Config
from .database import Database
from .logging_setup import get_logger

log = get_logger("duplicates")

KIND_EXACT_BINARY = "exact_binary"
KIND_TEXT = "normalized_text"
KIND_NEAR = "near_duplicate"

REL_EXACT_BINARY = "exact_binary_duplicate"
REL_SAME_TEXT_DIFFERENT_RENDERING = "same_text_different_pdf_rendering"
REL_CHAIN_CONTAINS_EARLIER = "email_chain_contains_earlier_email"
REL_DRAFT_AND_FINAL = "draft_and_final"
REL_NEAR_DUPLICATE = "near_duplicate"
REL_POSSIBLE_DUPLICATE = "possible_duplicate"

_WHITESPACE_RE = re.compile(r"\s+")
_NON_WORD_RE = re.compile(r"[^\w\s]")


# ---------------------------------------------------------------------------
# normalisation
# ---------------------------------------------------------------------------
class TextNormalizer:
    """Normalises document text so incidental differences stop mattering.

    Bates stamps, page-number footers and confidentiality legends differ
    between two copies of the same document.  Stripping them before hashing is
    what lets pass 2 recognise "same text, different rendering".
    """

    def __init__(self, strip_patterns: Sequence[str] = ()) -> None:
        self.strip_res = [re.compile(pattern, re.IGNORECASE) for pattern in strip_patterns]

    @classmethod
    def from_config(cls, config: Config) -> "TextNormalizer":
        """Build a normaliser from configuration."""
        return cls(config.get("duplicates", "normalize_strip_patterns", default=[]) or [])

    def normalize(self, text: str) -> str:
        """Return the canonical form of ``text`` used for hashing."""
        if not text:
            return ""
        cleaned = text
        for pattern in self.strip_res:
            cleaned = pattern.sub(" ", cleaned)
        cleaned = cleaned.lower()
        cleaned = _NON_WORD_RE.sub(" ", cleaned)
        return _WHITESPACE_RE.sub(" ", cleaned).strip()

    def digest(self, text: str) -> Optional[str]:
        """SHA-256 of the normalised text, or ``None`` when empty."""
        normalized = self.normalize(text)
        if not normalized:
            return None
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# SimHash
# ---------------------------------------------------------------------------
def shingles(tokens: Sequence[str], size: int = 4) -> List[str]:
    """Return overlapping ``size``-token shingles."""
    if size <= 1 or len(tokens) < size:
        return list(tokens)
    return [" ".join(tokens[i:i + size]) for i in range(len(tokens) - size + 1)]


def simhash(text: str, *, bits: int = 64, shingle_size: int = 4) -> int:
    """Compute a SimHash fingerprint of ``text``.

    Two documents differing only in a few words produce fingerprints within a
    small Hamming distance of each other, which is what makes near-duplicate
    detection tractable without pairwise comparison.
    """
    tokens = text.split()
    if not tokens:
        return 0
    vector = [0] * bits
    for shingle in shingles(tokens, shingle_size):
        digest = hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for position in range(bits):
            vector[position] += 1 if (value >> position) & 1 else -1
    fingerprint = 0
    for position in range(bits):
        if vector[position] > 0:
            fingerprint |= 1 << position
    return fingerprint


def hamming_distance(left: int, right: int) -> int:
    """Number of differing bits between two fingerprints."""
    return bin(left ^ right).count("1")


def band_keys(fingerprint: int, *, bits: int = 64, bands: int = 8) -> List[str]:
    """Split a fingerprint into LSH band signatures.

    Two fingerprints within a small Hamming distance share at least one band
    with high probability, so bucketing by band gives a cheap candidate set.
    """
    width = bits // bands
    mask = (1 << width) - 1
    return [
        f"{index}:{(fingerprint >> (index * width)) & mask:0{(width + 3) // 4}x}"
        for index in range(bands)
    ]


# ---------------------------------------------------------------------------
# grouping
# ---------------------------------------------------------------------------
@dataclass
class DuplicateGroup:
    """A set of documents considered duplicates of one another."""

    group_id: str
    kind: str
    file_ids: List[int] = field(default_factory=list)
    relation: str = REL_POSSIBLE_DUPLICATE
    similarity: Optional[float] = None


@dataclass
class DocumentFingerprint:
    """Everything duplicate detection needs to know about one document."""

    file_id: int
    normalized_text: str
    normalized_sha: Optional[str]
    fingerprint: int
    token_count: int
    document_type: Optional[str] = None
    subject: Optional[str] = None


def build_fingerprint(
    file_id: int,
    text: str,
    normalizer: TextNormalizer,
    *,
    bits: int = 64,
    shingle_size: int = 4,
    document_type: Optional[str] = None,
    subject: Optional[str] = None,
) -> DocumentFingerprint:
    """Normalise and fingerprint one document's text."""
    normalized = normalizer.normalize(text)
    return DocumentFingerprint(
        file_id=file_id,
        normalized_text=normalized,
        normalized_sha=(
            hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else None
        ),
        fingerprint=simhash(normalized, bits=bits, shingle_size=shingle_size),
        token_count=len(normalized.split()),
        document_type=document_type,
        subject=subject,
    )


def group_exact_text(
    fingerprints: Sequence[DocumentFingerprint], *, min_chars: int = 200
) -> List[DuplicateGroup]:
    """Group documents whose normalised text hashes are identical."""
    buckets: Dict[str, List[int]] = defaultdict(list)
    for item in fingerprints:
        if item.normalized_sha and len(item.normalized_text) >= min_chars:
            buckets[item.normalized_sha].append(item.file_id)

    groups: List[DuplicateGroup] = []
    for digest, members in buckets.items():
        if len(members) > 1:
            groups.append(
                DuplicateGroup(
                    group_id=f"TXT-{digest[:12]}",
                    kind=KIND_TEXT,
                    file_ids=sorted(members),
                    relation=REL_SAME_TEXT_DIFFERENT_RENDERING,
                    similarity=100.0,
                )
            )
    return groups


def group_near_duplicates(
    fingerprints: Sequence[DocumentFingerprint],
    *,
    bits: int = 64,
    bands: int = 8,
    max_distance: int = 3,
    confirm_similarity: float = 88.0,
    min_chars: int = 200,
    max_pairs_per_bucket: int = 5000,
    exclude_pairs: Optional[Set[Tuple[int, int]]] = None,
) -> List[DuplicateGroup]:
    """Group near-duplicate documents using SimHash + LSH banding.

    Only documents sharing an LSH band are compared, and each bucket is capped,
    so the work stays roughly linear in the number of documents even when the
    production contains large families of similar exhibits.

    Parameters
    ----------
    exclude_pairs:
        Pairs already accounted for by an earlier pass (exact binary or exact
        text), so they are not re-reported as near duplicates.

    Returns
    -------
    list of DuplicateGroup
        Connected components of the confirmed-similarity graph, each labelled
        with the reason the members resemble each other.
    """
    eligible = [
        item for item in fingerprints
        if len(item.normalized_text) >= min_chars and item.fingerprint
    ]
    if len(eligible) < 2:
        return []

    by_id = {item.file_id: item for item in eligible}
    buckets: Dict[str, List[int]] = defaultdict(list)
    for item in eligible:
        for key in band_keys(item.fingerprint, bits=bits, bands=bands):
            buckets[key].append(item.file_id)

    excluded = exclude_pairs or set()
    candidate_pairs: Set[Tuple[int, int]] = set()
    truncated_buckets = 0
    for members in buckets.values():
        if len(members) < 2:
            continue
        unique = sorted(set(members))
        pair_count = len(unique) * (len(unique) - 1) // 2
        if pair_count > max_pairs_per_bucket:
            truncated_buckets += 1
            unique = unique[: _max_members_for(max_pairs_per_bucket)]
        for left, right in itertools.combinations(unique, 2):
            pair = (left, right)
            if pair not in excluded:
                candidate_pairs.add(pair)

    if truncated_buckets:
        log.warning(
            "%d LSH bucket(s) exceeded the configured pair cap and were "
            "truncated; some near-duplicate pairs may not be reported",
            truncated_buckets,
        )

    confirmed: List[Tuple[int, int, float, str]] = []
    for left, right in candidate_pairs:
        a, b = by_id[left], by_id[right]
        if hamming_distance(a.fingerprint, b.fingerprint) > max_distance:
            continue
        score = _similarity(a.normalized_text, b.normalized_text)
        if score >= confirm_similarity:
            confirmed.append((left, right, score, _relation_for(a, b, score)))

    return _components_to_groups(confirmed, KIND_NEAR)


def _max_members_for(max_pairs: int) -> int:
    """Largest bucket size whose pair count stays within ``max_pairs``."""
    size = 2
    while size * (size - 1) // 2 <= max_pairs:
        size += 1
    return max(2, size - 1)


def _similarity(left: str, right: str) -> float:
    """Token-set similarity in ``[0, 100]``.

    Uses :mod:`rapidfuzz` when available and falls back to a Jaccard index so
    the module still works in a minimal environment.
    """
    try:
        from rapidfuzz import fuzz

        return float(fuzz.token_set_ratio(left[:20000], right[:20000]))
    except ImportError:  # pragma: no cover - optional dependency
        left_tokens, right_tokens = set(left.split()), set(right.split())
        if not left_tokens or not right_tokens:
            return 0.0
        overlap = len(left_tokens & right_tokens)
        return 100.0 * overlap / len(left_tokens | right_tokens)


def _relation_for(
    left: DocumentFingerprint, right: DocumentFingerprint, score: float
) -> str:
    """Describe *why* two documents resemble each other."""
    types = {left.document_type, right.document_type}
    if types & {"email", "email_chain"} and abs(
        left.token_count - right.token_count
    ) > max(40, 0.25 * max(left.token_count, right.token_count)):
        return REL_CHAIN_CONTAINS_EARLIER
    if left.subject and right.subject and left.subject == right.subject and score < 99:
        return REL_DRAFT_AND_FINAL
    if score >= 97:
        return REL_NEAR_DUPLICATE
    return REL_POSSIBLE_DUPLICATE


def _components_to_groups(
    edges: Sequence[Tuple[int, int, float, str]], kind: str
) -> List[DuplicateGroup]:
    """Convert a similarity edge list into connected-component groups."""
    parent: Dict[int, int] = {}

    def find(node: int) -> int:
        parent.setdefault(node, node)
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: int, b: int) -> None:
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parent[root_b] = root_a

    scores: Dict[int, List[float]] = defaultdict(list)
    relations: Dict[int, List[str]] = defaultdict(list)
    for left, right, score, relation in edges:
        union(left, right)
        scores[left].append(score)
        scores[right].append(score)
        relations[left].append(relation)
        relations[right].append(relation)

    components: Dict[int, List[int]] = defaultdict(list)
    for node in parent:
        components[find(node)].append(node)

    groups: List[DuplicateGroup] = []
    for index, (root, members) in enumerate(sorted(components.items()), start=1):
        if len(members) < 2:
            continue
        member_scores = [s for m in members for s in scores.get(m, [])]
        member_relations = [r for m in members for r in relations.get(m, [])]
        dominant = (
            max(set(member_relations), key=member_relations.count)
            if member_relations
            else REL_POSSIBLE_DUPLICATE
        )
        groups.append(
            DuplicateGroup(
                group_id=f"NEAR-{index:05d}",
                kind=kind,
                file_ids=sorted(members),
                relation=dominant,
                similarity=round(sum(member_scores) / len(member_scores), 2)
                if member_scores
                else None,
            )
        )
    return groups


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------
def persist_groups(database: Database, groups: Sequence[DuplicateGroup], kind: str) -> None:
    """Replace all membership rows of one kind with ``groups``."""
    database.clear_duplicate_groups(kind)
    members = [
        {
            "group_id": group.group_id,
            "file_id": file_id,
            "similarity": group.similarity,
            "relation": group.relation,
        }
        for group in groups
        for file_id in group.file_ids
    ]
    database.add_duplicate_members(kind, members)
    log.info("Recorded %d %s group(s) covering %d document(s)",
             len(groups), kind, len(members))


def exact_binary_pairs(database: Database) -> Set[Tuple[int, int]]:
    """Return every file-id pair already known to be an exact binary duplicate."""
    pairs: Set[Tuple[int, int]] = set()
    buckets: Dict[str, List[int]] = defaultdict(list)
    for row in database.query(
        "SELECT group_id, file_id FROM duplicate_members WHERE group_kind = ?",
        (KIND_EXACT_BINARY,),
    ):
        buckets[row["group_id"]].append(row["file_id"])
    for members in buckets.values():
        for left, right in itertools.combinations(sorted(members), 2):
            pairs.add((left, right))
    return pairs


def group_lookup(database: Database, kind: str) -> Dict[int, str]:
    """Return ``file_id -> group_id`` for one duplicate-group kind."""
    return {
        row["file_id"]: row["group_id"]
        for row in database.query(
            "SELECT file_id, group_id FROM duplicate_members WHERE group_kind = ?",
            (kind,),
        )
    }
