import asyncio
from urllib.parse import urlparse, parse_qs
from typing import Optional, List, TYPE_CHECKING

from fastapi import HTTPException
from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore
from youtube_transcript_api.proxies import GenericProxyConfig, WebshareProxyConfig
from app.core.config import settings
from app.utils.transcript_cache import get_cache, Transcript

if TYPE_CHECKING:
    import httpx

class YouTubeTools:
    @staticmethod
    def _get_youtube_api() -> YouTubeTranscriptApi:
        """Create YouTubeTranscriptApi instance with proxy configuration if available."""
        proxy_config = None
        
        if settings.PROXY_TYPE == "generic" and settings.PROXY_URL:
            # Use the provided proxy URL for both HTTP and HTTPS
            proxy_config = GenericProxyConfig(
                http_url=settings.PROXY_URL,
                https_url=settings.PROXY_URL
            )
        elif settings.PROXY_TYPE == "generic" and (settings.PROXY_HTTP or settings.PROXY_HTTPS):
            # Use separate HTTP/HTTPS proxies if provided
            proxy_config = GenericProxyConfig(
                http_url=settings.PROXY_HTTP or settings.PROXY_HTTPS,
                https_url=settings.PROXY_HTTPS or settings.PROXY_HTTP
            )
        elif settings.PROXY_TYPE == "webshare" and settings.WEBSHARE_USERNAME and settings.WEBSHARE_PASSWORD:
            # Use Webshare rotating proxies
            proxy_config = WebshareProxyConfig(
                proxy_username=settings.WEBSHARE_USERNAME,
                proxy_password=settings.WEBSHARE_PASSWORD
            )
        
        return YouTubeTranscriptApi(proxy_config=proxy_config)

    @staticmethod
    async def _fetch_transcript(
        video_id: str,
        languages: Optional[List[str]] = None,
        translate_to: Optional[str] = None
    ) -> List[Transcript]:
        """
        Fetch transcript for a video, using cache if available.

        This is a shared method used by both get_video_captions and get_video_timestamps
        to avoid duplicate API calls and benefit from caching.

        Args:
            video_id: YouTube video ID
            languages: List of language codes (e.g., ["en", "es"])
            translate_to: Target language code for translation (e.g., "en")
                         If provided, will translate from available transcript.
                         If not provided but direct fetch fails, will attempt auto-translation.

        Returns:
            List of transcript snippets

        Raises:
            HTTPException: If transcript cannot be fetched
        """
        cache = get_cache()
        normalized_languages = languages or ["en"]

        # Create cache key that includes translation target
        cache_key_langs = normalized_languages if not translate_to else [f"{normalized_languages[0]}->>{translate_to}"]

        # Try to get from cache first
        cached_transcript = cache.get(video_id, cache_key_langs)
        if cached_transcript is not None:
            return cached_transcript

        api = YouTubeTools._get_youtube_api()
        loop = asyncio.get_running_loop()

        # If explicit translation requested, go directly to translation flow
        if translate_to:
            transcript = await YouTubeTools._fetch_with_translation(
                api, loop, video_id, normalized_languages, translate_to
            )
            cache.set(video_id, transcript, cache_key_langs)
            return transcript

        # Try direct fetch first
        try:
            transcript = await loop.run_in_executor(
                None,
                lambda: api.fetch(video_id, languages=normalized_languages)
            )
            cache.set(video_id, transcript, cache_key_langs)
            return transcript
        except Exception as direct_error:
            # Direct fetch failed - try translation fallback
            target_lang = normalized_languages[0]  # Translate to first requested language
            try:
                transcript = await YouTubeTools._fetch_with_translation(
                    api, loop, video_id, None, target_lang
                )
                # Cache with translation marker
                cache.set(video_id, transcript, [f"auto->>{target_lang}"])
                return transcript
            except Exception:
                # Translation also failed - raise the original error with helpful message
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "This video's captions are currently unavailable. "
                        "This may be due to:\n"
                        "• The video doesn't have captions/subtitles enabled\n"
                        "• Temporary YouTube API restrictions\n"
                        "• The video is private or restricted\n\n"
                        "Try another video or check back later."
                    )
                )

    @staticmethod
    async def _fetch_with_translation(
        api,
        loop,
        video_id: str,
        source_languages: Optional[List[str]],
        target_language: str
    ) -> List[Transcript]:
        """
        Fetch transcript and translate it to target language.

        Args:
            api: YouTubeTranscriptApi instance
            loop: Event loop for executor
            video_id: YouTube video ID
            source_languages: Preferred source languages (None = any available)
            target_language: Target language code for translation

        Returns:
            List of translated transcript snippets

        Raises:
            HTTPException: If no translatable transcript is found
        """
        def _translate_transcript():
            transcript_list = api.list(video_id)

            # Find a transcript to translate from
            transcript_to_translate = None

            # If source languages specified, try those first
            if source_languages:
                for lang in source_languages:
                    try:
                        transcript_to_translate = transcript_list.find_transcript([lang])
                        break
                    except Exception:
                        continue

            # If no specific source found, find any translatable transcript
            if transcript_to_translate is None:
                for transcript in transcript_list:
                    if transcript.is_translatable:
                        transcript_to_translate = transcript
                        break

            if transcript_to_translate is None:
                raise HTTPException(
                    status_code=404,
                    detail="No translatable captions found for this video."
                )

            if not transcript_to_translate.is_translatable:
                raise HTTPException(
                    status_code=400,
                    detail=f"Captions in '{transcript_to_translate.language}' cannot be translated."
                )

            # Check if target language is available for translation
            # Handle both object attributes (new API) and dict keys (old API) for compatibility
            available_langs = [
                lang.language_code if hasattr(lang, 'language_code') else lang['language_code']
                for lang in transcript_to_translate.translation_languages
            ]
            if target_language not in available_langs:
                raise HTTPException(
                    status_code=400,
                    detail=f"Translation to '{target_language}' not available. Available: {available_langs[:10]}..."
                )

            # Translate and fetch
            translated = transcript_to_translate.translate(target_language)
            return translated.fetch()

        try:
            return await loop.run_in_executor(None, _translate_transcript)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error translating captions: {str(e)}"
            )

    @staticmethod
    def get_youtube_video_id(url_or_id: str) -> Optional[str]:
        """Extract a YouTube video ID from either a full URL *or* a raw video ID.

        This helper now supports three input formats so that the API is more
        forgiving when used from the interactive docs:

        1. Full YouTube watch URLs – e.g. ``https://www.youtube.com/watch?v=dQw4w9WgXcQ``
        2. Shortened URLs – e.g. ``https://youtu.be/dQw4w9WgXcQ``
        3. A plain 11-character video ID – e.g. ``dQw4w9WgXcQ``
        """

        # First, handle the case where the user passed the plain 11-character ID.
        allowed_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
        if len(url_or_id) == 11 and all(ch in allowed_chars for ch in url_or_id):
            return url_or_id

        # Otherwise, attempt to parse as a URL.
        parsed_url = urlparse(url_or_id)
        hostname = parsed_url.hostname

        if hostname == "youtu.be":
            return parsed_url.path.lstrip("/") or None

        if hostname in ("www.youtube.com", "youtube.com"):
            if parsed_url.path == "/watch":
                query_params = parse_qs(parsed_url.query)
                return query_params.get("v", [None])[0]
            if parsed_url.path.startswith("/embed/"):
                return parsed_url.path.split("/")[2]
            if parsed_url.path.startswith("/v/"):
                return parsed_url.path.split("/")[2]

        return None

    @staticmethod
    async def get_video_data(url: str, use_cache: bool = True) -> dict:
        """Function to get video data from a YouTube URL.

        Args:
            url: YouTube video URL or ID
            use_cache: Whether to use cached metadata (default: True)
        """
        if not url:
            raise HTTPException(status_code=400, detail="No URL provided")

        try:
            video_id = YouTubeTools.get_youtube_video_id(url)
            if not video_id:
                raise HTTPException(status_code=400, detail="Invalid YouTube URL")
        except Exception:
            raise HTTPException(status_code=400, detail="Error getting video ID from URL")

        # Check metadata cache first
        cache = get_cache()
        if use_cache:
            cached_metadata = cache.get_metadata(video_id)
            if cached_metadata is not None:
                return cached_metadata

        try:
            from app.main import get_http_client
            client = get_http_client()

            params = {"format": "json", "url": f"https://www.youtube.com/watch?v={video_id}"}
            oembed_url = "https://www.youtube.com/oembed"

            response = await client.get(oembed_url, params=params)
            response.raise_for_status()
            video_data = response.json()

            clean_data = {
                "title": video_data.get("title"),
                "author_name": video_data.get("author_name"),
                "author_url": video_data.get("author_url"),
                "type": video_data.get("type"),
                "height": video_data.get("height"),
                "width": video_data.get("width"),
                "version": video_data.get("version"),
                "provider_name": video_data.get("provider_name"),
                "provider_url": video_data.get("provider_url"),
                "thumbnail_url": video_data.get("thumbnail_url"),
            }

            # Cache the metadata
            if use_cache:
                cache.set_metadata(video_id, clean_data)

            return clean_data
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error getting video data: {str(e)}")

    @staticmethod
    async def get_video_captions(
        url_or_id: str,
        languages: Optional[List[str]] = None,
        translate_to: Optional[str] = None
    ) -> str:
        """Return plain-text captions for the requested YouTube video.

        If *languages* is omitted, English (``["en"]``) will be used by default.
        If *translate_to* is provided, captions will be translated to that language.
        If direct fetch fails, auto-translation will be attempted.
        """

        if not url_or_id:
            raise HTTPException(status_code=400, detail="No URL or ID provided")

        video_id = YouTubeTools.get_youtube_video_id(url_or_id)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL/ID")

        transcript = await YouTubeTools._fetch_transcript(video_id, languages, translate_to)

        if transcript:
            # Handle both object attributes and dict keys (from cache)
            return " ".join(
                snippet.text if hasattr(snippet, 'text') else snippet.get('text', '')
                for snippet in transcript
            )
        return "No captions found for video"

    @staticmethod
    async def get_video_timestamps(
        url_or_id: str,
        languages: Optional[List[str]] = None,
        translate_to: Optional[str] = None
    ) -> List[str]:
        """Return caption lines prefixed with the *start* timestamp.

        The function now mirrors :py:meth:`get_video_captions` and accepts either
        a full URL **or** a raw 11-character video ID.  If *languages* is
        omitted we default to English (``["en"]``).
        If *translate_to* is provided, captions will be translated to that language.
        """

        if not url_or_id:
            raise HTTPException(status_code=400, detail="No URL or ID provided")

        video_id = YouTubeTools.get_youtube_video_id(url_or_id)
        if not video_id:
            raise HTTPException(status_code=400, detail="Invalid YouTube URL/ID")

        transcript = await YouTubeTools._fetch_transcript(video_id, languages, translate_to)

        timestamps: List[str] = []
        for snippet in transcript:
            # Handle both object attributes and dict keys (from cache)
            start = int(snippet.start if hasattr(snippet, 'start') else snippet.get('start', 0))
            text = snippet.text if hasattr(snippet, 'text') else snippet.get('text', '')
            minutes, seconds = divmod(start, 60)
            timestamps.append(f"{minutes}:{seconds:02d} - {text}")
        return timestamps