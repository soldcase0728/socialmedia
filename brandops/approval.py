"""One approval queue, and the rule that nothing gets past it automatically.

The machine does about ninety percent of the preparation. A human makes the
final judgment. That is not a workflow preference -- it is the rule, because
the content is about minors, faith, discipline and claims a school has to
stand behind.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Sequence

from . import config
from .audiences import Audience
from .brand import Pillar
from .copywriting import CopyDraft
from .platforms import Platform
from .scoring import OpportunityScore


class Decision(str, Enum):
    PENDING = "PENDING"
    APPROVE = "APPROVE"
    EDIT = "EDIT"
    REJECT = "REJECT"
    HOLD = "HOLD"


# Conditions that make a card un-approvable until they are cleared. These are
# not warnings; the queue refuses to release the card.
BLOCKERS: dict[str, str] = {
    "consent": "photo release not confirmed for a student in frame",
    "placeholder": "copy still contains an unset link or handle",
    "unverified_claim": "contains a statistic or admissions claim that is not yet verified",
    "not_publishable": "contributor marked the asset as not yet publishable",
}


def approver_for(pillar: Pillar, review_reasons: Sequence[str]) -> str:
    """Route the card to the person who owns this kind of judgment."""
    joined = " ".join(review_reasons).lower()
    if "sensitive" in joined:
        return config.APPROVERS["sensitive"]
    if "statistic" in joined or "claim" in joined:
        return config.APPROVERS["statistics"]
    if pillar is Pillar.CATHOLIC:
        return config.APPROVERS["catholic_identity"]
    if pillar is Pillar.OUTCOMES and "donor" in joined:
        return config.APPROVERS["donor"]
    return config.APPROVERS["default"]


@dataclass
class ApprovalCard:
    """Everything an approver needs on one screen, and nothing else."""

    card_id: str
    asset_ids: tuple[str, ...]
    platform: Platform | None
    audience: Audience
    pillar: Pillar
    caption: str
    scheduled_for: date | None
    scheduled_time: str
    strategic_purpose: str
    score_total: int
    verdict: str
    hook: str = ""
    alt_text: str = ""
    title: str = ""
    flags: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    review_reasons: tuple[str, ...] = ()
    approver: str = ""
    decision: Decision = Decision.PENDING
    decided_by: str = ""
    decided_at: str = ""
    note: str = ""
    paid: bool = False

    @property
    def approved(self) -> bool:
        return self.decision is Decision.APPROVE and not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "asset_ids": list(self.asset_ids),
            "platform": self.platform.value if self.platform else None,
            "audience": self.audience.value,
            "pillar": self.pillar.value,
            "caption": self.caption,
            "scheduled_for": self.scheduled_for.isoformat() if self.scheduled_for else None,
            "scheduled_time": self.scheduled_time,
            "strategic_purpose": self.strategic_purpose,
            "score_total": self.score_total,
            "verdict": self.verdict,
            "hook": self.hook,
            "alt_text": self.alt_text,
            "title": self.title,
            "flags": list(self.flags),
            "warnings": list(self.warnings),
            "blockers": list(self.blockers),
            "review_reasons": list(self.review_reasons),
            "approver": self.approver,
            "decision": self.decision.value,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
            "note": self.note,
            "paid": self.paid,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalCard":
        return cls(
            card_id=data["card_id"],
            asset_ids=tuple(data.get("asset_ids", ())),
            platform=Platform(data["platform"]) if data.get("platform") else None,
            audience=Audience(data["audience"]),
            pillar=Pillar(data["pillar"]),
            caption=data.get("caption", ""),
            scheduled_for=date.fromisoformat(data["scheduled_for"]) if data.get("scheduled_for") else None,
            scheduled_time=data.get("scheduled_time", ""),
            strategic_purpose=data.get("strategic_purpose", ""),
            score_total=int(data.get("score_total", 0)),
            verdict=data.get("verdict", ""),
            hook=data.get("hook", ""),
            alt_text=data.get("alt_text", ""),
            title=data.get("title", ""),
            flags=tuple(data.get("flags", ())),
            warnings=tuple(data.get("warnings", ())),
            blockers=tuple(data.get("blockers", ())),
            review_reasons=tuple(data.get("review_reasons", ())),
            approver=data.get("approver", ""),
            decision=Decision(data.get("decision", "PENDING")),
            decided_by=data.get("decided_by", ""),
            decided_at=data.get("decided_at", ""),
            note=data.get("note", ""),
            paid=bool(data.get("paid", False)),
        )

    def as_text(self) -> str:
        where = self.platform.spec.name if self.platform else "internal"
        when = f"{self.scheduled_for or 'unscheduled'} {self.scheduled_time}".strip()
        lines = [
            f"[{self.card_id}] {where} -- {when}",
            f"Purpose: {self.strategic_purpose}",
            f"Score: {self.score_total}/50 ({self.verdict})   Approver: {self.approver}",
            "",
            self.caption,
        ]
        if self.blockers:
            lines += ["", "BLOCKED:"] + [f"  x {b}" for b in self.blockers]
        if self.flags:
            lines += ["", "Copy flags:"] + [f"  ! {f}" for f in self.flags]
        if self.warnings:
            lines += ["", "Warnings:"] + [f"  - {w}" for w in self.warnings]
        if self.review_reasons:
            lines += ["", "Why a human is looking at this:"] + [f"  - {r}" for r in self.review_reasons]
        lines += ["", "APPROVE / EDIT / REJECT / HOLD"]
        return "\n".join(lines)


def find_blockers(
    draft: CopyDraft,
    *,
    consent_ok: bool = True,
    publish_now_ok: bool = True,
    claim_verified: bool = False,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not consent_ok:
        blockers.append(BLOCKERS["consent"])
    if not publish_now_ok:
        blockers.append(BLOCKERS["not_publishable"])
    if "<<set " in draft.text:
        blockers.append(BLOCKERS["placeholder"])
    if not claim_verified and any("statistic" in w for w in draft.warnings):
        blockers.append(BLOCKERS["unverified_claim"])
    return tuple(blockers)


def build_card(
    card_id: str,
    draft: CopyDraft,
    *,
    pillar: Pillar,
    asset_ids: Sequence[str],
    score: OpportunityScore,
    strategic_purpose: str,
    scheduled_for: date | None = None,
    scheduled_time: str = "",
    hook: str = "",
    review_reasons: Sequence[str] = (),
    consent_ok: bool = True,
    publish_now_ok: bool = True,
    claim_verified: bool = False,
    paid: bool = False,
) -> ApprovalCard:
    return ApprovalCard(
        card_id=card_id,
        asset_ids=tuple(asset_ids),
        platform=draft.platform,
        audience=draft.audience,
        pillar=pillar,
        caption=draft.text,
        scheduled_for=scheduled_for,
        scheduled_time=scheduled_time,
        strategic_purpose=strategic_purpose,
        score_total=score.total,
        verdict=score.verdict.value,
        hook=hook,
        alt_text=draft.alt_text,
        title=draft.title,
        flags=tuple(str(f) for f in draft.flags),
        warnings=tuple(draft.warnings),
        blockers=find_blockers(
            draft,
            consent_ok=consent_ok,
            publish_now_ok=publish_now_ok,
            claim_verified=claim_verified,
        ),
        review_reasons=tuple(review_reasons),
        approver=approver_for(pillar, review_reasons),
        paid=paid,
    )


class ApprovalError(RuntimeError):
    pass


@dataclass
class ApprovalQueue:
    cards: list[ApprovalCard] = field(default_factory=list)

    def add(self, card: ApprovalCard) -> ApprovalCard:
        if any(c.card_id == card.card_id for c in self.cards):
            raise ApprovalError(f"duplicate card id: {card.card_id}")
        self.cards.append(card)
        return card

    def get(self, card_id: str) -> ApprovalCard:
        for card in self.cards:
            if card.card_id == card_id:
                return card
        raise ApprovalError(f"no such card: {card_id}")

    def pending(self) -> list[ApprovalCard]:
        return [c for c in self.cards if c.decision is Decision.PENDING]

    def blocked(self) -> list[ApprovalCard]:
        return [c for c in self.cards if c.blockers]

    def ready_to_schedule(self) -> list[ApprovalCard]:
        return [c for c in self.cards if c.approved]

    def decide(
        self,
        card_id: str,
        decision: Decision,
        *,
        by: str,
        note: str = "",
        when: datetime | None = None,
    ) -> ApprovalCard:
        card = self.get(card_id)
        if decision is Decision.APPROVE and card.blockers:
            raise ApprovalError(
                f"{card_id} cannot be approved while blocked: " + "; ".join(card.blockers)
            )
        if not by.strip():
            raise ApprovalError("a decision requires a named human approver")
        card.decision = decision
        card.decided_by = by.strip()
        card.decided_at = (when or datetime.now()).isoformat(timespec="minutes")
        card.note = note
        return card

    def clear_blocker(self, card_id: str, blocker: str, *, by: str) -> ApprovalCard:
        """Record that a human resolved a blocker (consent obtained, stat verified)."""
        card = self.get(card_id)
        remaining = tuple(b for b in card.blockers if blocker.lower() not in b.lower())
        if len(remaining) == len(card.blockers):
            raise ApprovalError(f"{card_id} has no blocker matching {blocker!r}")
        card.blockers = remaining
        card.note = (card.note + f" | blocker cleared by {by}: {blocker}").strip(" |")
        return card

    def to_dict(self) -> dict[str, Any]:
        return {"cards": [c.to_dict() for c in self.cards]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalQueue":
        return cls(cards=[ApprovalCard.from_dict(c) for c in data.get("cards", [])])


def can_publish(card: ApprovalCard) -> tuple[bool, str]:
    """The single gate every publish path must call. There is no bypass."""
    if card.blockers:
        return False, "blocked: " + "; ".join(card.blockers)
    if card.decision is not Decision.APPROVE:
        return False, f"not approved (decision is {card.decision.value})"
    if not card.decided_by:
        return False, "approval has no named human attached to it"
    return True, "approved by " + card.decided_by
