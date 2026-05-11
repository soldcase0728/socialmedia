from fastapi import APIRouter, Query

from ..models import Creator, FollowRequest, FollowResult, Post
from ..scrapers import TikTokScraper
from ._common import do_follow, fetch_creator, fetch_posts

router = APIRouter(prefix="/tiktok", tags=["tiktok"])


@router.get("/creators/{handle}", response_model=Creator)
async def get_creator(handle: str) -> Creator:
    return await fetch_creator(TikTokScraper, handle)


@router.get("/creators/{handle}/posts", response_model=list[Post])
async def get_posts(
    handle: str, limit: int = Query(default=20, ge=1, le=50)
) -> list[Post]:
    return await fetch_posts(TikTokScraper, handle, limit)


@router.post("/creators/{handle}/follow", response_model=FollowResult)
async def follow_creator(handle: str, body: FollowRequest) -> FollowResult:
    return await do_follow(TikTokScraper, handle, body)
