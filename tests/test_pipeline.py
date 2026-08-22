"""Intake -> lifecycle -> triage -> score -> package -> copy -> approval."""

from __future__ import annotations

from datetime import date

import pytest

from brandops.approval import (
    ApprovalError,
    ApprovalQueue,
    Decision,
    build_card,
    can_publish,
)
from brandops.assets import IntakeError, Status, TransitionError, from_intake, unresolved
from brandops.audiences import Audience
from brandops.brand import Pillar, scan_copy
from brandops.copywriting import write_copy, write_package_copy
from brandops.hooks import generate_hooks
from brandops.packages import build_package
from brandops.platforms import Platform
from brandops.scoring import OpportunityScore, ScoreError, Verdict, qualifies_for_slot, rank
from brandops.triage import triage, triage_batch


# -- intake -----------------------------------------------------------------

def test_intake_requires_the_four_fields():
    with pytest.raises(IntakeError) as exc:
        from_intake({"event": "Mass"})
    assert "department" in str(exc.value)


def test_intake_infers_video_from_extension(lab_video):
    assert lab_video.kind.value == "video"


def test_intake_defaults_optional_fields_rather_than_bouncing_the_teacher():
    asset = from_intake({
        "event": "Lunch", "department": "Student Life",
        "contributor": "Ms. R", "description": "lunch table",
    })
    assert asset.captured_at == date.today()
    assert asset.consent_ok is True
    assert asset.status is Status.RAW


def test_sensitive_language_auto_flags_even_when_the_box_is_unchecked():
    asset = from_intake({
        "event": "Practice", "department": "Athletics",
        "contributor": "Coach", "description": "update on a player injury",
    })
    assert asset.sensitive is True


# -- lifecycle --------------------------------------------------------------

def test_legal_transitions_advance_and_record_history(lab_video):
    lab_video.advance(Status.REVIEWED).advance(Status.CONTENT_OPPORTUNITY, "strong lab footage")
    assert lab_video.status is Status.CONTENT_OPPORTUNITY
    assert "strong lab footage" in lab_video.history[-1]


def test_illegal_transition_is_refused(lab_video):
    with pytest.raises(TransitionError):
        lab_video.advance(Status.PUBLISHED)


def test_rejected_is_terminal(lab_video):
    lab_video.advance(Status.REJECTED)
    with pytest.raises(TransitionError):
        lab_video.advance(Status.REVIEWED)


def test_every_asset_must_resolve_somewhere(lab_video, mass_photo):
    assert unresolved([lab_video, mass_photo]) == [lab_video, mass_photo]
    lab_video.advance(Status.REVIEWED).advance(Status.LIBRARY)
    mass_photo.advance(Status.REJECTED)
    assert unresolved([lab_video, mass_photo]) == []


def test_asset_round_trips_through_json(lab_video):
    from brandops.assets import Asset
    clone = Asset.from_dict(lab_video.to_dict())
    assert clone.to_dict() == lab_video.to_dict()


# -- scoring ----------------------------------------------------------------

def test_score_rejects_out_of_range_values():
    with pytest.raises(ScoreError):
        OpportunityScore(6, 3, 3, 3, 3, 3, 3, 3, 3, 3)


def test_verdict_thresholds():
    # Bands are on the unweighted total out of 50: 40+ / 33+ / 26+ / 20+ / below.
    assert OpportunityScore(*([5] * 10)).verdict is Verdict.LEAD          # 50
    assert OpportunityScore(*([4] * 10)).verdict is Verdict.LEAD          # 40, exactly on the floor
    assert OpportunityScore(*([4] * 5 + [3] * 5)).verdict is Verdict.PUBLISH   # 35
    assert OpportunityScore(*([3] * 10)).verdict is Verdict.DEVELOP       # 30
    assert OpportunityScore(*([3] * 5 + [2] * 5)).verdict is Verdict.LIBRARY   # 25
    assert OpportunityScore(*([1] * 10)).verdict is Verdict.REJECT        # 10


def test_verdict_band_floors_are_inclusive():
    assert OpportunityScore(*([4] * 3 + [3] * 7)).total == 33
    assert OpportunityScore(*([4] * 3 + [3] * 7)).verdict is Verdict.PUBLISH
    assert OpportunityScore(*([2] * 10)).total == 20
    assert OpportunityScore(*([2] * 10)).verdict is Verdict.LIBRARY


def test_an_empty_calendar_slot_is_not_a_reason_to_publish():
    mediocre = OpportunityScore(*([3] * 10))
    assert not qualifies_for_slot(mediocre)


