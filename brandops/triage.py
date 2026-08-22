"""Automated triage of everything that lands in the content inbox.

Runs on arrival, before a human has looked at anything. It reads the asset and
its intake metadata and proposes: pillar, audience, platforms, paid potential,
urgency, story angle, hooks, what footage is still missing, and an opportunity
score. A human confirms or overrides -- but never starts from a blank folder.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Sequence

from .assets import Asset, AssetKind, Orientation, Status
from .audiences import PILLAR_AUDIENCES, Audience, audience_read
from .brand import Pillar, classify_pillars
from .hooks import Hook, generate_hooks, missing_facts
from .platforms import Platform
from .scoring import OpportunityScore, Verdict, rank

DEPARTMENT_DEFAULTS: dict[str, Pillar] = {
    "campus ministry": Pillar.CATHOLIC,
    "chapel": Pillar.CATHOLIC,
    "theology": Pillar.CATHOLIC,
    "athletics": Pillar.BELONGING,
    "admissions": Pillar.KNOWN,
    "science": Pillar.CHALLENGED,
    "math": Pillar.CHALLENGED,
    "english": Pillar.CHALLENGED,
    "history": Pillar.CHALLENGED,
    "world languages": Pillar.CHALLENGED,
    "arts": Pillar.BELONGING,
    "music": Pillar.BELONGING,
    "theater": Pillar.BELONGING,
    "student life": Pillar.BELONGING,
    "counseling": Pillar.KNOWN,
    "college counseling": Pillar.OUTCOMES,
    "advancement": Pillar.OUTCOMES,
    "alumni": Pillar.OUTCOMES,
    "service": Pillar.FORMATION,
    "leadership": Pillar.FORMATION,
}

PERISHABLE = (
    "game", "match", "meet", "tonight", "today", "mass", "signing", "decision day",
    "competition", "tournament", "performance", "concert", "assembly", "feast",
    "retreat", "snow", "championship", "finals", "opening", "first day", "last day",
    "graduation", "homecoming", "spirit week", "open house",
)

POSED = ("group photo", "posed", "lineup", "line up", "photo op", "grip and grin",
         "team photo", "check presentation", "ribbon cutting")
CANDID = ("candid", "unposed", "caught", "behind the scenes", "unscripted", "reaction")
EMOTION = ("first", "last", "tears", "cheer", "hug", "celebrat", "reunion", "tribute",
           "memor", "farewell", "surprise", "standing ovation", "nervous", "relief")
LOGISTICAL = ("setup", "set up", "banner", "sign ", "empty", "parking", "schedule",
              "flyer", "poster", "logo")
NUMERIC = ("%", "percent", "scholarship", "gpa", "score", "average", "rate", "$")


def _clamp(value: int) -> int:
    return max(1, min(5, value))


def _contains(text: str, needles: Sequence[str]) -> bool:
    return any(n in text for n in needles)


@dataclass
class TriageResult:
    """What the automation proposes for one asset."""

    asset_id: str
    primary_pillar: Pillar
    secondary_pillars: tuple[Pillar, ...]
    audiences: tuple[Audience, ...]
    platforms: tuple[Platform, ...]
    urgency: str  # same_day | this_week | evergreen
    organic: bool
    paid_candidate: bool
    story_angle: str
    hooks: tuple[Hook, ...]
    needs_more_footage: tuple[str, ...]
    missing_facts: tuple[str, ...]
    review_reasons: tuple[str, ...]
    score: OpportunityScore
    recommended_status: Status

    @property
    def audience_read(self) -> str:
        return audience_read(list(self.audiences))

    @property
    def verdict(self) -> Verdict:
        return self.score.verdict

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "primary_pillar": self.primary_pillar.value,
            "secondary_pillars": [p.value for p in self.secondary_pillars],
            "audiences": [a.value for a in self.audiences],
            "audience_read": self.audience_read,
            "platforms": [p.value for p in self.platforms],
            "urgency": self.urgency,
            "organic": self.organic,
            "paid_candidate": self.paid_candidate,
            "story_angle": self.story_angle,
            "hooks": [h.to_dict() for h in self.hooks],
            "needs_more_footage": list(self.needs_more_footage),
            "missing_facts": list(self.missing_facts),
            "review_reasons": list(self.review_reasons),
            "score": self.score.to_dict(),
            "score_total": self.score.total,
            "verdict": self.verdict.value,
            "recommended_status": self.recommended_status.value,
        }


def _pillars_for(asset: Asset) -> tuple[Pillar, tuple[Pillar, ...], int]:
    hits = classify_pillars(asset.searchable_text)
    if hits:
        primary = hits[0][0]
        return primary, tuple(p for p, _ in hits[1:3]), hits[0][1]
    department = asset.department.strip().lower()
    for key, pillar in DEPARTMENT_DEFAULTS.items():
        if key in department:
            return pillar, (), 0
    return Pillar.BELONGING, (), 0


def _urgency(asset: Asset, today: date) -> str:
    text = asset.searchable_text.lower()
    age = (today - asset.captured_at).days
    if _contains(text, PERISHABLE) and age <= 2 and asset.publish_now_ok:
        return "same_day"
    if age <= 7:
        return "this_week"
    return "evergreen"


def _platforms_for(asset: Asset, audiences: Sequence[Audience], pillar: Pillar) -> tuple[Platform, ...]:
    vertical = asset.orientation is Orientation.VERTICAL
    chosen: list[Platform] = []

    def add(platform: Platform) -> None:
        if platform not in chosen:
            chosen.append(platform)

    if asset.kind is AssetKind.VIDEO and vertical:
        for audience in audiences:
            if audience in (Audience.GRADE_6_7, Audience.GRADE_8):
                add(Platform.TIKTOK)
            if audience in (Audience.PROSPECTIVE_PARENT, Audience.CURRENT_PARENT):
                add(Platform.FACEBOOK)
        add(Platform.INSTAGRAM_REEL)
        add(Platform.YOUTUBE_SHORTS)
        add(Platform.INSTAGRAM_STORY)
    elif asset.kind is AssetKind.VIDEO:
        add(Platform.YOUTUBE)
        add(Platform.FACEBOOK)
    else:
        add(Platform.INSTAGRAM_FEED)
        add(Platform.FACEBOOK)
        add(Platform.INSTAGRAM_STORY)

    if pillar is Pillar.OUTCOMES:
        add(Platform.LINKEDIN)
    return tuple(chosen)


def _story_angle(asset: Asset, pillar: Pillar) -> str:
    subject = asset.subjects[0] if asset.subjects else "a student"
    spec = pillar.spec
    if asset.possible_story:
        return asset.possible_story.rstrip(".") + f" -- carried as {spec.name.lower()}."
    return (
        f"{asset.event}: use {subject} to prove {spec.name.lower()}. "
        f"{spec.evidence_test}"
    )


def _needs_more_footage(asset: Asset, pillar: Pillar) -> tuple[str, ...]:
    wants: list[str] = []
    text = asset.searchable_text.lower()
    if asset.kind is AssetKind.VIDEO and (asset.duration_s or 0) < 8:
        wants.append("clip is under 8s -- get two more angles of the same moment")
    if asset.kind is AssetKind.PHOTO:
        wants.append("3-5 vertical clips, 5-10s each, of the same activity")
    if asset.orientation is not Orientation.VERTICAL and asset.kind is AssetKind.VIDEO:
        wants.append("re-shoot vertical, or plan this as YouTube/Facebook only")
    if not asset.subjects:
        wants.append("names of the students in frame (and their consent status)")
    if "says" not in text and "quote" not in text:
        wants.append("one student explaining what he is doing, in one sentence")
    if pillar is Pillar.KNOWN and "teacher" not in text and "coach" not in text:
        wants.append("one teacher-student interaction in the same setting")
    if pillar is Pillar.OUTCOMES and not _contains(text, NUMERIC):
        wants.append("the verifiable number: acceptance, scholarship, score or destination")
    return tuple(wants)


def _review_reasons(asset: Asset, pillar: Pillar) -> tuple[str, ...]:
    reasons: list[str] = ["students appear in this asset"]
    text = asset.searchable_text.lower()
    if not asset.consent_ok:
        reasons.append("photo release not confirmed -- do not publish until it is")
    if asset.sensitive or asset.flags_sensitive_language():
        reasons.append("flagged sensitive at intake or by language scan")
    if pillar is Pillar.CATHOLIC:
        reasons.append("religious content -- confirm accuracy and tone with campus ministry")
    if _contains(text, NUMERIC):
        reasons.append("contains a claim or statistic that must be verified before publishing")
    if not asset.publish_now_ok:
        reasons.append("contributor marked this as not-yet-publishable")
    return tuple(reasons)


def _auto_score(asset: Asset, pillar: Pillar, pillar_hits: int, urgency: str) -> OpportunityScore:
    text = asset.searchable_text.lower()
    vertical_video = asset.kind is AssetKind.VIDEO and asset.orientation is Orientation.VERTICAL
    posed = _contains(text, POSED)
    candid = _contains(text, CANDID)
    named = bool(asset.subjects)

    emotional = 3 + _contains(text, EMOTION) + (pillar in (Pillar.FORMATION, Pillar.CATHOLIC, Pillar.OUTCOMES) and named)
    emotional -= _contains(text, LOGISTICAL)

    visual = 3 + vertical_video + candid - posed
    visual -= _contains(text, LOGISTICAL)

    authenticity = 4 - 2 * posed + candid

    parent_base = {Pillar.KNOWN: 5, Pillar.CHALLENGED: 5, Pillar.OUTCOMES: 5,
                   Pillar.FORMATION: 4, Pillar.CATHOLIC: 4, Pillar.BELONGING: 3}[pillar]
    student_base = {Pillar.BELONGING: 5, Pillar.OUTCOMES: 4, Pillar.CHALLENGED: 3,
                    Pillar.KNOWN: 3, Pillar.FORMATION: 3, Pillar.CATHOLIC: 3}[pillar]
    student_base += vertical_video

    fit = 2 + pillar_hits

    differentiation = 3 + _contains(text, ("polish", "heritage", "chapel", "orchard lake"))
    differentiation += named
    differentiation -= _contains(text, ("assembly", "meeting", "announcement"))

    timeliness = {"same_day": 5, "this_week": 3, "evergreen": 2}[urgency]

    admissions_base = {Pillar.OUTCOMES: 5, Pillar.KNOWN: 5, Pillar.CHALLENGED: 4,
                       Pillar.FORMATION: 4, Pillar.CATHOLIC: 3, Pillar.BELONGING: 3}[pillar]
    admissions_base += _contains(text, NUMERIC)
    admissions_base -= 0 if asset.consent_ok else 2

    share = 3 + named + (pillar in (Pillar.BELONGING, Pillar.OUTCOMES))
    share -= _contains(text, LOGISTICAL)

    return OpportunityScore(
        emotional_strength=_clamp(int(emotional)),
        visual_strength=_clamp(int(visual)),
        authenticity=_clamp(int(authenticity)),
        parent_relevance=_clamp(int(parent_base)),
        student_relevance=_clamp(int(student_base)),
        pillar_fit=_clamp(int(fit)),
        differentiation=_clamp(int(differentiation)),
        timeliness=_clamp(int(timeliness)),
        admissions_value=_clamp(int(admissions_base)),
        shareability=_clamp(int(share)),
    )


def _recommended_status(score: OpportunityScore, asset: Asset) -> Status:
    if score.verdict in (Verdict.LEAD, Verdict.PUBLISH):
        return Status.CONTENT_OPPORTUNITY
    if score.verdict is Verdict.DEVELOP:
        return Status.CONTENT_OPPORTUNITY if asset.consent_ok else Status.REVIEWED
    if score.verdict is Verdict.LIBRARY:
        return Status.LIBRARY
    return Status.REJECTED


def triage(asset: Asset, *, today: date | None = None) -> TriageResult:
    """Classify one asset and propose everything a human would otherwise decide."""
    today = today or date.today()
    primary, secondary, hits = _pillars_for(asset)
    audiences = PILLAR_AUDIENCES[primary]
    urgency = _urgency(asset, today)
    score = _auto_score(asset, primary, hits, urgency)
    platforms = _platforms_for(asset, audiences, primary)

    values: dict[str, str] = {}
    if asset.subjects:
        values["subject"] = asset.subjects[0]
    hooks = generate_hooks(
        asset.event, pillar=primary, audience=audiences[0], values=values
    )

    paid = (
        primary in (Pillar.KNOWN, Pillar.CHALLENGED, Pillar.OUTCOMES, Pillar.FORMATION)
        and score.admissions_value >= 4
        and asset.consent_ok
        and not asset.sensitive
    )

    return TriageResult(
        asset_id=asset.asset_id,
        primary_pillar=primary,
        secondary_pillars=secondary,
        audiences=audiences,
        platforms=platforms,
        urgency=urgency,
        organic=True,
        paid_candidate=paid,
        story_angle=_story_angle(asset, primary),
        hooks=tuple(hooks),
        needs_more_footage=_needs_more_footage(asset, primary),
        missing_facts=tuple(missing_facts(primary, values)),
        review_reasons=_review_reasons(asset, primary),
        score=score,
        recommended_status=_recommended_status(score, asset),
    )


def triage_batch(assets: Iterable[Asset], *, today: date | None = None) -> list[TriageResult]:
    """Triage an inbox and return it strongest-opportunity-first."""
    results = [triage(asset, today=today) for asset in assets]
    ordered = rank([(r, r.score) for r in results])
    return [result for result, _ in ordered]
