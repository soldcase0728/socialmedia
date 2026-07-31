"""Configurable issue tagging.

Issue tags are **screening tools only**.  A tag records that a configured term
appeared in a document's extracted text.  It is not a legal conclusion, not a
relevance determination, not a privilege call, and not an assertion that the
document supports any claim.  Every report that carries tags repeats this.

Each hit retains the matching term, the page it appeared on, a hit count, and
a short context *locator*.  The locator is deliberately small and is withheld
from Excel by default so the workbook does not become a dump of confidential
text.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .config import Config
from .logging_setup import get_logger

log = get_logger("issue_tags")

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass
class IssueHit:
    """A single issue-tag match."""

    tag: str
    term: str
    page_number: Optional[int]
    hit_count: int = 1
    locator: Optional[str] = None

    def to_row(self) -> Dict[str, object]:
        """Convert to the dictionary shape :mod:`src.database` expects."""
        return {
            "tag": self.tag,
            "term": self.term,
            "page_number": self.page_number,
            "hit_count": self.hit_count,
            "locator": self.locator,
        }


@dataclass
class TagSummary:
    """Rolled-up tagging result for one document."""

    tags: List[str] = field(default_factory=list)
    hits: List[IssueHit] = field(default_factory=list)
    hit_counts: Dict[str, int] = field(default_factory=dict)
    terms_by_tag: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def tag_string(self) -> Optional[str]:
        """Tags joined for a single report cell."""
        return "; ".join(self.tags) if self.tags else None

    def summary_string(self) -> Optional[str]:
        """``TAG (n hits)`` per tag, for the report."""
        if not self.tags:
            return None
        return "; ".join(f"{tag} ({self.hit_counts.get(tag, 0)})" for tag in self.tags)


class IssueTagger:
    """Matches a configurable dictionary of terms against document text.

    Terms are compiled once into per-tag alternation patterns, so tagging a
    document costs one pass per tag rather than one pass per term.  Matching is
    case-insensitive and word-boundary anchored by default, which stops
    ``one year`` from firing inside ``one yearbook``.
    """

    def __init__(
        self,
        tag_dictionary: Dict[str, Sequence[str]],
        *,
        case_sensitive: bool = False,
        whole_word: bool = True,
        context_chars: int = 60,
        max_hits_per_tag: int = 50,
    ) -> None:
        self.tag_dictionary = {
            tag: list(terms) for tag, terms in (tag_dictionary or {}).items() if terms
        }
        self.case_sensitive = case_sensitive
        self.whole_word = whole_word
        self.context_chars = max(0, context_chars)
        self.max_hits_per_tag = max(1, max_hits_per_tag)
        self._patterns: Dict[str, List[Tuple[str, re.Pattern]]] = {}
        self._compile()

    @classmethod
    def from_config(cls, config: Config) -> "IssueTagger":
        """Build a tagger from ``issue_tags`` and ``issue_tag_options``."""
        options = config.section("issue_tag_options")
        return cls(
            config.issue_tags(),
            case_sensitive=bool(options.get("case_sensitive", False)),
            whole_word=bool(options.get("whole_word", True)),
            context_chars=int(options.get("context_chars", 60)),
            max_hits_per_tag=int(options.get("max_hits_per_tag", 50)),
        )

    # ------------------------------------------------------------------
    def _compile(self) -> None:
        """Compile one regex per term, grouped by tag."""
        flags = 0 if self.case_sensitive else re.IGNORECASE
        for tag, terms in self.tag_dictionary.items():
            compiled: List[Tuple[str, re.Pattern]] = []
            for term in terms:
                escaped = re.escape(str(term))
                # Allow flexible whitespace inside multi-word terms.
                escaped = escaped.replace(r"\ ", r"\s+")
                pattern = (
                    rf"(?<!\w){escaped}(?!\w)" if self.whole_word else escaped
                )
                try:
                    compiled.append((str(term), re.compile(pattern, flags)))
                except re.error as exc:  # pragma: no cover - defensive
                    log.warning("Skipping unusable term %r in tag %s: %s", term, tag, exc)
            if compiled:
                self._patterns[tag] = compiled

    @property
    def tags(self) -> List[str]:
        """All configured tag names."""
        return sorted(self._patterns)

    # ------------------------------------------------------------------
    def tag_pages(self, pages: Sequence[Tuple[int, str]]) -> TagSummary:
        """Tag a document supplied as ``(page_number, text)`` pairs.

        Returns
        -------
        TagSummary
            Distinct tags, per-tag hit counts, matched terms, and per-hit
            records carrying the page number and a short locator.
        """
        summary = TagSummary()
        counts: Dict[str, int] = defaultdict(int)
        terms_seen: Dict[str, List[str]] = defaultdict(list)
        per_tag_hits: Dict[str, int] = defaultdict(int)

        for page_number, text in pages:
            if not text:
                continue
            for tag, compiled in self._patterns.items():
                for term, pattern in compiled:
                    if per_tag_hits[tag] >= self.max_hits_per_tag:
                        break
                    matches = list(pattern.finditer(text))
                    if not matches:
                        continue
                    counts[tag] += len(matches)
                    if term not in terms_seen[tag]:
                        terms_seen[tag].append(term)
                    summary.hits.append(
                        IssueHit(
                            tag=tag,
                            term=term,
                            page_number=page_number,
                            hit_count=len(matches),
                            locator=self._locator(text, matches[0]),
                        )
                    )
                    per_tag_hits[tag] += 1

        summary.tags = sorted(counts)
        summary.hit_counts = dict(counts)
        summary.terms_by_tag = {tag: terms_seen[tag] for tag in summary.tags}
        return summary

    def tag_text(self, text: str, page_number: Optional[int] = None) -> TagSummary:
        """Tag a single block of text."""
        return self.tag_pages([(page_number or 1, text)])

    # ------------------------------------------------------------------
    def _locator(self, text: str, match: re.Match) -> str:
        """Build a short context locator around a match.

        The locator exists so a reviewer can find the hit quickly.  It is kept
        deliberately short and is withheld from Excel by default; it is not a
        substitute for reading the document.
        """
        if self.context_chars <= 0:
            return ""
        start = max(0, match.start() - self.context_chars // 2)
        end = min(len(text), match.end() + self.context_chars // 2)
        snippet = _WHITESPACE_RE.sub(" ", text[start:end]).strip()
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{snippet}{suffix}"[: self.context_chars + 12]


def aggregate_tag_counts(hits: Iterable[IssueHit]) -> Dict[str, int]:
    """Total hit counts per tag across an iterable of hits."""
    counts: Dict[str, int] = defaultdict(int)
    for hit in hits:
        counts[hit.tag] += hit.hit_count
    return dict(counts)
