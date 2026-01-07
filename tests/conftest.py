"""
Pytest configuration and fixtures for YouTube API Server tests.
"""
import pytest
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_transcript() -> List[Dict[str, Any]]:
    """Sample transcript data for testing."""
    return [
        {"text": "Hello everyone", "start": 0.0, "duration": 2.0},
        {"text": "Welcome to this video", "start": 2.0, "duration": 3.0},
        {"text": "Today we'll discuss Python", "start": 5.0, "duration": 4.0},
        {"text": "Let's get started", "start": 12.0, "duration": 2.5},  # 3 second gap
        {"text": "First topic is testing", "start": 14.5, "duration": 3.0},
        {"text": "Testing is important", "start": 17.5, "duration": 2.5},
        {"text": "It helps catch bugs", "start": 20.0, "duration": 3.0},
        {"text": "Now let's move on", "start": 26.0, "duration": 2.0},  # 3 second gap
        {"text": "Second topic is caching", "start": 28.0, "duration": 3.0},
        {"text": "Caching improves performance", "start": 31.0, "duration": 3.5},
    ]


@pytest.fixture
def mock_metadata() -> Dict[str, Any]:
    """Sample video metadata for testing."""
    return {
        "title": "Test Video Title",
        "author_name": "Test Author",
        "author_url": "https://www.youtube.com/@testauthor",
        "type": "video",
        "height": 113,
        "width": 200,
        "version": "1.0",
        "provider_name": "YouTube",
        "provider_url": "https://www.youtube.com/",
        "thumbnail_url": "https://i.ytimg.com/vi/test123/hqdefault.jpg",
    }


@pytest.fixture
def test_video_ids() -> List[str]:
    """Sample video IDs for testing."""
    return [
        "dQw4w9WgXcQ",  # Rick Astley - Never Gonna Give You Up
        "jNQXAC9IVRw",  # Me at the zoo (first YouTube video)
        "9bZkp7q19f0",  # PSY - Gangnam Style
    ]


@pytest.fixture
def test_video_urls() -> List[str]:
    """Various YouTube URL formats for testing."""
    return [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/v/dQw4w9WgXcQ",
        "dQw4w9WgXcQ",  # Plain video ID
    ]


@pytest.fixture
def mock_cache():
    """Mock transcript cache for testing."""
    from app.utils.transcript_cache import TranscriptCache

    cache = TranscriptCache()
    cache.enabled = True
    cache.ttl_seconds = 3600
    cache.max_size = 100
    return cache


@pytest.fixture
def test_client():
    """FastAPI test client."""
    from fastapi.testclient import TestClient
    from app.main import app

    # Create a test client
    with TestClient(app) as client:
        yield client


@pytest.fixture
def async_test_client():
    """Async FastAPI test client for async tests."""
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def mock_youtube_api(mock_transcript):
    """Mock YouTubeTranscriptApi for testing without real API calls."""
    with patch('app.utils.youtube_tools.YouTubeTranscriptApi') as mock_api:
        # Create a mock transcript response
        mock_fetch = MagicMock()
        mock_fetch.return_value = [
            MagicMock(text=t["text"], start=t["start"], duration=t["duration"])
            for t in mock_transcript
        ]
        mock_api.return_value.fetch = mock_fetch
        yield mock_api


@pytest.fixture
def mock_http_client(mock_metadata):
    """Mock httpx client for testing metadata fetching."""
    with patch('app.main.http_client') as mock_client:
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_metadata
        mock_response.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        yield mock_client
