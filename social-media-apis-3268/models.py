from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Platform = Literal["twitter", "instagram", "tiktok", "youtube"]


class Creator(BaseModel):
    platform: Platform
    handle: str
    display_name: str | None = None
    bio: str | None = None
    follower_count: int | None = None
    following_count: int | None = None
    post_count: int | None = None
    verified: bool = False
    profile_url: str | None = None
    avatar_url: str | None = None


class Post(BaseModel):
    platform: Platform
    id: str
    author_handle: str
    text: str | None = None
    media_urls: list[str] = Field(default_factory=list)
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    view_count: int | None = None
    posted_at: datetime | None = None
    url: str | None = None


class FollowRequest(BaseModel):
    handle: str = Field(..., min_length=1, description="Creator handle without @")
    notify: bool = Field(default=False, description="Enable notifications for posts")


class FollowResult(BaseModel):
    platform: Platform
    handle: str
    followed: bool
    already_following: bool = False
    notifications_enabled: bool = False
    followed_at: datetime
    message: str | None = None


class ErrorResponse(BaseModel):
    detail: str
    platform: Platform | None = None
