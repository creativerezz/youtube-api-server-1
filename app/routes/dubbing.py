"""
ElevenLabs Dubbing API routes.

Provides endpoints for dubbing YouTube videos into different languages
using ElevenLabs' AI dubbing service.
"""

import logging
from typing import Optional
from enum import Enum

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from elevenlabs.client import ElevenLabs

from app.core.config import settings
from app.utils.youtube_tools import YouTubeTools

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dubbing", tags=["dubbing"])


# Supported languages for dubbing
class TargetLanguage(str, Enum):
    ENGLISH = "en"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    ITALIAN = "it"
    PORTUGUESE = "pt"
    POLISH = "pl"
    HINDI = "hi"
    JAPANESE = "ja"
    KOREAN = "ko"
    CHINESE = "zh"
    ARABIC = "ar"
    RUSSIAN = "ru"
    TURKISH = "tr"
    DUTCH = "nl"
    SWEDISH = "sv"
    INDONESIAN = "id"
    FILIPINO = "fil"
    TAMIL = "ta"
    UKRAINIAN = "uk"
    GREEK = "el"
    CZECH = "cs"
    FINNISH = "fi"
    CROATIAN = "hr"
    MALAY = "ms"
    SLOVAK = "sk"
    DANISH = "da"
    ROMANIAN = "ro"
    BULGARIAN = "bg"


class DubbingRequest(BaseModel):
    """Request model for creating a dubbing project."""
    video: str = Field(..., description="YouTube URL or video ID")
    target_lang: TargetLanguage = Field(..., description="Target language for dubbing")
    source_lang: Optional[str] = Field(default="auto", description="Source language (auto-detect by default)")
    num_speakers: Optional[int] = Field(default=0, description="Number of speakers (0 for auto-detect)")
    watermark: Optional[bool] = Field(default=False, description="Add watermark to output")
    start_time: Optional[int] = Field(default=None, description="Start time in seconds")
    end_time: Optional[int] = Field(default=None, description="End time in seconds")
    highest_resolution: Optional[bool] = Field(default=True, description="Use highest resolution")
    drop_background_audio: Optional[bool] = Field(default=False, description="Remove background audio")


class DubbingResponse(BaseModel):
    """Response model for dubbing creation."""
    dubbing_id: str
    expected_duration_sec: float
    video_id: str
    target_lang: str


class DubbingStatusResponse(BaseModel):
    """Response model for dubbing status."""
    dubbing_id: str
    name: Optional[str] = None
    status: str
    target_languages: list[str] = []
    error: Optional[str] = None


def get_elevenlabs_client() -> ElevenLabs:
    """Get ElevenLabs client instance."""
    if not settings.ELEVENLABS_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="ElevenLabs API key not configured. Set ELEVENLABS_API_KEY environment variable."
        )
    return ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)


@router.post("/create", response_model=DubbingResponse)
async def create_dubbing(request: DubbingRequest):
    """
    Create a dubbing project for a YouTube video.

    Submits a YouTube video to ElevenLabs for dubbing into the target language.
    Returns a dubbing_id that can be used to check status and retrieve the dubbed audio.

    **Note:** Dubbing is an async process and may take several minutes depending on video length.
    """
    # Extract video ID
    video_id = YouTubeTools.get_youtube_video_id(request.video)
    if not video_id:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL or video ID")

    # Construct YouTube URL for ElevenLabs
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"

    logger.info(f"Creating dubbing project for video {video_id} -> {request.target_lang.value}")

    try:
        client = get_elevenlabs_client()

        # Create dubbing project
        response = client.dubbing.dub_a_video_or_an_audio_file(
            source_url=youtube_url,
            target_lang=request.target_lang.value,
            source_lang=request.source_lang if request.source_lang != "auto" else None,
            num_speakers=request.num_speakers,
            watermark=request.watermark,
            start_time=request.start_time,
            end_time=request.end_time,
            highest_resolution=request.highest_resolution,
            drop_background_audio=request.drop_background_audio,
        )

        logger.info(f"Dubbing project created: {response.dubbing_id}")

        return DubbingResponse(
            dubbing_id=response.dubbing_id,
            expected_duration_sec=response.expected_duration_sec,
            video_id=video_id,
            target_lang=request.target_lang.value
        )

    except Exception as e:
        logger.error(f"Failed to create dubbing project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create dubbing project: {str(e)}")


