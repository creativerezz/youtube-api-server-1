"""
YouTube Data API v3 routes for search and channel endpoints.

These endpoints proxy requests to the YouTube Data API, allowing
the frontend to avoid quota issues by using a centralized API key.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(
    prefix="/youtube/data",
    tags=["youtube-data-api"],
    responses={404: {"description": "Not found"}},
)

# Build rate limit string from settings
rate_limit = f"{settings.RATE_LIMIT_REQUESTS}/{settings.RATE_LIMIT_WINDOW}"

YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3"


def conditional_rate_limit(limit_string: str):
    """Apply rate limiting only if enabled in settings."""
    def decorator(func):
        if settings.RATE_LIMIT_ENABLED:
            return limiter.limit(limit_string)(func)
        return func
    return decorator


def get_api_key() -> str:
    """Get YouTube API key, raising error if not configured."""
    if not settings.YOUTUBE_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="YouTube API key not configured. Please set YOUTUBE_API_KEY environment variable."
        )
    return settings.YOUTUBE_API_KEY


@router.get(
    "/search",
    summary="Search YouTube videos",
    response_description="List of videos matching the search query.",
)
@conditional_rate_limit(rate_limit)
async def search_videos(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    max_results: int = Query(12, ge=1, le=50, description="Maximum number of results"),
) -> Dict[str, Any]:
    """
    Search for YouTube videos using the YouTube Data API v3.

    Returns video ID, title, thumbnail, channel name, and publish date.
    """
    api_key = get_api_key()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{YOUTUBE_API_URL}/search",
                params={
                    "part": "snippet",
                    "q": q,
                    "type": "video",
                    "maxResults": max_results,
                    "key": api_key,
                },
            )

            if response.status_code == 403:
                logger.warning(f"YouTube API 403 error: {response.text}")
                raise HTTPException(
                    status_code=403,
                    detail="YouTube API quota exceeded or access forbidden."
                )

            if not response.is_success:
                logger.error(f"YouTube API error: {response.status_code} - {response.text}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"YouTube API request failed: {response.status_code}"
                )

            data = response.json()

            videos = [
                {
                    "id": item["id"]["videoId"],
                    "title": item["snippet"]["title"],
                    "thumbnail": item["snippet"]["thumbnails"]["medium"]["url"],
                    "channelTitle": item["snippet"]["channelTitle"],
                    "publishedAt": item["snippet"]["publishedAt"],
                }
                for item in data.get("items", [])
                if item.get("id", {}).get("videoId")
            ]

            return {"videos": videos}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in search_videos: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search videos: {str(e)}"
        )


@router.get(
    "/channel/{channel_id}",
    summary="Get channel info and videos",
    response_description="Channel information and recent uploads.",
)
@conditional_rate_limit(rate_limit)
async def get_channel(
    request: Request,
    channel_id: str,
    max_results: int = Query(20, ge=1, le=50, description="Maximum number of videos to return"),
) -> Dict[str, Any]:
    """
    Get YouTube channel information and recent uploads.

    Returns channel title, description, thumbnail, subscriber count,
    and a list of recent video uploads with durations.
    """
    api_key = get_api_key()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Fetch channel info (including contentDetails for uploads playlist)
            channel_response = await client.get(
                f"{YOUTUBE_API_URL}/channels",
                params={
                    "part": "snippet,statistics,contentDetails",
                    "id": channel_id,
                    "key": api_key,
                },
            )

            if channel_response.status_code == 403:
                logger.warning(f"YouTube API 403 error: {channel_response.text}")
                raise HTTPException(
                    status_code=403,
                    detail="YouTube API quota exceeded or access forbidden."
                )

            if not channel_response.is_success:
                logger.error(f"YouTube Channel API error: {channel_response.status_code}")
                raise HTTPException(
                    status_code=channel_response.status_code,
                    detail=f"Failed to fetch channel information: {channel_response.status_code}"
                )

            channel_data = channel_response.json()

            if not channel_data.get("items"):
                raise HTTPException(status_code=404, detail="Channel not found")

            channel = channel_data["items"][0]
            channel_info = {
                "title": channel["snippet"]["title"],
                "description": channel["snippet"]["description"],
                "thumbnail": channel["snippet"]["thumbnails"]["medium"]["url"],
                "subscriberCount": format_subscriber_count(
                    int(channel["statistics"].get("subscriberCount", 0))
                ),
            }

            # Try to get uploads playlist ID from channel contentDetails
            uploads_playlist_id = None
            if "contentDetails" in channel and "relatedPlaylists" in channel["contentDetails"]:
                uploads_playlist_id = channel["contentDetails"]["relatedPlaylists"].get("uploads")

            # Fetch recent uploads - prefer using uploads playlist if available
            if uploads_playlist_id:
                logger.info(f"Using uploads playlist {uploads_playlist_id} for channel {channel_id}")
                uploads_response = await client.get(
                    f"{YOUTUBE_API_URL}/playlistItems",
                    params={
                        "part": "snippet",
                        "playlistId": uploads_playlist_id,
                        "maxResults": max_results,
                        "key": api_key,
                    },
                )
            else:
                # Fallback to search API if uploads playlist not available
                logger.info(f"Using search API fallback for channel {channel_id}")
                uploads_response = await client.get(
                    f"{YOUTUBE_API_URL}/search",
                    params={
                        "part": "snippet",
                        "channelId": channel_id,
                        "order": "date",
                        "type": "video",
                        "maxResults": max_results,
                        "key": api_key,
                    },
                )

            if uploads_response.status_code == 403:
                logger.warning(f"YouTube uploads API 403 error: {uploads_response.text}")
                raise HTTPException(
                    status_code=403,
                    detail="YouTube API quota exceeded or access forbidden."
                )

            if not uploads_response.is_success:
                error_text = uploads_response.text
                logger.error(
                    f"YouTube uploads API error: {uploads_response.status_code} - {error_text}"
                )
                raise HTTPException(
                    status_code=uploads_response.status_code,
                    detail=f"Failed to fetch channel videos: {uploads_response.status_code}. {error_text[:200]}"
                )

            uploads_data = uploads_response.json()
            
            # Check if we got any items
            items = uploads_data.get("items", [])
            if not items:
                logger.info(f"No videos found for channel {channel_id}")
                return {"channelInfo": channel_info, "videos": []}
            
            # Extract video IDs based on whether we used playlist or search API
            video_ids = []
            if uploads_playlist_id:
                # From playlistItems API: video ID is in item.snippet.resourceId.videoId
                video_ids = [
                    item["snippet"]["resourceId"]["videoId"]
                    for item in items
                    if item.get("snippet", {}).get("resourceId", {}).get("videoId")
                ]
            else:
                # From search API: video ID is in item.id.videoId
                video_ids = [
                    item["id"]["videoId"]
                    for item in items
                    if item.get("id", {}).get("videoId")
                ]

            if not video_ids:
                logger.warning(f"No valid video IDs extracted from uploads for channel {channel_id}")
                return {"channelInfo": channel_info, "videos": []}

            # Fetch video details for duration
            videos = []
            details_response = await client.get(
                f"{YOUTUBE_API_URL}/videos",
                params={
                    "part": "contentDetails",
                    "id": ",".join(video_ids),
                    "key": api_key,
                },
            )

            durations = {}
            if details_response.is_success:
                details_data = details_response.json()
                for item in details_data.get("items", []):
                    durations[item["id"]] = item["contentDetails"]["duration"]
            else:
                logger.warning(
                    f"Failed to fetch video details: {details_response.status_code}. "
                    "Continuing without durations."
                )

            # Combine uploads with durations
            for item in items:
                # Extract video ID based on API type
                if uploads_playlist_id:
                    video_id = item.get("snippet", {}).get("resourceId", {}).get("videoId")
                else:
                    video_id = item.get("id", {}).get("videoId")
                
                if video_id:
                    try:
                        snippet = item["snippet"]
                        videos.append({
                            "id": video_id,
                            "title": snippet["title"],
                            "thumbnail": snippet["thumbnails"]["medium"]["url"],
                            "publishedAt": format_date(snippet["publishedAt"]),
                            "duration": durations.get(video_id, "PT0S"),
                        })
                    except KeyError as e:
                        logger.warning(f"Missing field in video data: {e}. Skipping video {video_id}")
                        continue

            logger.info(f"Successfully fetched {len(videos)} videos for channel {channel_id}")
            return {"channelInfo": channel_info, "videos": videos}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_channel: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch channel data: {str(e)}"
        )


def format_subscriber_count(count: int) -> str:
    """Format subscriber count with K/M suffix."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def format_date(iso_date: str) -> str:
    """Format ISO date to readable format."""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y")
    except Exception:
        return iso_date
