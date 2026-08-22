"""Assets, intake metadata and the lifecycle every asset must resolve to.

The failure mode this module exists to prevent: a folder with nine hundred
forgotten photographs in it. Every asset ends as a content opportunity, an
entry in the evergreen library, or an intentional rejection.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Iterable


class AssetKind(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"


class Orientation(str, Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    SQUARE = "square"


class Status(str, Enum):
    """The pipeline every asset moves through."""

    RAW = "RAW"
    REVIEWED = "REVIEWED"
    CONTENT_OPPORTUNITY = "CONTENT_OPPORTUNITY"
    DRAFTED = "DRAFTED"
    APPROVED = "APPROVED"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    MEASURED = "MEASURED"
    # Terminal side-exits.
    LIBRARY = "LIBRARY"
    REJECTED = "REJECTED"


MAIN_LINE: tuple[Status, ...] = (
    Status.RAW,
    Status.REVIEWED,
    Status.CONTENT_OPPORTUNITY,
    Status.DRAFTED,
    Status.APPROVED,
    Status.SCHEDULED,
    Status.PUBLISHED,
    Status.MEASURED,
)

TRANSITIONS: dict[Status, tuple[Status, ...]] = {
    Status.RAW: (Status.REVIEWED, Status.REJECTED),
    Status.REVIEWED: (Status.CONTENT_OPPORTUNITY, Status.LIBRARY, Status.REJECTED),
    Status.CONTENT_OPPORTUNITY: (Status.DRAFTED, Status.LIBRARY, Status.REJECTED),
    Status.DRAFTED: (Status.APPROVED, Status.CONTENT_OPPORTUNITY, Status.REJECTED),
    Status.APPROVED: (Status.SCHEDULED, Status.DRAFTED, Status.REJECTED),
    Status.SCHEDULED: (Status.PUBLISHED, Status.APPROVED, Status.REJECTED),
    Status.PUBLISHED: (Status.MEASURED,),
    Status.MEASURED: (Status.LIBRARY,),
    Status.LIBRARY: (Status.CONTENT_OPPORTUNITY,),
    Status.REJECTED: (),
}


class TransitionError(ValueError):
    """Raised when an asset is pushed somewhere the pipeline does not allow."""


def can_transition(current: Status, target: Status) -> bool:
    return target in TRANSITIONS[current]


# Intake fields collected by the phone upload form. Anything not on this list
# is the automation's job, not the contributor's. Nobody renames a file.
INTAKE_FIELDS: tuple[tuple[str, bool, str], ...] = (
    ("event", True, "What was happening? e.g. 'AP Bio lab', 'All-School Mass'"),
    ("department", True, "Department, team, club or grade"),
    ("contributor", True, "Your name -- so we can ask a follow-up question"),
    ("description", True, "One sentence. What is in the shot?"),
    ("captured_at", False, "Date taken (defaults to upload date)"),
    ("subjects", False, "Student or faculty names, if you know them"),
    ("possible_story", False, "Anything we would not know from looking at it"),
    ("publish_now_ok", False, "Is this fine to post today? Yes/No"),
    ("sensitive", False, "Discipline, privacy, health, anything delicate? Yes/No"),
    ("consent_ok", False, "Are all students shown cleared for photo release?"),
)

REQUIRED_INTAKE_FIELDS = tuple(name for name, required, _ in INTAKE_FIELDS if required)

# Words in a description that force a human read before anything is drafted.
SENSITIVE_SIGNALS: tuple[str, ...] = (
    "discipline", "suspension", "injury", "injured", "hospital", "accident",
    "funeral", "death", "died", "illness", "diagnosis", "counseling",
    "police", "lawsuit", "custody", "iep", "504", "arrest", "protest",
)


def _slug(text: str, limit: int = 24) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned[:limit] or "asset"


@dataclass
class Asset:
    """One photograph or video clip that arrived in the content inbox."""

    asset_id: str
    kind: AssetKind
    event: str
    department: str
    contributor: str
    description: str
    captured_at: date
    filename: str = ""
    subjects: tuple[str, ...] = ()
    possible_story: str = ""
    orientation: Orientation = Orientation.VERTICAL
    duration_s: float | None = None
    consent_ok: bool = True
    sensitive: bool = False
    publish_now_ok: bool = True
    status: Status = Status.RAW
    tags: tuple[str, ...] = ()
    history: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind is AssetKind.VIDEO and self.duration_s is None:
            self.duration_s = 0.0
        if not self.sensitive and self.flags_sensitive_language():
            self.sensitive = True

    # -- text signals -------------------------------------------------------

    @property
    def searchable_text(self) -> str:
        return " ".join(
            [self.event, self.department, self.description, self.possible_story,
             " ".join(self.subjects), " ".join(self.tags)]
        )

    def flags_sensitive_language(self) -> bool:
        lowered = self.searchable_text.lower()
        return any(signal in lowered for signal in SENSITIVE_SIGNALS)

    # -- lifecycle ----------------------------------------------------------

    def advance(self, target: Status, note: str = "") -> "Asset":
        if not can_transition(self.status, target):
            allowed = ", ".join(s.value for s in TRANSITIONS[self.status]) or "nothing"
            raise TransitionError(
                f"{self.asset_id}: {self.status.value} -> {target.value} is not a "
                f"legal transition (allowed: {allowed})"
            )
        stamp = f"{self.status.value} -> {target.value}"
        self.history.append(f"{stamp}: {note}" if note else stamp)
        self.status = target
        return self

    @property
    def resolved(self) -> bool:
        """True once the asset can no longer be forgotten in a folder."""
        return self.status in (
            Status.CONTENT_OPPORTUNITY, Status.DRAFTED, Status.APPROVED,
            Status.SCHEDULED, Status.PUBLISHED, Status.MEASURED,
            Status.LIBRARY, Status.REJECTED,
        )

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["kind"] = self.kind.value
        data["orientation"] = self.orientation.value
        data["status"] = self.status.value
        data["captured_at"] = self.captured_at.isoformat()
        data["subjects"] = list(self.subjects)
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Asset":
        payload = dict(data)
        payload["kind"] = AssetKind(payload["kind"])
        payload["orientation"] = Orientation(payload.get("orientation", "vertical"))
        payload["status"] = Status(payload.get("status", "RAW"))
        payload["captured_at"] = _coerce_date(payload["captured_at"])
        payload["subjects"] = tuple(payload.get("subjects") or ())
        payload["tags"] = tuple(payload.get("tags") or ())
        payload["history"] = list(payload.get("history") or ())
        return cls(**payload)


class IntakeError(ValueError):
    """The upload form did not carry enough to work with."""


def _coerce_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise IntakeError(f"cannot read a date from {value!r}")


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"y", "yes", "true", "1", "ok"}


def from_intake(payload: dict[str, Any], *, asset_id: str = "") -> Asset:
    """Build an Asset from one phone-upload form submission.

    Missing optional fields are filled in rather than bounced back at the
    teacher who sent it. Only the four required fields can fail.
    """
    missing = [f for f in REQUIRED_INTAKE_FIELDS if not str(payload.get(f, "")).strip()]
    if missing:
        raise IntakeError(f"intake is missing required field(s): {', '.join(missing)}")

    captured = _coerce_date(payload.get("captured_at") or date.today())
    filename = str(payload.get("filename", ""))
    kind_raw = payload.get("kind")
    if kind_raw:
        kind = AssetKind(str(kind_raw).lower())
    else:
        kind = AssetKind.VIDEO if _looks_like_video(filename) else AssetKind.PHOTO

    subjects = payload.get("subjects") or ()
    if isinstance(subjects, str):
        subjects = tuple(s.strip() for s in subjects.split(",") if s.strip())

    generated_id = asset_id or "{}-{}-{}".format(
        captured.isoformat(), _slug(payload["event"]), _slug(filename or payload["contributor"], 10)
    )

    return Asset(
        asset_id=generated_id,
        kind=kind,
        event=str(payload["event"]).strip(),
        department=str(payload["department"]).strip(),
        contributor=str(payload["contributor"]).strip(),
        description=str(payload["description"]).strip(),
        captured_at=captured,
        filename=filename,
        subjects=tuple(subjects),
        possible_story=str(payload.get("possible_story", "")).strip(),
        orientation=Orientation(str(payload.get("orientation", "vertical")).lower()),
        duration_s=_coerce_float(payload.get("duration_s")),
        consent_ok=_coerce_bool(payload.get("consent_ok"), True),
        sensitive=_coerce_bool(payload.get("sensitive"), False),
        publish_now_ok=_coerce_bool(payload.get("publish_now_ok"), True),
        tags=tuple(payload.get("tags") or ()),
    )


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".hevc", ".avi", ".webm")


def _looks_like_video(filename: str) -> bool:
    return filename.lower().endswith(VIDEO_EXTENSIONS)


def unresolved(assets: Iterable[Asset]) -> list[Asset]:
    """Assets still sitting in the inbox with no decision made about them."""
    return [a for a in assets if not a.resolved]
