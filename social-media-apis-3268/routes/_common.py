from __future__ import annotations

from typing import Awaitable, Callable, TypeVar

from fastapi import HTTPException

from ..models import Creator, FollowRequest, FollowResult, Post
from ..scrapers.base import BaseScraper, ScraperError

T = TypeVar("T")


async def with_scraper(
    factory: Callable[[], BaseScraper],
    op: Callable[[BaseScraper], Awaitable[T]],
) -> T:
    scraper = factory()
    try:
        return await op(scraper)
    except ScraperError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    finally:
        await scraper.aclose()


async def fetch_creator(factory: Callable[[], BaseScraper], handle: str) -> Creator:
    return await with_scraper(factory, lambda s: s.get_creator(handle))


async def fetch_posts(
    factory: Callable[[], BaseScraper], handle: str, limit: int
) -> list[Post]:
    return await with_scraper(factory, lambda s: s.get_posts(handle, limit=limit))


async def do_follow(
    factory: Callable[[], BaseScraper], handle: str, body: FollowRequest
) -> FollowResult:
    target = body.handle or handle
    return await with_scraper(
        factory, lambda s: s.follow_creator(target, notify=body.notify)
    )
