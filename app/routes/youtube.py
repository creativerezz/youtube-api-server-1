import asyncio
import logging
import re
from typing import List, Optional, Dict, Any
from functools import wraps

from fastapi import APIRouter, Query, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.utils.youtube_tools import YouTubeTools
from app.utils.transcript_cache import get_cache
from app.models.youtube import VideoData
from app.core.config import settings

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(
    prefix="/youtube",
    tags=["youtube"],
    responses={404: {"description": "Not found"}},
)

# Build rate limit string from settings
rate_limit = f"{settings.RATE_LIMIT_REQUESTS}/{settings.RATE_LIMIT_WINDOW}"


def conditional_rate_limit(limit_string: str):
    """Apply rate limiting only if enabled in settings."""
    def decorator(func):
        if settings.RATE_LIMIT_ENABLED:
            return limiter.limit(limit_string)(func)
        return func
    return decorator


@router.get(
    "/metadata",
    summary="Get video metadata",
    response_description="Clean YouTube oEmbed metadata for the requested video.",
    response_model=VideoData,
)
@conditional_rate_limit(rate_limit)
async def get_video_metadata(
    request: Request,
    video: str = Query(
        ..., description="YouTube video URL or ID", examples=["https://youtu.be/dQw4w9WgXcQ", "dQw4w9WgXcQ"]
    ),
) -> VideoData:
    """Return basic video information such as *title*, *author* and *thumbnail*."""
    try:
        data = await YouTubeTools.get_video_data(video)
        return VideoData(**data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_video_metadata: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve video metadata: {str(e)}"
        )


@router.get(
    "/captions",
    summary="Get plain-text captions",
    response_description="Concatenated caption text (one large string) for the requested video.",
)
@conditional_rate_limit(rate_limit)
async def get_video_captions(
    request: Request,
    video: str = Query(..., description="YouTube video URL or ID"),
    languages: Optional[List[str]] = Query(None, description="Preferred caption languages (ISO 639-1 codes). Default: ['en']"),
    translate_to: Optional[str] = Query(None, description="Translate captions to this language (ISO 639-1 code, e.g., 'en'). Auto-translation is attempted if direct fetch fails."),
) -> str:
    """Return plain-text captions for the requested video (English by default).

    If the video doesn't have captions in the requested language, the API will
    automatically attempt to translate from an available language.
    Use `translate_to` to explicitly request translation.
    """
    try:
        return await YouTubeTools.get_video_captions(video, languages, translate_to)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_video_captions: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve video captions: {str(e)}"
        )


@router.get(
    "/timestamps",
    summary="Get caption timestamps",
    response_description="A list of caption lines with starting timestamps.",
)
@conditional_rate_limit(rate_limit)
async def get_video_timestamps(
    request: Request,
    video: str = Query(..., description="YouTube video URL or ID"),
    languages: Optional[List[str]] = Query(None, description="Preferred caption languages (ISO 639-1 codes). Default: ['en']"),
    translate_to: Optional[str] = Query(None, description="Translate captions to this language (ISO 639-1 code, e.g., 'en'). Auto-translation is attempted if direct fetch fails."),
) -> List[str]:
    """Return caption text with starting timestamps (English by default).

    If the video doesn't have captions in the requested language, the API will
    automatically attempt to translate from an available language.
    """
    try:
        return await YouTubeTools.get_video_timestamps(video, languages, translate_to)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_video_timestamps: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve video timestamps: {str(e)}"
        )


