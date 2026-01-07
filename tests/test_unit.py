"""
Unit tests for YouTube API Server.

These tests use mocked data and don't require actual YouTube API access.
"""
import pytest
import time
from unittest.mock import patch, MagicMock, AsyncMock

from app.utils.youtube_tools import YouTubeTools
from app.utils.transcript_cache import (
    TranscriptCache,
    MemoryCacheBackend,
    get_cache,
)


class TestVideoIdExtraction:
    """Tests for YouTube video ID extraction from various URL formats."""

    def test_extract_from_standard_url(self):
        """Test extraction from standard YouTube watch URL."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert YouTubeTools.get_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_from_short_url(self):
        """Test extraction from youtu.be short URL."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert YouTubeTools.get_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_from_embed_url(self):
        """Test extraction from YouTube embed URL."""
        url = "https://www.youtube.com/embed/dQw4w9WgXcQ"
        assert YouTubeTools.get_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_from_v_url(self):
        """Test extraction from YouTube /v/ URL."""
        url = "https://www.youtube.com/v/dQw4w9WgXcQ"
        assert YouTubeTools.get_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_extract_plain_video_id(self):
        """Test extraction when given a plain 11-character video ID."""
        video_id = "dQw4w9WgXcQ"
        assert YouTubeTools.get_youtube_video_id(video_id) == "dQw4w9WgXcQ"

    def test_extract_with_extra_params(self):
        """Test extraction from URL with extra query parameters."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PLxyz"
        assert YouTubeTools.get_youtube_video_id(url) == "dQw4w9WgXcQ"

    def test_invalid_url_returns_none(self):
        """Test that invalid URLs return None."""
        assert YouTubeTools.get_youtube_video_id("https://example.com/video") is None
        assert YouTubeTools.get_youtube_video_id("not-a-url") is None
        assert YouTubeTools.get_youtube_video_id("") is None

    def test_video_id_with_special_chars(self):
        """Test video IDs containing special characters like underscore and hyphen."""
        assert YouTubeTools.get_youtube_video_id("abc_def-123") == "abc_def-123"
        assert YouTubeTools.get_youtube_video_id("_-_-_-_-_-_") == "_-_-_-_-_-_"


class TestMemoryCacheBackend:
    """Tests for the in-memory cache backend."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = MemoryCacheBackend(max_size=10)
        cache.set("key1", {"data": "value"}, ttl_seconds=3600)

        result = cache.get("key1")
        assert result == {"data": "value"}

    def test_get_nonexistent_key(self):
        """Test getting a key that doesn't exist."""
        cache = MemoryCacheBackend(max_size=10)
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = MemoryCacheBackend(max_size=10)
        cache.set("key1", "value", ttl_seconds=1)

        # Should exist immediately
        assert cache.get("key1") == "value"

        # Wait for expiration
        time.sleep(1.5)
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        """Test that LRU eviction works when cache is full."""
        cache = MemoryCacheBackend(max_size=3)

        cache.set("key1", "value1", ttl_seconds=3600)
        cache.set("key2", "value2", ttl_seconds=3600)
        cache.set("key3", "value3", ttl_seconds=3600)

        # Access key1 to make it recently used
        cache.get("key1")

        # Add a new key, should evict key2 (least recently used)
        cache.set("key4", "value4", ttl_seconds=3600)

        assert cache.get("key1") == "value1"  # Still exists (was accessed)
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"  # Still exists
        assert cache.get("key4") == "value4"  # New entry

    def test_clear(self):
        """Test clearing the cache."""
        cache = MemoryCacheBackend(max_size=10)
        cache.set("key1", "value1", ttl_seconds=3600)
        cache.set("key2", "value2", ttl_seconds=3600)

        assert cache.size() == 2
        cache.clear()
        assert cache.size() == 0

    def test_size(self):
        """Test size reporting."""
        cache = MemoryCacheBackend(max_size=10)
        assert cache.size() == 0

        cache.set("key1", "value1", ttl_seconds=3600)
        assert cache.size() == 1

        cache.set("key2", "value2", ttl_seconds=3600)
        assert cache.size() == 2

    def test_update_existing_key(self):
        """Test updating an existing key."""
        cache = MemoryCacheBackend(max_size=10)
        cache.set("key1", "old_value", ttl_seconds=3600)
        cache.set("key1", "new_value", ttl_seconds=3600)

        assert cache.get("key1") == "new_value"
        assert cache.size() == 1


