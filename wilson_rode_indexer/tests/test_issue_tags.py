"""Tests for issue tagging and priority scoring."""

from __future__ import annotations

import pytest

from src.issue_tags import IssueTagger, aggregate_tag_counts
from src.priority import DISCLAIMER, PriorityScorer


@pytest.fixture
def tagger() -> IssueTagger:
    """A tagger over a small, explicit dictionary."""
    return IssueTagger(
        {
            "STATUTE_OF_FRAUDS": ["statute of frauds", "one year", "lifetime"],
            "JOHN_WILSON": ["John Wilson", "termination"],
            "INSURANCE": ["reservation of rights", "carrier"],
        },
        context_chars=40,
    )


class TestTagging:
    """Term matching behaviour."""

    def test_matches_a_single_term(self, tagger):
        summary = tagger.tag_text("The statute of frauds bars the claim.")
        assert summary.tags == ["STATUTE_OF_FRAUDS"]
        assert summary.hit_counts["STATUTE_OF_FRAUDS"] == 1

    def test_is_case_insensitive_by_default(self, tagger):
        assert tagger.tag_text("STATUTE OF FRAUDS").tags == ["STATUTE_OF_FRAUDS"]

    def test_respects_word_boundaries(self, tagger):
        """'one year' must not fire inside 'one yearbook'."""
        assert tagger.tag_text("he bought one yearbook").tags == []

    def test_matches_across_flexible_whitespace(self, tagger):
        assert tagger.tag_text("statute  of\nfrauds").tags == ["STATUTE_OF_FRAUDS"]

    def test_counts_repeat_hits(self, tagger):
        summary = tagger.tag_text("lifetime and lifetime and lifetime")
        assert summary.hit_counts["STATUTE_OF_FRAUDS"] == 3

    def test_multiple_tags_on_one_document(self, tagger):
        summary = tagger.tag_text(
            "John Wilson wrote about the statute of frauds and the carrier."
        )
        assert set(summary.tags) == {"STATUTE_OF_FRAUDS", "JOHN_WILSON", "INSURANCE"}

    def test_records_page_numbers(self, tagger):
        summary = tagger.tag_pages([(1, "nothing here"), (2, "lifetime")])
        assert [hit.page_number for hit in summary.hits] == [2]

    def test_records_a_short_locator(self, tagger):
        summary = tagger.tag_text("Preceding words then lifetime then following words")
        locator = summary.hits[0].locator
        assert "lifetime" in locator
        assert len(locator) <= 60

    def test_no_match_yields_no_tags(self, tagger):
        summary = tagger.tag_text("Entirely unrelated prose about weather.")
        assert summary.tags == []
        assert summary.tag_string is None

    def test_empty_text_is_safe(self, tagger):
        assert tagger.tag_pages([(1, ""), (2, None)]).tags == []

    def test_summary_string_includes_counts(self, tagger):
        summary = tagger.tag_text("lifetime lifetime")
        assert summary.summary_string() == "STATUTE_OF_FRAUDS (2)"

    def test_hit_cap_is_enforced(self):
        capped = IssueTagger({"T": ["alpha", "beta", "gamma"]}, max_hits_per_tag=1)
        summary = capped.tag_text("alpha beta gamma")
        assert len(summary.hits) == 1

    def test_aggregate_counts(self, tagger):
        summary = tagger.tag_pages([(1, "lifetime"), (2, "one year")])
        assert aggregate_tag_counts(summary.hits)["STATUTE_OF_FRAUDS"] == 2

    def test_loads_from_project_config(self, config):
        real = IssueTagger.from_config(config)
        assert "STATUTE_OF_FRAUDS" in real.tags
        assert "BANKRUPTCY" in real.tags
        assert real.tag_text("statute of frauds").tags == ["STATUTE_OF_FRAUDS"]


class TestPriorityScoring:
    """Transparent, explainable scoring."""

    def test_no_tags_contributes_no_tag_points(self, config):
        """With no tags, only the configured unique-content bonus can fire."""
        result = PriorityScorer(config).score(tags=[])
        assert not any("issue tag" in component for component in result.components)
        assert result.score == config.get("priority", "unique_content_bonus",
                                          default=0)
        assert DISCLAIMER in result.explanation()

    def test_disabled_scorer_scores_zero(self, config, tmp_path):
        import yaml

        raw = dict(config.raw)
        raw["priority"] = dict(raw["priority"])
        raw["priority"]["enabled"] = False
        path = tmp_path / "config.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")

        from src.config import Config

        result = PriorityScorer(Config.load(path)).score(tags=["STATUTE_OF_FRAUDS"])
        assert result.score == 0

    def test_a_weighted_tag_raises_the_score(self, config):
        result = PriorityScorer(config).score(tags=["STATUTE_OF_FRAUDS"])
        assert result.score > 0
        assert any("STATUTE_OF_FRAUDS" in c for c in result.components)

    def test_more_tags_score_higher(self, config):
        scorer = PriorityScorer(config)
        one = scorer.score(tags=["DAMAGES"]).score
        many = scorer.score(tags=["DAMAGES", "STATUTE_OF_FRAUDS", "APPEAL"]).score
        assert many > one

    def test_explanation_lists_every_component(self, config):
        result = PriorityScorer(config).score(
            tags=["STATUTE_OF_FRAUDS", "JOHN_WILSON"],
            tag_hit_counts={"STATUTE_OF_FRAUDS": 3},
            matched_terms=["statute of frauds"],
            participants=["John Wilson <jw@example.com>"],
        )
        explanation = result.explanation()
        assert "STATUTE_OF_FRAUDS" in explanation
        assert "JOHN_WILSON" in explanation
        assert "statute of frauds" in explanation

    def test_duplicates_are_penalised_relative_to_unique(self, config):
        scorer = PriorityScorer(config)
        unique = scorer.score(tags=["DAMAGES"], is_duplicate=False).score
        duplicate = scorer.score(tags=["DAMAGES"], is_duplicate=True).score
        assert unique > duplicate

    def test_score_is_clipped_to_the_configured_range(self, config):
        result = PriorityScorer(config).score(
            tags=list(config.issue_tags().keys()),
            matched_terms=["statute of frauds", "lifetime", "perpetual",
                           "leave to amend", "affirmative defense"],
            participants=["wilson", "rode"],
        )
        assert 0 <= result.score <= 100

    def test_explanation_never_claims_malpractice(self, config):
        explanation = PriorityScorer(config).score(
            tags=["STATUTE_OF_FRAUDS"]
        ).explanation()
        assert "not a legal conclusion" in explanation.lower()
        assert "malpractice" in explanation.lower()  # only in the disclaimer

    def test_scoring_is_reproducible(self, config):
        scorer = PriorityScorer(config)
        first = scorer.score(tags=["DAMAGES"], matched_terms=["lost revenue"])
        second = scorer.score(tags=["DAMAGES"], matched_terms=["lost revenue"])
        assert first.score == second.score
        assert first.components == second.components