@router.get(
    "/captions/batch",
    summary="Get captions for multiple videos",
    response_description="Dictionary mapping video IDs to their captions.",
)
@conditional_rate_limit(rate_limit)
async def get_batch_captions(
    request: Request,
    videos: str = Query(..., description="Comma-separated list of video URLs or IDs (max 10)"),
    languages: Optional[List[str]] = Query(None, description="Preferred caption languages. Default: ['en']"),
    translate_to: Optional[str] = Query(None, description="Translate captions to this language. Auto-translation is attempted if direct fetch fails."),
) -> Dict[str, Any]:
    """
    Fetch captions for multiple videos in parallel.

    Returns a dictionary with video IDs as keys and their captions (or error message) as values.
    Limited to 10 videos per request. Auto-translation is attempted if direct fetch fails.
    """
    try:
        video_list = [v.strip() for v in videos.split(",") if v.strip()]

        if len(video_list) > 10:
            raise HTTPException(status_code=400, detail="Maximum 10 videos per batch request")

        if not video_list:
            raise HTTPException(status_code=400, detail="No valid video IDs provided")

        # Extract video IDs
        video_ids = []
        for v in video_list:
            vid = YouTubeTools.get_youtube_video_id(v)
            if vid:
                video_ids.append(vid)
            else:
                video_ids.append(None)

        # Fetch all captions in parallel
        async def fetch_caption(video_id: Optional[str]) -> tuple[str, Any]:
            if video_id is None:
                return ("invalid", {"error": "Invalid video URL/ID"})
            try:
                caption = await YouTubeTools.get_video_captions(video_id, languages, translate_to)
                return (video_id, {"caption": caption})
            except Exception as e:
                return (video_id, {"error": str(e)})

        results = await asyncio.gather(*[fetch_caption(vid) for vid in video_ids])

        return {
            "results": {vid: data for vid, data in results},
            "total": len(video_list),
            "successful": sum(1 for _, data in results if "caption" in data),
            "failed": sum(1 for _, data in results if "error" in data),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_batch_captions: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve batch captions: {str(e)}"
        )


@router.get(
    "/search",
    summary="Search within transcript",
    response_description="List of matching transcript segments with timestamps.",
)
@conditional_rate_limit(rate_limit)
async def search_transcript(
    request: Request,
    video: str = Query(..., description="YouTube video URL or ID"),
    query: str = Query(..., min_length=1, description="Search query (case-insensitive)"),
    languages: Optional[List[str]] = Query(None, description="Preferred caption languages. Default: ['en']"),
    translate_to: Optional[str] = Query(None, description="Translate captions before searching. Auto-translation is attempted if direct fetch fails."),
    context_lines: int = Query(1, ge=0, le=5, description="Number of context lines before/after match"),
) -> Dict[str, Any]:
    """
    Search for keywords within a video's transcript.

    Returns all segments containing the search query, with timestamps
    and optional context lines before and after each match.
    """
    try:
        video_id = YouTubeTools.get_youtube_video_id(video)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL/ID")

        # Get raw transcript
        transcript = await YouTubeTools._fetch_transcript(video_id, languages, translate_to)

        if not transcript:
            return {"video_id": video_id, "query": query, "matches": [], "total_matches": 0}

        # Search through transcript
        matches = []
        query_lower = query.lower()

        for i, segment in enumerate(transcript):
            text = segment.text if hasattr(segment, 'text') else segment.get('text', '')
            if query_lower in text.lower():
                start = segment.start if hasattr(segment, 'start') else segment.get('start', 0)
                minutes, seconds = divmod(int(start), 60)

                # Get context
                context_before = []
                context_after = []

                if context_lines > 0:
                    for j in range(max(0, i - context_lines), i):
                        ctx_seg = transcript[j]
                        ctx_text = ctx_seg.text if hasattr(ctx_seg, 'text') else ctx_seg.get('text', '')
                        context_before.append(ctx_text)

                    for j in range(i + 1, min(len(transcript), i + 1 + context_lines)):
                        ctx_seg = transcript[j]
                        ctx_text = ctx_seg.text if hasattr(ctx_seg, 'text') else ctx_seg.get('text', '')
                        context_after.append(ctx_text)

                match_info = {
                    "timestamp": f"{minutes}:{seconds:02d}",
                    "start_seconds": start,
                    "text": text,
                    "index": i,
                }

                if context_lines > 0:
                    match_info["context_before"] = context_before
                    match_info["context_after"] = context_after

                matches.append(match_info)

        return {
            "video_id": video_id,
            "query": query,
            "matches": matches,
            "total_matches": len(matches),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in search_transcript: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search transcript: {str(e)}"
        )


