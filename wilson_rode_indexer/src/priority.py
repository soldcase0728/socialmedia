"""Transparent priority scoring.

The score answers one question only: *which documents should a reviewer open
first?*  It is an additive, fully configurable sum of components, and every
component that fires appends a sentence to the explanation, so any score can
be reconstructed by hand from ``config.yaml``.

A high score does **not** prove malpractice, breach, liability, or anything
else.  It means configured screening terms clustered in the document.  Every
report that carries a score repeats this.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

from .config import Config
from .logging_setup import get_logger

log = get_logger("priority")

DISCLAIMER = (
    "Priority score is a review-ordering aid based on configured keyword and "
    "metadata signals. It is not a legal conclusion and does not indicate "
    "malpractice, liability, relevance, or privilege."
)


@dataclass
class PriorityResult:
    """A computed priority score and its human-readable derivation."""

    score: float
    components: List[str] = field(default_factory=list)

    def explanation(self) -> str:
        """Full explanation string written into the report."""
        if not self.components:
            return f"Score 0: no configured priority signals matched. {DISCLAIMER}"
        return f"Score {self.score:g}: " + "; ".join(self.components) + f". {DISCLAIMER}"


class PriorityScorer:
    """Computes the configurable priority score for a document."""

    def __init__(self, config: Config) -> None:
        section = config.section("priority")
        self.enabled = bool(section.get("enabled", True))
        self.tag_weights: Dict[str, float] = {
            str(k): float(v) for k, v in (section.get("tag_weights") or {}).items()
        }
        self.multi_tag_bonus = float(section.get("multi_tag_bonus", 0))
        self.max_multi_tag_bonus = float(section.get("max_multi_tag_bonus", 0))
        self.keyword_bonus: Dict[str, float] = {
            str(k).lower(): float(v)
            for k, v in (section.get("keyword_bonus") or {}).items()
        }
        self.max_keyword_bonus = float(section.get("max_keyword_bonus", 0))
        self.participant_bonus: Dict[str, float] = {
            str(k).lower(): float(v)
            for k, v in (section.get("participant_bonus") or {}).items()
        }
        self.unique_content_bonus = float(section.get("unique_content_bonus", 0))
        self.duplicate_penalty = float(section.get("duplicate_penalty", 0))
        self.manual_review_bonus = float(section.get("manual_review_bonus", 0))
        self.date_windows = list(section.get("date_windows") or [])
        self.min_score = float(section.get("min_score", 0))
        self.max_score = float(section.get("max_score", 100))

    # ------------------------------------------------------------------
    def score(
        self,
        *,
        tags: Sequence[str],
        tag_hit_counts: Optional[Dict[str, int]] = None,
        matched_terms: Optional[Sequence[str]] = None,
        participants: Sequence[Optional[str]] = (),
        document_date: Optional[str] = None,
        is_duplicate: bool = False,
        manual_review_required: bool = False,
    ) -> PriorityResult:
        """Compute the score for one document.

        Parameters
        ----------
        tags:
            Issue tags present on the document.
        tag_hit_counts:
            Per-tag hit counts, used only in the explanation.
        matched_terms:
            Terms that actually matched, used for the keyword bonus.
        participants:
            Derived participants (From/To/Cc values) checked against
            ``participant_bonus``.
        document_date:
            ISO date used against ``date_windows``.
        is_duplicate:
            Whether the document belongs to a text or near-duplicate group.
        manual_review_required:
            Whether the extraction flagged the record for human review.

        Returns
        -------
        PriorityResult
            The clipped score plus one explanation sentence per component.
        """
        if not self.enabled:
            return PriorityResult(0.0, ["priority scoring is disabled in config.yaml"])

        total = 0.0
        components: List[str] = []
        counts = tag_hit_counts or {}

        for tag in sorted(set(tags)):
            weight = self.tag_weights.get(tag)
            if weight:
                total += weight
                hits = counts.get(tag)
                detail = f" ({hits} hit{'s' if hits != 1 else ''})" if hits else ""
                components.append(f"issue tag {tag}{detail} +{weight:g}")

        distinct = len({t for t in tags if t in self.tag_weights})
        if distinct > 1 and self.multi_tag_bonus:
            bonus = min(self.multi_tag_bonus * (distinct - 1), self.max_multi_tag_bonus)
            if bonus:
                total += bonus
                components.append(f"{distinct} distinct scored tags +{bonus:g}")

        if self.keyword_bonus and matched_terms:
            lowered = {str(term).lower() for term in matched_terms}
            keyword_total = 0.0
            fired: List[str] = []
            for keyword, points in self.keyword_bonus.items():
                if keyword in lowered:
                    keyword_total += points
                    fired.append(f"'{keyword}' +{points:g}")
            if keyword_total:
                capped = min(keyword_total, self.max_keyword_bonus) if (
                    self.max_keyword_bonus
                ) else keyword_total
                total += capped
                components.append("high-signal terms " + ", ".join(fired) +
                                  (f" (capped at +{capped:g})" if capped < keyword_total
                                   else ""))

        if self.participant_bonus:
            haystack = " ".join(str(p) for p in participants if p).lower()
            for name, points in self.participant_bonus.items():
                if name in haystack:
                    total += points
                    components.append(f"derived participant matching '{name}' +{points:g}")

        window_points = self._date_window_points(document_date)
        for points, label in window_points:
            total += points
            components.append(f"apparent date falls in {label} +{points:g}")

        if is_duplicate and self.duplicate_penalty:
            total += self.duplicate_penalty
            components.append(
                f"belongs to a duplicate group {self.duplicate_penalty:+g}"
            )
        elif not is_duplicate and self.unique_content_bonus:
            total += self.unique_content_bonus
            components.append(
                f"content appears unique in the production +{self.unique_content_bonus:g}"
            )

        if manual_review_required and self.manual_review_bonus:
            total += self.manual_review_bonus
            components.append(
                f"flagged for manual review +{self.manual_review_bonus:g}"
            )

        clipped = max(self.min_score, min(self.max_score, total))
        if clipped != total:
            components.append(
                f"raw total {total:g} clipped to configured range "
                f"[{self.min_score:g}, {self.max_score:g}]"
            )
        return PriorityResult(round(clipped, 2), components)

    # ------------------------------------------------------------------
    def _date_window_points(self, document_date: Optional[str]) -> List[tuple]:
        """Return ``(points, label)`` for every configured window the date hits."""
        if not document_date or not self.date_windows:
            return []
        try:
            value = datetime.strptime(document_date[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return []
        hits: List[tuple] = []
        for window in self.date_windows:
            try:
                start = datetime.strptime(str(window["start"]), "%Y-%m-%d").date()
                end = datetime.strptime(str(window["end"]), "%Y-%m-%d").date()
            except (KeyError, ValueError, TypeError):
                continue
            if start <= value <= end:
                hits.append((float(window.get("points", 0)),
                             str(window.get("label", f"{start}..{end}"))))
        return hits