def test_rank_puts_the_strongest_first():
    weak = OpportunityScore(*([2] * 10))
    strong = OpportunityScore(*([5] * 10))
    ordered = rank([("a", weak), ("b", strong)])
    assert [key for key, _ in ordered] == ["b", "a"]


def test_fix_list_names_what_would_have_to_change():
    score = OpportunityScore(2, 5, 5, 5, 5, 5, 5, 5, 5, 5)
    assert any("emotional_strength" in item for item in score.fix_list())


# -- triage -----------------------------------------------------------------

def test_triage_reads_the_pillar_from_the_description(lab_video, today):
    assert triage(lab_video, today=today).primary_pillar is Pillar.CHALLENGED


def test_triage_falls_back_to_department_when_text_is_silent(today):
    asset = from_intake({
        "event": "Morning gathering", "department": "Campus Ministry",
        "contributor": "Fr. N", "description": "students in the courtyard",
    })
    assert triage(asset, today=today).primary_pillar is Pillar.CATHOLIC


def test_vertical_video_routes_to_short_form(lab_video, today):
    platforms = triage(lab_video, today=today).platforms
    assert Platform.INSTAGRAM_REEL in platforms
    assert Platform.TIKTOK in platforms


def test_horizontal_video_does_not_route_to_reels(today):
    asset = from_intake({
        "event": "Alumni panel", "department": "Advancement", "contributor": "K",
        "description": "alumni speaking to seniors", "filename": "p.mov",
        "orientation": "horizontal", "duration_s": 300,
    })
    platforms = triage(asset, today=today).platforms
    assert Platform.INSTAGRAM_REEL not in platforms
    assert Platform.YOUTUBE in platforms


def test_missing_consent_blocks_paid_candidacy(today):
    asset = from_intake({
        "event": "Signing day", "department": "College Counseling", "contributor": "K",
        "description": "student signs his scholarship letter", "consent_ok": "no",
    })
    assert triage(asset, today=today).paid_candidate is False


def test_triage_always_requires_human_review_for_student_content(lab_video, today):
    assert triage(lab_video, today=today).review_reasons


def test_triage_asks_for_the_missing_footage(lab_video, today):
    wants = triage(lab_video, today=today).needs_more_footage
    assert any("one sentence" in w for w in wants)


def test_perishable_content_is_same_day(today):
    asset = from_intake({
        "event": "Homecoming game", "department": "Athletics", "contributor": "Coach",
        "description": "student section during the fourth quarter",
        "captured_at": today.isoformat(), "filename": "g.mov", "duration_s": 12,
    })
    assert triage(asset, today=today).urgency == "same_day"


def test_old_footage_is_evergreen(today):
    asset = from_intake({
        "event": "Chapel interior", "department": "Campus Ministry", "contributor": "K",
        "description": "the chapel in morning light", "captured_at": "2026-06-01",
    })
    assert triage(asset, today=today).urgency == "evergreen"


def test_triage_batch_returns_strongest_first(lab_video, mass_photo, today):
    ordered = triage_batch([mass_photo, lab_video], today=today)
    assert ordered[0].score.total >= ordered[1].score.total


# -- hooks ------------------------------------------------------------------

def test_hooks_never_contain_unfilled_placeholders():
    hooks = generate_hooks("AP Chemistry lab", pillar=Pillar.CHALLENGED,
                           audience=Audience.GRADE_8)
    assert hooks
    for hook in hooks:
        assert "{" not in hook.text


def test_hooks_skip_structures_whose_facts_are_missing():
    hooks = generate_hooks("Signing day", pillar=Pillar.OUTCOMES,
                           audience=Audience.PROSPECTIVE_PARENT)
    # No verified statistic was supplied, so no statistic hook may be invented.
    assert all(h.structure.value != "surprising_stat" for h in hooks)


def test_a_supplied_statistic_unlocks_the_stat_hook_and_flags_it_for_verification():
    hooks = generate_hooks("Class of 2026", pillar=Pillar.OUTCOMES,
                           audience=Audience.PROSPECTIVE_PARENT,
                           values={"stat": "Every senior was accepted somewhere."})
    stat_hooks = [h for h in hooks if h.structure.value == "surprising_stat"]
    assert stat_hooks and stat_hooks[0].requires_verification


def test_generated_hooks_survive_the_copy_lint():
    for pillar in Pillar:
        for hook in generate_hooks("a normal Tuesday", pillar=pillar,
                                   audience=Audience.PROSPECTIVE_PARENT):
            assert scan_copy(hook.text) == []


# -- packages and copy ------------------------------------------------------

def test_one_event_becomes_many_outputs(lab_video, today):
    package = build_package(triage(lab_video, today=today), [lab_video])
    keys = {item.key for item in package.items}
    assert {"reel", "tiktok", "youtube_short", "parent_post"} <= keys
    assert {"quote_card", "website_photo", "evergreen"} <= keys  # banked, not published


