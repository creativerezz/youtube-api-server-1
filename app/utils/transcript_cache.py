"""
Transcript and metadata cache module for storing YouTube data.

Provides in-memory caching with TTL (time-to-live) support to reduce
API calls and improve response times. Optionally supports Redis backend
for distributed caching.
"""
import time
import json
import logging
from typing import Optional, List, Tuple, TypedDict, Dict, Any
from collections import OrderedDict
from abc import ABC, abstractmethod

from app.core.config import settings

logger = logging.getLogger(__name__)


class Transcript(TypedDict):
    """Type definition for YouTube transcript snippet."""
    text: str
    start: float
    duration: float


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Set a value in the cache with TTL."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a value from the cache."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all values from the cache."""
        pass

    @abstractmethod
    def size(self) -> int:
        """Get the number of items in the cache."""
        pass


class MemoryCacheBackend(CacheBackend):
    """In-memory cache backend using OrderedDict for LRU eviction."""

    def __init__(self, max_size: int = 1000):
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self.max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None

        value, expiry = self._cache[key]

        # Check if expired
        if time.time() > expiry:
            del self._cache[key]
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        # Remove if already exists
        if key in self._cache:
            del self._cache[key]

        # Evict oldest entries if cache is full
        while len(self._cache) >= self.max_size:
            self._cache.popitem(last=False)

        # Add new entry with expiry time
        expiry = time.time() + ttl_seconds
        self._cache[key] = (value, expiry)

    def delete(self, key: str) -> None:
        if key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


class RedisCacheBackend(CacheBackend):
    """Redis cache backend for distributed caching."""

    def __init__(self, redis_url: str):
        try:
            import redis
            self._redis = redis.from_url(redis_url, decode_responses=True)
            self._prefix = "ytcache:"
            # Test connection
            self._redis.ping()
            logger.info(f"Connected to Redis at {redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def _make_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    def get(self, key: str) -> Optional[Any]:
        try:
            value = self._redis.get(self._make_key(key))
            if value is None:
                return None
            return json.loads(value)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        try:
            self._redis.setex(
                self._make_key(key),
                ttl_seconds,
                json.dumps(value)
            )
        except Exception as e:
            logger.error(f"Redis set error: {e}")

    def delete(self, key: str) -> None:
        try:
            self._redis.delete(self._make_key(key))
        except Exception as e:
            logger.error(f"Redis delete error: {e}")

    def clear(self) -> None:
        try:
            # Delete all keys with our prefix
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=f"{self._prefix}*", count=100)
                if keys:
                    self._redis.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.error(f"Redis clear error: {e}")

    def size(self) -> int:
        try:
            cursor = 0
            count = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=f"{self._prefix}*", count=100)
                count += len(keys)
                if cursor == 0:
                    break
            return count
        except Exception as e:
            logger.error(f"Redis size error: {e}")
            return 0


class TranscriptCache:
    """
    Cache for YouTube transcripts and metadata with TTL support.

    Supports both in-memory (LRU) and Redis backends.
    Cache keys are constructed from video_id and optional language tuple.
    """

    def __init__(self):
        self.enabled = settings.CACHE_ENABLED
        self.ttl_seconds = settings.CACHE_TTL_SECONDS
        self.max_size = settings.CACHE_MAX_SIZE
        self.backend_type = settings.CACHE_BACKEND

        # Initialize backend
        if not self.enabled:
            self._backend = None
        elif self.backend_type == "redis":
            try:
                self._backend = RedisCacheBackend(settings.REDIS_URL)
            except Exception:
                logger.warning("Failed to initialize Redis, falling back to memory cache")
                self._backend = MemoryCacheBackend(self.max_size)
                self.backend_type = "memory"
        else:
            self._backend = MemoryCacheBackend(self.max_size)

    def _make_transcript_key(self, video_id: str, languages: Optional[List[str]]) -> str:
        """Create a cache key for transcript from video_id and languages."""
        lang_str = ",".join(sorted(languages)) if languages else "en"
        return f"transcript:{video_id}:{lang_str}"

    def _make_metadata_key(self, video_id: str) -> str:
        """Create a cache key for metadata from video_id."""
        return f"metadata:{video_id}"

    def get(self, video_id: str, languages: Optional[List[str]] = None) -> Optional[List[Transcript]]:
        """
        Get cached transcript if available and not expired.

        Args:
            video_id: YouTube video ID
            languages: List of language codes (e.g., ["en", "es"])

        Returns:
            Cached transcript list if found and valid, None otherwise
        """
        if not self.enabled or self._backend is None:
            return None

        key = self._make_transcript_key(video_id, languages)
        return self._backend.get(key)

    def set(self, video_id: str, transcript: List[Transcript], languages: Optional[List[str]] = None) -> None:
        """
        Cache a transcript.

        Args:
            video_id: YouTube video ID
            transcript: List of transcript snippets
            languages: List of language codes used to fetch the transcript
        """
        if not self.enabled or self._backend is None:
            return

        key = self._make_transcript_key(video_id, languages)
        # Convert transcript objects to dicts if they have __dict__
        transcript_data = [
            {"text": t.text, "start": t.start, "duration": t.duration}
            if hasattr(t, 'text') else dict(t)
            for t in transcript
        ]
        self._backend.set(key, transcript_data, self.ttl_seconds)

    def get_metadata(self, video_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached metadata if available and not expired.

        Args:
            video_id: YouTube video ID

        Returns:
            Cached metadata dict if found and valid, None otherwise
        """
        if not self.enabled or self._backend is None:
            return None

        key = self._make_metadata_key(video_id)
        return self._backend.get(key)

    def set_metadata(self, video_id: str, metadata: Dict[str, Any]) -> None:
        """
        Cache video metadata.

        Args:
            video_id: YouTube video ID
            metadata: Metadata dictionary
        """
        if not self.enabled or self._backend is None:
            return

        key = self._make_metadata_key(video_id)
        self._backend.set(key, metadata, self.ttl_seconds)

    def clear(self) -> None:
        """Clear all cached data."""
        if self._backend is not None:
            self._backend.clear()

    def size(self) -> int:
        """Get current cache size."""
        if self._backend is None:
            return 0
        return self._backend.size()

    def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.
        Note: Only applicable for memory backend. Redis handles expiry automatically.

        Returns:
            Number of entries removed (0 for Redis backend)
        """
        if not self.enabled or self._backend is None:
            return 0

        if isinstance(self._backend, MemoryCacheBackend):
            # For memory backend, we need to scan and remove expired entries
            # This is handled automatically on get() but we can do a full scan
            expired_count = 0
            keys_to_check = list(self._backend._cache.keys())
            for key in keys_to_check:
                if key in self._backend._cache:
                    _, expiry = self._backend._cache[key]
                    if time.time() > expiry:
                        del self._backend._cache[key]
                        expired_count += 1
            return expired_count

        # Redis handles expiry automatically
        return 0


# Global cache instance
_transcript_cache: Optional[TranscriptCache] = None


def get_cache() -> TranscriptCache:
    """Get the global transcript cache instance."""
    global _transcript_cache
    if _transcript_cache is None:
        _transcript_cache = TranscriptCache()
    return _transcript_cache
