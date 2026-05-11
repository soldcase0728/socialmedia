from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx

from settings import get_settings

from ..models import Creator, FollowResult, Platform, Post


class ScraperError(Exception):
    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


class BaseScraper(ABC):
    platform: Platform

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            headers={"User-Agent": settings.user_agent},
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> "BaseScraper":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    @abstractmethod
    async def get_creator(self, handle: str) -> Creator: ...

    @abstractmethod
    async def get_posts(self, handle: str, limit: int = 20) -> list[Post]: ...

    @abstractmethod
    async def follow_creator(self, handle: str, *, notify: bool = False) -> FollowResult: ...

    def _build_follow_result(
        self,
        handle: str,
        *,
        followed: bool,
        already_following: bool = False,
        notifications_enabled: bool = False,
        message: str | None = None,
    ) -> FollowResult:
        return FollowResult(
            platform=self.platform,
            handle=handle.lstrip("@"),
            followed=followed,
            already_following=already_following,
            notifications_enabled=notifications_enabled,
            followed_at=datetime.now(timezone.utc),
            message=message,
        )