def test_paid_creative_appears_only_for_paid_candidates(today):
    asset = from_intake({
        "event": "Lunch", "department": "Student Life", "contributor": "R",
        "description": "students at a lunch table", "consent_ok": "no",
    })
    result = triage(asset, today=today)
    package = build_package(result, [asset])
    assert result.paid_candidate is False
    assert all(not item.paid for item in package.items)


def test_copy_differs_per_platform(lab_video, today):
    result = triage(lab_video, today=today)
    package = build_package(result, [lab_video])
    drafts = write_package_copy(
        [i for i in package.items if i.platform],
        story=lab_video.event, pillar=result.primary_pillar,
        hook=result.hooks[0], evidence=[lab_video.possible_story],
    )
    texts = {d.platform: d.text for d in drafts}
    assert len(set(texts.values())) > 1, "copy was pasted identically across platforms"


def test_tiktok_copy_carries_no_call_to_action(lab_video, today):
    result = triage(lab_video, today=today)
    package = build_package(result, [lab_video])
    tiktok = next(i for i in package.items if i.platform is Platform.TIKTOK)
    draft = write_copy(tiktok, story=lab_video.event, pillar=result.primary_pillar,
                       evidence=[lab_video.possible_story])
    assert draft.cta == ""


def test_copy_warns_about_unset_links(lab_video, today):
    result = triage(lab_video, today=today)
    package = build_package(result, [lab_video])
    reel = next(i for i in package.items if i.platform is Platform.INSTAGRAM_REEL)
    draft = write_copy(reel, story=lab_video.event, pillar=result.primary_pillar)
    assert any("unset link" in w for w in draft.warnings)


def test_copy_flags_a_statistic_for_verification(lab_video, today):
    result = triage(lab_video, today=today)
    package = build_package(result, [lab_video])
    item = next(i for i in package.items if i.platform is Platform.TIKTOK)
    draft = write_copy(item, story=lab_video.event, pillar=result.primary_pillar,
                       evidence=["94% of the class scored a 3 or better"])
    assert any("statistic" in w for w in draft.warnings)


# -- approval ---------------------------------------------------------------

def _card(**overrides):
    from brandops.copywriting import CopyDraft
    draft = CopyDraft(
        platform=Platform.FACEBOOK, audience=Audience.PROSPECTIVE_PARENT,
        opening="A hook", body="Nine juniors ran the titration twice.", cta="",
        hashtags=(), alt_text="students in a lab",
    )
    defaults = dict(
        pillar=Pillar.CHALLENGED, asset_ids=["a1"],
        score=OpportunityScore(*([4] * 10)), strategic_purpose="prove the work is real",
    )
    defaults.update(overrides)
    return build_card("card-1", draft, **defaults)


def test_nothing_publishes_without_a_named_human():
    queue = ApprovalQueue()
    card = queue.add(_card())
    ok, why = can_publish(card)
    assert not ok and "not approved" in why
    with pytest.raises(ApprovalError):
        queue.decide("card-1", Decision.APPROVE, by="   ")
    queue.decide("card-1", Decision.APPROVE, by="Director of Marketing")
    ok, why = can_publish(card)
    assert ok and "Director of Marketing" in why


def test_blocked_cards_cannot_be_approved():
    queue = ApprovalQueue()
    queue.add(_card(consent_ok=False))
    with pytest.raises(ApprovalError):
        queue.decide("card-1", Decision.APPROVE, by="Director of Marketing")


def test_clearing_a_blocker_records_who_cleared_it():
    queue = ApprovalQueue()
    card = queue.add(_card(consent_ok=False))
    queue.clear_blocker("card-1", "photo release", by="Admissions Director")
    assert card.blockers == ()
    assert "Admissions Director" in card.note
    queue.decide("card-1", Decision.APPROVE, by="Admissions Director")
    assert can_publish(card)[0]


def test_catholic_content_routes_to_campus_ministry():
    card = _card(pillar=Pillar.CATHOLIC)
    assert "Campus Ministry" in card.approver


def test_sensitive_content_routes_to_the_head_of_school():
    card = _card(review_reasons=["flagged sensitive at intake"])
    assert "Head of School" in card.approver


def test_queue_round_trips_through_json():
    queue = ApprovalQueue()
    queue.add(_card())
    clone = ApprovalQueue.from_dict(queue.to_dict())
    assert clone.to_dict() == queue.to_dict()


def test_duplicate_card_ids_are_refused():
    queue = ApprovalQueue()
    queue.add(_card())
    with pytest.raises(ApprovalError):
        queue.add(_card())
