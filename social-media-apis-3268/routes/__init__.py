from .instagram import router as instagram_router
from .tiktok import router as tiktok_router
from .twitter import router as twitter_router
from .youtube import router as youtube_router

__all__ = [
    "instagram_router",
    "tiktok_router",
    "twitter_router",
    "youtube_router",
]