class TestTranscriptCache:
    """Tests for the TranscriptCache class."""

    def test_cache_disabled(self):
        """Test that cache returns None when disabled."""
        with patch('app.utils.transcript_cache.settings') as mock_settings:
            mock_settings.CACHE_ENABLED = False
            mock_settings.CACHE_TTL_SECONDS = 3600
            mock_settings.CACHE_MAX_SIZE = 1000
            mock_settings.CACHE_BACKEND = "memory"

            cache = TranscriptCache()
            cache.set("video123", [{"text": "test"}], ["en"])
            assert cache.get("video123", ["en"]) is None

    def test_transcript_cache_key_generation(self):
        """Test that cache keys are generated correctly."""
        cache = TranscriptCache()

        # Test transcript key
        key1 = cache._make_transcript_key("video123", ["en"])
        key2 = cache._make_transcript_key("video123", ["en", "es"])
        key3 = cache._make_transcript_key("video123", None)

        assert key1 == "transcript:video123:en"
        assert key2 == "transcript:video123:en,es"  # Sorted
        assert key3 == "transcript:video123:en"  # Default

    def test_metadata_cache_key_generation(self):
        """Test that metadata cache keys are generated correctly."""
        cache = TranscriptCache()
        key = cache._make_metadata_key("video123")
        assert key == "metadata:video123"

    def test_set_and_get_transcript(self, mock_transcript):
        """Test caching and retrieving transcripts."""
        with patch('app.utils.transcript_cache.settings') as mock_settings:
            mock_settings.CACHE_ENABLED = True
            mock_settings.CACHE_TTL_SECONDS = 3600
            mock_settings.CACHE_MAX_SIZE = 1000
            mock_settings.CACHE_BACKEND = "memory"

            cache = TranscriptCache()
            cache.set("video123", mock_transcript, ["en"])

            result = cache.get("video123", ["en"])
            assert result is not None
            assert len(result) == len(mock_transcript)

    def test_set_and_get_metadata(self, mock_metadata):
        """Test caching and retrieving metadata."""
        with patch('app.utils.transcript_cache.settings') as mock_settings:
            mock_settings.CACHE_ENABLED = True
            mock_settings.CACHE_TTL_SECONDS = 3600
            mock_settings.CACHE_MAX_SIZE = 1000
            mock_settings.CACHE_BACKEND = "memory"

            cache = TranscriptCache()
            cache.set_metadata("video123", mock_metadata)

            result = cache.get_metadata("video123")
            assert result is not None
            assert result["title"] == mock_metadata["title"]


class TestYouTubeToolsAsync:
    """Async tests for YouTubeTools class."""

    @pytest.mark.asyncio
    async def test_get_video_data_caching(self, mock_metadata):
        """Test that video metadata is cached."""
        with patch('app.utils.transcript_cache.settings') as mock_settings:
            mock_settings.CACHE_ENABLED = True
            mock_settings.CACHE_TTL_SECONDS = 3600
            mock_settings.CACHE_MAX_SIZE = 1000
            mock_settings.CACHE_BACKEND = "memory"

            # Reset the global cache
            import app.utils.transcript_cache as cache_module
            cache_module._transcript_cache = None

            with patch('app.main.get_http_client') as mock_get_client:
                mock_response = MagicMock()
                mock_response.json.return_value = mock_metadata
                mock_response.raise_for_status = MagicMock()

                mock_client = AsyncMock()
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_get_client.return_value = mock_client

                # First call should hit the API
                result1 = await YouTubeTools.get_video_data("dQw4w9WgXcQ")
                assert result1["title"] == mock_metadata["title"]
                assert mock_client.get.call_count == 1

                # Second call should hit the cache
                result2 = await YouTubeTools.get_video_data("dQw4w9WgXcQ")
                assert result2["title"] == mock_metadata["title"]
                assert mock_client.get.call_count == 1  # No additional API call

    @pytest.mark.asyncio
    async def test_get_video_captions(self, mock_transcript):
        """Test getting video captions."""
        with patch('app.utils.transcript_cache.settings') as mock_settings:
            mock_settings.CACHE_ENABLED = False
            mock_settings.CACHE_TTL_SECONDS = 3600
            mock_settings.CACHE_MAX_SIZE = 1000
            mock_settings.CACHE_BACKEND = "memory"

            # Reset cache
            import app.utils.transcript_cache as cache_module
            cache_module._transcript_cache = None

            with patch.object(YouTubeTools, '_get_youtube_api') as mock_get_api:
                # Create mock transcript objects with attributes
                mock_snippets = [
                    MagicMock(text=t["text"], start=t["start"], duration=t["duration"])
                    for t in mock_transcript
                ]

                mock_api = MagicMock()
                mock_api.fetch.return_value = mock_snippets
                mock_get_api.return_value = mock_api

                result = await YouTubeTools.get_video_captions("dQw4w9WgXcQ")

                assert "Hello everyone" in result
                assert "Welcome to this video" in result

    @pytest.mark.asyncio
    async def test_get_video_timestamps(self, mock_transcript):
        """Test getting video timestamps."""
        with patch('app.utils.transcript_cache.settings') as mock_settings:
            mock_settings.CACHE_ENABLED = False
            mock_settings.CACHE_TTL_SECONDS = 3600
            mock_settings.CACHE_MAX_SIZE = 1000
            mock_settings.CACHE_BACKEND = "memory"

            # Reset cache
            import app.utils.transcript_cache as cache_module
            cache_module._transcript_cache = None

            with patch.object(YouTubeTools, '_get_youtube_api') as mock_get_api:
                mock_snippets = [
                    MagicMock(text=t["text"], start=t["start"], duration=t["duration"])
                    for t in mock_transcript
                ]

                mock_api = MagicMock()
                mock_api.fetch.return_value = mock_snippets
                mock_get_api.return_value = mock_api

                result = await YouTubeTools.get_video_timestamps("dQw4w9WgXcQ")

                assert len(result) == len(mock_transcript)
                assert "0:00 - Hello everyone" in result
                assert "0:02 - Welcome to this video" in result


