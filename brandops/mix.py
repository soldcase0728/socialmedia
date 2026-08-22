"""Content mix balance.

Two failure modes this guards against: publishing whatever happened to be
easiest to shoot, and letting athletics quietly become the school's entire
admissions identity. The mix report is what produces the MISSING section of
the daily brief.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .audiences import AUDIENCES, Audience
from .brand import PILLARS, Pillar

PILLAR_TARGETS: dict[Pillar, float] = {p: spec.target_share for p, spec in PILLARS.items()}
AUDIENCE_TARGETS: dict[Audience, float] = {a: spec.target_share for a, spec in AUDIENCES.items()}

# Athletics photographs well and community loves it. It still cannot be more
# than a quarter of what the market sees, or it becomes the whole identity.
ATHLETICS_CAP = 0.25

ATHLETICS_SIGNALS = (
    "game", "football", "basketball", "hockey", "baseball", "soccer", "wrestling",
    "lacrosse", "track", "golf", "tennis", "swim", "coach", "athletics", "varsity",
    "tournament", "championship", "playoff", "roster", "signing day",
)

TOLERANCE = 0.05  # a pillar within five points of target is fine


def is_athletics(text: str) -> bool:
    lowered = f" {text.lower()} "
    return any(signal in lowered for signal in ATHLETICS_SIGNALS)


@dataclass
class MixReport:
    total: int
    pillar_shares: dict[Pillar, float]
    audience_shares: dict[Audience, float]
    platform_counts: dict[str, int]
    athletics_share: float
    warnings: list[str] = field(default_factory=list)

    def pillar_delta(self) -> dict[Pillar, float]:
        return {p: self.pillar_shares.get(p, 0.0) - PILLAR_TARGETS[p] for p in PILLAR_TARGETS}

    def audience_delta(self) -> dict[Audience, float]:
        return {a: self.audience_shares.get(a, 0.0) - AUDIENCE_TARGETS[a] for a in AUDIENCE_TARGETS}

    def pillar_deficits(self, limit: int = 3) -> list[Pillar]:
        deltas = sorted(self.pillar_delta().items(), key=lambda kv: kv[1])
        return [p for p, delta in deltas if delta < -TOLERANCE][:limit]

    def audience_deficits(self, limit: int = 2) -> list[Audience]:
        deltas = sorted(self.audience_delta().items(), key=lambda kv: kv[1])
        return [a for a, delta in deltas if delta < -TOLERANCE][:limit]

    def overweight(self, limit: int = 2) -> list[Pillar]:
        deltas = sorted(self.pillar_delta().items(), key=lambda kv: -kv[1])
        return [p for p, delta in deltas if delta > TOLERANCE][:limit]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "pillar_shares": {p.value: round(v, 3) for p, v in self.pillar_shares.items()},
            "pillar_delta": {p.value: round(v, 3) for p, v in self.pillar_delta().items()},
            "audience_shares": {a.value: round(v, 3) for a, v in self.audience_shares.items()},
            "platform_counts": dict(self.platform_counts),
            "athletics_share": round(self.athletics_share, 3),
            "deficits": [p.value for p in self.pillar_deficits()],
            "overweight": [p.value for p in self.overweight()],
            "warnings": list(self.warnings),
        }

    def as_text(self) -> str:
        lines = [f"Mix over the last {self.total} published items:"]
        for pillar, share in sorted(self.pillar_shares.items(), key=lambda kv: -kv[1]):
            target = PILLAR_TARGETS[pillar]
            lines.append(
                f"  {pillar.spec.name:<26} {share:>5.0%}  (target {target:.0%}, "
                f"{share - target:+.0%})"
            )
        lines.append(f"  athletics topic share: {self.athletics_share:.0%} (cap {ATHLETICS_CAP:.0%})")
        for warning in self.warnings:
            lines.append(f"  ! {warning}")
        return "\n".join(lines)


def analyze(records: Sequence[Mapping[str, Any]]) -> MixReport:
    """Analyze published records.

    Each record needs `pillar` and `audience` (values or enum members); `platform`
    and `text` are optional and used for platform balance and athletics share.
    """
    total = len(records)
    if not total:
        return MixReport(0, {}, {}, {}, 0.0, ["nothing published in this window"])

    pillars = Counter()
    audiences = Counter()
    platforms: Counter = Counter()
    athletics = 0

    for record in records:
        pillar = record.get("pillar")
        if pillar is not None:
            pillars[Pillar(pillar)] += 1
        audience = record.get("audience")
        if audience is not None:
            audiences[Audience(audience)] += 1
        platform = record.get("platform")
        if platform:
            platforms[str(platform)] += 1
        text = " ".join(str(record.get(k, "")) for k in ("text", "event", "topic"))
        if record.get("athletics") or is_athletics(text):
            athletics += 1

    report = MixReport(
        total=total,
        pillar_shares={p: c / total for p, c in pillars.items()},
        audience_shares={a: c / total for a, c in audiences.items()},
        platform_counts=dict(platforms),
        athletics_share=athletics / total,
    )

    if report.athletics_share > ATHLETICS_CAP:
        report.warnings.append(
            f"athletics is {report.athletics_share:.0%} of the mix -- over the "
            f"{ATHLETICS_CAP:.0%} cap; it is becoming the school's whole identity"
        )
    for pillar in report.pillar_deficits():
        report.warnings.append(
            f"{pillar.spec.name} is underweight -- {pillar.spec.evidence_test}"
        )
    for audience in report.audience_deficits():
        report.warnings.append(f"{audience.spec.name} have not been spoken to lately")
    if len(report.platform_counts) < 3:
        report.warnings.append("publishing to fewer than three surfaces")
    return report


def weighted_sequence(count: int, deficits: Sequence[Pillar] = ()) -> list[Pillar]:
    """Build a pillar rotation of `count` slots proportional to target share.

    Deficits are placed first so the next planning window corrects the gap.
    """
    if count <= 0:
        return []
    quotas = {p: PILLAR_TARGETS[p] * count for p in PILLAR_TARGETS}
    allocation = {p: int(q) for p, q in quotas.items()}
    remainder = count - sum(allocation.values())
    leftovers = sorted(quotas.items(), key=lambda kv: -(kv[1] - int(kv[1])))
    for pillar, _ in leftovers[:remainder]:
        allocation[pillar] += 1

    sequence: list[Pillar] = []
    for pillar in deficits:
        if allocation.get(pillar, 0) > 0:
            sequence.append(pillar)
            allocation[pillar] -= 1

    # Interleave the rest so no pillar runs three days in a row.
    pool = [p for p, n in allocation.items() for _ in range(n)]
    pool.sort(key=lambda p: (-allocation.get(p, 0), p.value))
    while pool:
        for pillar in list(dict.fromkeys(pool)):
            pool.remove(pillar)
            sequence.append(pillar)
    return sequence[:count]