@router.get(
    "/chapters",
    summary="Detect chapters in transcript",
    response_description="List of detected chapter boundaries with timestamps.",
)
@conditional_rate_limit(rate_limit)
async def detect_chapters(
    request: Request,
    video: str = Query(..., description="YouTube video URL or ID"),
    languages: Optional[List[str]] = Query(None, description="Preferred caption languages. Default: ['en']"),
    translate_to: Optional[str] = Query(None, description="Translate captions before detecting chapters. Auto-translation is attempted if direct fetch fails."),
    min_gap_seconds: float = Query(3.0, ge=1.0, le=30.0, description="Minimum gap between segments to detect chapter break"),
    min_segments: int = Query(5, ge=3, le=50, description="Minimum segments per chapter"),
) -> Dict[str, Any]:
    """
    Detect logical chapter boundaries in a video's transcript.

    Uses silence gaps and topic changes to identify potential chapter breaks.
    This is a heuristic-based detection and may not be perfect.
    """
    try:
        video_id = YouTubeTools.get_youtube_video_id(video)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL/ID")

        # Get raw transcript
        transcript = await YouTubeTools._fetch_transcript(video_id, languages, translate_to)

        if not transcript:
            return {"video_id": video_id, "chapters": [], "total_chapters": 0}

        chapters = []
        current_chapter_start = 0
        current_chapter_segments = []

        for i, segment in enumerate(transcript):
            start = segment.start if hasattr(segment, 'start') else segment.get('start', 0)
            duration = segment.duration if hasattr(segment, 'duration') else segment.get('duration', 0)
            text = segment.text if hasattr(segment, 'text') else segment.get('text', '')

            current_chapter_segments.append(text)

            # Check for chapter break conditions
            if i < len(transcript) - 1:
                next_segment = transcript[i + 1]
                next_start = next_segment.start if hasattr(next_segment, 'start') else next_segment.get('start', 0)
                gap = next_start - (start + duration)

                # Detect chapter break based on gap
                is_chapter_break = gap >= min_gap_seconds and len(current_chapter_segments) >= min_segments

                if is_chapter_break:
                    # Create chapter
                    chapter_start_time = transcript[current_chapter_start].start if hasattr(transcript[current_chapter_start], 'start') else transcript[current_chapter_start].get('start', 0)
                    minutes, seconds = divmod(int(chapter_start_time), 60)

                    # Get first meaningful text as chapter title (first 50 chars)
                    first_text = current_chapter_segments[0] if current_chapter_segments else ""
                    chapter_title = re.sub(r'\s+', ' ', first_text).strip()[:50]
                    if len(first_text) > 50:
                        chapter_title += "..."

                    chapters.append({
                        "chapter_number": len(chapters) + 1,
                        "timestamp": f"{minutes}:{seconds:02d}",
                        "start_seconds": chapter_start_time,
                        "segment_count": len(current_chapter_segments),
                        "preview": chapter_title,
                    })

                    # Reset for next chapter
                    current_chapter_start = i + 1
                    current_chapter_segments = []

        # Add final chapter
        if current_chapter_segments:
            chapter_start_time = transcript[current_chapter_start].start if hasattr(transcript[current_chapter_start], 'start') else transcript[current_chapter_start].get('start', 0)
            minutes, seconds = divmod(int(chapter_start_time), 60)
            first_text = current_chapter_segments[0] if current_chapter_segments else ""
            chapter_title = re.sub(r'\s+', ' ', first_text).strip()[:50]
            if len(first_text) > 50:
                chapter_title += "..."

            chapters.append({
                "chapter_number": len(chapters) + 1,
                "timestamp": f"{minutes}:{seconds:02d}",
                "start_seconds": chapter_start_time,
                "segment_count": len(current_chapter_segments),
                "preview": chapter_title,
            })

        return {
            "video_id": video_id,
            "chapters": chapters,
            "total_chapters": len(chapters),
            "detection_params": {
                "min_gap_seconds": min_gap_seconds,
                "min_segments": min_segments,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in detect_chapters: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to detect chapters: {str(e)}"
        )


@router.get(
    "/cache/stats",
    summary="Get cache statistics",
    response_description="Current cache statistics including size and configuration.",
)
async def get_cache_stats() -> Dict[str, Any]:
    """Return cache statistics and configuration."""
    try:
        cache = get_cache()
        return {
            "enabled": cache.enabled,
            "backend": cache.backend_type,
            "size": cache.size(),
            "max_size": cache.max_size,
            "ttl_seconds": cache.ttl_seconds,
        }
    except Exception as e:
        logger.error(f"Unexpected error in get_cache_stats: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve cache statistics: {str(e)}"
        )


@router.delete(
    "/cache/clear",
    summary="Clear transcript cache",
    response_description="Clears all cached transcripts.",
)
async def clear_cache() -> Dict[str, Any]:
    """Clear all cached transcripts."""
    try:
        cache = get_cache()
        cache.clear()
        return {"message": "Cache cleared successfully", "size": cache.size()}
    except Exception as e:
        logger.error(f"Unexpected error in clear_cache: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear cache: {str(e)}"
        )


@router.get(
    "/performance/test",
    summary="Test transcript performance",
    response_description="Performance metrics for transcript fetching (cache miss vs cache hit).",
)
async def test_performance(
    video: str = Query(..., description="YouTube video URL or ID"),
    runs: int = Query(3, ge=2, le=10, description="Number of test runs (default: 3)"),
    languages: Optional[List[str]] = Query(None, description="Preferred caption languages. Default: ['en']"),
    translate_to: Optional[str] = Query(None, description="Translate captions to this language. Tests translation performance if provided."),
) -> Dict[str, Any]:
    """
    Test transcript fetching performance.

    Makes multiple requests to measure cache miss (first request) vs cache hit (subsequent requests) performance.
    Useful for benchmarking cache effectiveness.
    """
    try:
        import time

        video_id = YouTubeTools.get_youtube_video_id(video)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL/ID")

        normalized_languages = languages or ["en"]
        times: List[Optional[float]] = []
        errors: List[str] = []

        for i in range(runs):
            start_time = time.perf_counter()
            try:
                transcript = await YouTubeTools._fetch_transcript(video_id, normalized_languages, translate_to)
                elapsed = time.perf_counter() - start_time
                times.append(elapsed)
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                errors.append(str(e))
                times.append(None)

        if not times or all(t is None for t in times):
            raise HTTPException(
                status_code=500,
                detail=f"All requests failed. Errors: {', '.join(errors) if errors else 'Unknown error'}"
            )

        valid_times = [t for t in times if t is not None]

        cache_miss_time = valid_times[0] if valid_times else None
        cache_hit_times = valid_times[1:] if len(valid_times) > 1 else []

        result: Dict[str, Any] = {
            "video_id": video_id,
            "runs": runs,
            "successful_runs": len(valid_times),
            "cache_miss": {
                "time_seconds": cache_miss_time,
                "time_ms": cache_miss_time * 1000 if cache_miss_time else None,
            } if cache_miss_time else None,
            "cache_hits": {
                "count": len(cache_hit_times),
                "times_seconds": cache_hit_times,
                "times_ms": [t * 1000 for t in cache_hit_times],
                "avg_seconds": sum(cache_hit_times) / len(cache_hit_times) if cache_hit_times else None,
                "avg_ms": (sum(cache_hit_times) / len(cache_hit_times) * 1000) if cache_hit_times else None,
                "min_seconds": min(cache_hit_times) if cache_hit_times else None,
                "max_seconds": max(cache_hit_times) if cache_hit_times else None,
            } if cache_hit_times else None,
            "speedup": cache_miss_time / (sum(cache_hit_times) / len(cache_hit_times)) if cache_miss_time and cache_hit_times else None,
        }

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in test_performance: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run performance test: {str(e)}"
        )
