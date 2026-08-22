"""Loading and saving the engine's state.

Shared by the interactive CLI and the scheduled runner so both read exactly the
same files. Point BRANDOPS_DATA at a synced SharePoint or OneDrive folder and
the whole team -- and the morning job -- share one state.
"""

from __future__ import annotations

from typing import Any, Sequence

from . import store
from .approval import ApprovalQueue
from .assets import Asset
from .measurement import PostResult

ASSETS_KEY = "assets"
RESULTS_KEY = "results"
PUBLISHED_KEY = "published"
QUEUE_KEY = "queue"


def load_assets() -> list[Asset]:
    return [Asset.from_dict(a) for a in store.load(ASSETS_KEY, {}).get("assets", [])]


def save_assets(assets: Sequence[Asset]) -> None:
    store.save(ASSETS_KEY, {"assets": [a.to_dict() for a in assets]})


def load_results() -> list[PostResult]:
    return [PostResult.from_dict(r) for r in store.load(RESULTS_KEY, {}).get("results", [])]


def append_result(result: PostResult) -> None:
    payload = store.load(RESULTS_KEY, {})
    payload.setdefault("results", []).append(result.to_dict())
    store.save(RESULTS_KEY, payload)


def load_published() -> list[dict[str, Any]]:
    return list(store.load(PUBLISHED_KEY, {}).get("records", []))


def append_published(record: dict[str, Any]) -> None:
    payload = store.load(PUBLISHED_KEY, {})
    payload.setdefault("records", []).append(record)
    store.save(PUBLISHED_KEY, payload)


def load_queue() -> ApprovalQueue:
    return ApprovalQueue.from_dict(store.load(QUEUE_KEY, {}))


def save_queue(queue: ApprovalQueue) -> None:
    store.save(QUEUE_KEY, queue.to_dict())
