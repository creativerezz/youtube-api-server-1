"""
AI-powered video analysis and chat endpoints.

These endpoints require authentication when CLERK_AUTH_ENABLED is true.
"""
import logging
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field  # pyright: ignore[reportMissingImports]

from fastapi import APIRouter, Query, HTTPException, Request, Depends  # pyright: ignore[reportMissingImports]
from slowapi import Limiter  # pyright: ignore[reportMissingImports]
from slowapi.util import get_remote_address  # pyright: ignore[reportMissingImports]

from app.utils.youtube_tools import YouTubeTools
from app.utils.llm_service import get_llm_service
from app.core.config import settings
from app.core.auth import ClerkUser, get_current_user, get_optional_user

logger = logging.getLogger(__name__)

# Rate limiter (more restrictive for AI endpoints)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(
    prefix="/youtube/ai",
    tags=["ai"],
    responses={404: {"description": "Not found"}},
)

# Rate limit for AI endpoints (more restrictive)
ai_rate_limit = f"{settings.RATE_LIMIT_REQUESTS // 5}/{settings.RATE_LIMIT_WINDOW}"


def conditional_rate_limit(limit_string: str):
    """Apply rate limiting only if enabled in settings."""
    def decorator(func):
        if settings.RATE_LIMIT_ENABLED:
            return limiter.limit(limit_string)(func)
        return func
    return decorator


# Pydantic models for requests
class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    video: str = Field(..., description="YouTube video URL or ID")
    messages: List[ChatMessage] = Field(..., description="Chat message history")
    languages: Optional[List[str]] = Field(None, description="Caption language preferences")


class AnalyzeRequest(BaseModel):
    video: str = Field(..., description="YouTube video URL or ID")
    analysis_type: str = Field(
        "summary",
        description="Type of analysis: summary, patterns, insights, key_points, questions, action_items, topics"
    )
    custom_prompt: Optional[str] = Field(None, description="Custom prompt to use instead of built-in")
    languages: Optional[List[str]] = Field(None, description="Caption language preferences")


@router.get(
    "/status",
    summary="Check AI service status",
    response_description="AI service availability status",
)
async def ai_status() -> Dict[str, Any]:
    """Check if the AI/LLM service is configured and available."""
    llm_service = get_llm_service()
    return {
        "available": llm_service.is_available,
        "provider": settings.LLM_PROVIDER if llm_service.is_available else None,
        "analysis_types": [
            "summary", "patterns", "insights", "key_points",
            "questions", "action_items", "topics"
        ],
    }


@router.get(
    "/analyze",
    summary="Analyze video content",
    response_description="AI-generated analysis of the video",
)
@conditional_rate_limit(ai_rate_limit)
async def analyze_video_get(
    request: Request,
    video: str = Query(..., description="YouTube video URL or ID"),
    type: str = Query("summary", description="Analysis type: summary, patterns, insights, key_points, questions, action_items, topics"),
    languages: Optional[List[str]] = Query(None, description="Caption language preferences"),
    user: ClerkUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Analyze a YouTube video's content using AI.

    Available analysis types:
    - **summary**: Concise summary with main points and takeaways
    - **patterns**: Recurring themes, patterns, and structural elements
    - **insights**: Non-obvious observations and actionable insights
    - **key_points**: Main arguments, supporting points, and conclusions
    - **questions**: Questions raised (explicit and implicit)
    - **action_items**: Actionable recommendations and advice
    - **topics**: Topic outline and categorization
    """
    llm_service = get_llm_service()

    if not llm_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured. Please set LLM_PROVIDER and API key."
        )

    try:
        # Get video ID
        video_id = YouTubeTools.get_youtube_video_id(video)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL/ID")

        # Fetch transcript
        captions = await YouTubeTools.get_video_captions(video_id, languages)

        if not captions or captions == "No captions found for video":
            raise HTTPException(
                status_code=404,
                detail="No captions available for this video"
            )

        # Get video metadata for context
        try:
            metadata = await YouTubeTools.get_video_data(video_id)
            video_title = metadata.get("title", "")
        except Exception:
            video_title = ""

        # Perform analysis
        result = await llm_service.analyze(
            transcript=captions,
            analysis_type=type,
        )

        return {
            "video_id": video_id,
            "video_title": video_title,
            **result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@router.post(
    "/analyze",
    summary="Analyze video content (POST)",
    response_description="AI-generated analysis of the video",
)
@conditional_rate_limit(ai_rate_limit)
async def analyze_video_post(
    request: Request,
    body: AnalyzeRequest,
    user: ClerkUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Analyze a YouTube video's content using AI (POST version with custom prompt support).
    """
    llm_service = get_llm_service()

    if not llm_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured. Please set LLM_PROVIDER and API key."
        )

    try:
        video_id = YouTubeTools.get_youtube_video_id(body.video)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL/ID")

        captions = await YouTubeTools.get_video_captions(video_id, body.languages)

        if not captions or captions == "No captions found for video":
            raise HTTPException(
                status_code=404,
                detail="No captions available for this video"
            )

        try:
            metadata = await YouTubeTools.get_video_data(video_id)
            video_title = metadata.get("title", "")
        except Exception:
            video_title = ""

        result = await llm_service.analyze(
            transcript=captions,
            analysis_type=body.analysis_type,
            custom_prompt=body.custom_prompt,
        )

        return {
            "video_id": video_id,
            "video_title": video_title,
            **result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


@router.post(
    "/chat",
    summary="Chat about video content",
    response_description="AI response about the video",
)
@conditional_rate_limit(ai_rate_limit)
async def chat_with_video(
    request: Request,
    body: ChatRequest,
    user: ClerkUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Have a conversation about a YouTube video's content.

    Send the video ID/URL and a list of messages (conversation history).
    The AI will respond based on the video's transcript.
    """
    llm_service = get_llm_service()

    if not llm_service.is_available:
        raise HTTPException(
            status_code=503,
            detail="AI service is not configured. Please set LLM_PROVIDER and API key."
        )

    try:
        video_id = YouTubeTools.get_youtube_video_id(body.video)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL/ID")

        if not body.messages:
            raise HTTPException(status_code=400, detail="No messages provided")

        # Fetch transcript
        captions = await YouTubeTools.get_video_captions(video_id, body.languages)

        if not captions or captions == "No captions found for video":
            raise HTTPException(
                status_code=404,
                detail="No captions available for this video"
            )

        # Get video metadata
        try:
            metadata = await YouTubeTools.get_video_data(video_id)
            video_title = metadata.get("title", "")
        except Exception:
            video_title = ""

        # Format messages
        messages = [{"role": m.role, "content": m.content} for m in body.messages]

        # Get response
        response = await llm_service.chat_with_video(
            transcript=captions,
            messages=messages,
            video_title=video_title,
        )

        return {
            "video_id": video_id,
            "video_title": video_title,
            "response": response,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Chat failed: {str(e)}"
        )


@router.get(
    "/quick/{analysis_type}",
    summary="Quick analysis shortcut",
    response_description="Quick AI analysis of the video",
)
@conditional_rate_limit(ai_rate_limit)
async def quick_analysis(
    request: Request,
    analysis_type: str,
    video: str = Query(..., description="YouTube video URL or ID"),
    languages: Optional[List[str]] = Query(None, description="Caption language preferences"),
    user: ClerkUser = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Quick shortcut for common analysis types.

    Path parameter is the analysis type (summary, patterns, insights, etc.)
    """
    return await analyze_video_get(
        request=request,
        video=video,
        type=analysis_type,
        languages=languages,
        user=user,
    )