@router.get("/create")
async def create_dubbing_get(
    video: str = Query(..., description="YouTube URL or video ID"),
    target_lang: TargetLanguage = Query(..., description="Target language for dubbing"),
    source_lang: Optional[str] = Query(default="auto", description="Source language"),
    num_speakers: Optional[int] = Query(default=0, description="Number of speakers"),
    watermark: Optional[bool] = Query(default=False, description="Add watermark"),
    start_time: Optional[int] = Query(default=None, description="Start time in seconds"),
    end_time: Optional[int] = Query(default=None, description="End time in seconds"),
    highest_resolution: Optional[bool] = Query(default=True, description="Use highest resolution"),
    drop_background_audio: Optional[bool] = Query(default=False, description="Remove background audio"),
):
    """
    Create a dubbing project via GET request (query parameters).

    Same as POST /create but accepts query parameters for easier testing.
    """
    request = DubbingRequest(
        video=video,
        target_lang=target_lang,
        source_lang=source_lang,
        num_speakers=num_speakers,
        watermark=watermark,
        start_time=start_time,
        end_time=end_time,
        highest_resolution=highest_resolution,
        drop_background_audio=drop_background_audio,
    )
    return await create_dubbing(request)


@router.get("/{dubbing_id}/status", response_model=DubbingStatusResponse)
async def get_dubbing_status(dubbing_id: str):
    """
    Get the status of a dubbing project.

    **Status values:**
    - `dubbing` - Processing in progress
    - `dubbed` - Complete, ready for download
    - `failed` - Processing failed
    """
    try:
        client = get_elevenlabs_client()

        response = client.dubbing.get_dubbing_project_metadata(dubbing_id=dubbing_id)

        return DubbingStatusResponse(
            dubbing_id=dubbing_id,
            name=response.name,
            status=response.status,
            target_languages=response.target_languages if response.target_languages else [],
            error=response.error if hasattr(response, 'error') else None
        )

    except Exception as e:
        logger.error(f"Failed to get dubbing status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get dubbing status: {str(e)}")


@router.get("/{dubbing_id}/audio/{language_code}")
async def get_dubbed_audio(
    dubbing_id: str,
    language_code: str,
):
    """
    Download the dubbed audio/video file.

    **Note:** The dubbing must be complete (status = 'dubbed') before downloading.

    Returns the dubbed content as a streaming MP3/MP4 file.
    """
    try:
        client = get_elevenlabs_client()

        # First check status
        metadata = client.dubbing.get_dubbing_project_metadata(dubbing_id=dubbing_id)
        if metadata.status != "dubbed":
            raise HTTPException(
                status_code=400,
                detail=f"Dubbing not complete. Current status: {metadata.status}"
            )

        # Get the dubbed file
        audio_generator = client.dubbing.get_dubbed_file(
            dubbing_id=dubbing_id,
            language_code=language_code
        )

        # Stream the response
        def generate():
            for chunk in audio_generator:
                yield chunk

        return StreamingResponse(
            generate(),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"attachment; filename=dubbed_{dubbing_id}_{language_code}.mp3"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get dubbed audio: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get dubbed audio: {str(e)}")


@router.delete("/{dubbing_id}")
async def delete_dubbing(dubbing_id: str):
    """
    Delete a dubbing project.

    Removes the dubbing project and all associated files from ElevenLabs.
    """
    try:
        client = get_elevenlabs_client()

        client.dubbing.delete_dubbing_project(dubbing_id=dubbing_id)

        return {"message": f"Dubbing project {dubbing_id} deleted successfully"}

    except Exception as e:
        logger.error(f"Failed to delete dubbing project: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete dubbing project: {str(e)}")