class TestSearchFunctionality:
    """Tests for transcript search functionality."""

    @pytest.mark.asyncio
    async def test_search_finds_matches(self, mock_transcript):
        """Test that search finds matching text."""
        with patch('app.utils.transcript_cache.settings') as mock_settings:
            mock_settings.CACHE_ENABLED = False
            mock_settings.CACHE_TTL_SECONDS = 3600
            mock_settings.CACHE_MAX_SIZE = 1000
            mock_settings.CACHE_BACKEND = "memory"

            import app.utils.transcript_cache as cache_module
            cache_module._transcript_cache = None

            with patch.object(YouTubeTools, '_fetch_transcript') as mock_fetch:
                mock_fetch.return_value = mock_transcript

                # Import the function we want to test
                from app.routes.youtube import search_transcript
                from fastapi import Request
                from unittest.mock import MagicMock

                mock_request = MagicMock(spec=Request)
                mock_request.state = MagicMock()

                result = await search_transcript(
                    request=mock_request,
                    video="dQw4w9WgXcQ",
                    query="Python",
                    context_lines=0
                )

                assert result["total_matches"] == 1
                assert "Python" in result["matches"][0]["text"]

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, mock_transcript):
        """Test that search is case-insensitive."""
        with patch('app.utils.transcript_cache.settings') as mock_settings:
            mock_settings.CACHE_ENABLED = False
            mock_settings.CACHE_TTL_SECONDS = 3600
            mock_settings.CACHE_MAX_SIZE = 1000
            mock_settings.CACHE_BACKEND = "memory"

            import app.utils.transcript_cache as cache_module
            cache_module._transcript_cache = None

            with patch.object(YouTubeTools, '_fetch_transcript') as mock_fetch:
                mock_fetch.return_value = mock_transcript

                from app.routes.youtube import search_transcript
                from fastapi import Request
                from unittest.mock import MagicMock

                mock_request = MagicMock(spec=Request)
                mock_request.state = MagicMock()

                result = await search_transcript(
                    request=mock_request,
                    video="dQw4w9WgXcQ",
                    query="python",  # lowercase
                    context_lines=0
                )

                assert result["total_matches"] == 1


class TestChapterDetection:
    """Tests for chapter detection functionality."""

    @pytest.mark.asyncio
    async def test_detect_chapters_with_gaps(self, mock_transcript):
        """Test that chapters are detected at silence gaps."""
        with patch('app.utils.transcript_cache.settings') as mock_settings:
            mock_settings.CACHE_ENABLED = False
            mock_settings.CACHE_TTL_SECONDS = 3600
            mock_settings.CACHE_MAX_SIZE = 1000
            mock_settings.CACHE_BACKEND = "memory"

            import app.utils.transcript_cache as cache_module
            cache_module._transcript_cache = None

            with patch.object(YouTubeTools, '_fetch_transcript') as mock_fetch:
                mock_fetch.return_value = mock_transcript

                from app.routes.youtube import detect_chapters
                from fastapi import Request
                from unittest.mock import MagicMock

                mock_request = MagicMock(spec=Request)
                mock_request.state = MagicMock()

                result = await detect_chapters(
                    request=mock_request,
                    video="dQw4w9WgXcQ",
                    min_gap_seconds=2.5,
                    min_segments=3
                )

                # Should detect chapters based on the 3-second gaps in mock_transcript
                assert result["total_chapters"] >= 1
                assert "chapters" in result
