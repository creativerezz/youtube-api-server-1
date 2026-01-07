"""
LLM Service for video analysis and chat.

Supports OpenAI and Anthropic APIs for processing video transcripts
with prompts for extraction, summarization, and chat.
"""
import logging
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> str:
        """Generate a completion from the LLM."""
        pass

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> str:
        """Generate a chat completion with message history."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1"

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> str:
        from app.main import get_http_client

        client = get_http_client()

        response = await client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def chat(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> str:
        from app.main import get_http_client

        client = get_http_client()

        formatted_messages = [{"role": "system", "content": system_prompt}]
        for msg in messages:
            formatted_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        response = await client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": formatted_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


class AnthropicProvider(LLMProvider):
    """Anthropic API provider."""

    def __init__(self, api_key: str, model: str = "claude-3-haiku-20240307"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1"

    async def complete(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> str:
        from app.main import get_http_client

        client = get_http_client()

        response = await client.post(
            f"{self.base_url}/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]

    async def chat(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        temperature: float = 0.7,
    ) -> str:
        from app.main import get_http_client

        client = get_http_client()

        formatted_messages = []
        for msg in messages:
            formatted_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            })

        response = await client.post(
            f"{self.base_url}/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "system": system_prompt,
                "messages": formatted_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"]


class LLMService:
    """
    Main LLM service that manages providers and handles analysis requests.
    """

    def __init__(self):
        self.provider: Optional[LLMProvider] = None
        self._initialize_provider()

    def _initialize_provider(self):
        """Initialize the LLM provider based on configuration."""
        provider_type = settings.LLM_PROVIDER.lower()

        if provider_type == "openai" and settings.OPENAI_API_KEY:
            self.provider = OpenAIProvider(
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_MODEL,
            )
            logger.info(f"Initialized OpenAI provider with model {settings.OPENAI_MODEL}")
        elif provider_type == "anthropic" and settings.ANTHROPIC_API_KEY:
            self.provider = AnthropicProvider(
                api_key=settings.ANTHROPIC_API_KEY,
                model=settings.ANTHROPIC_MODEL,
            )
            logger.info(f"Initialized Anthropic provider with model {settings.ANTHROPIC_MODEL}")
        else:
            logger.warning("No LLM provider configured. Analysis features will be disabled.")

    @property
    def is_available(self) -> bool:
        """Check if LLM service is available."""
        return self.provider is not None

    async def analyze(
        self,
        transcript: str,
        analysis_type: str,
        custom_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze a video transcript using a specific analysis type.

        Args:
            transcript: The video transcript text
            analysis_type: Type of analysis (summary, patterns, insights, etc.)
            custom_prompt: Optional custom prompt to use

        Returns:
            Analysis results
        """
        if not self.is_available:
            raise ValueError("LLM service is not configured")

        # Get the appropriate prompt
        system_prompt = self._get_analysis_prompt(analysis_type, custom_prompt)

        # Truncate transcript if too long (keep first ~12000 chars for context window)
        max_transcript_length = 12000
        if len(transcript) > max_transcript_length:
            transcript = transcript[:max_transcript_length] + "\n\n[Transcript truncated...]"

        user_message = f"Please analyze the following video transcript:\n\n{transcript}"

        try:
            result = await self.provider.complete(
                system_prompt=system_prompt,
                user_message=user_message,
                max_tokens=2000,
                temperature=0.7,
            )
            return {
                "analysis_type": analysis_type,
                "result": result,
                "truncated": len(transcript) > max_transcript_length,
            }
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            raise

    async def chat_with_video(
        self,
        transcript: str,
        messages: List[Dict[str, str]],
        video_title: Optional[str] = None,
    ) -> str:
        """
        Chat about a video's content.

        Args:
            transcript: The video transcript text
            messages: Chat message history
            video_title: Optional video title for context

        Returns:
            Assistant's response
        """
        if not self.is_available:
            raise ValueError("LLM service is not configured")

        # Truncate transcript if too long
        max_transcript_length = 10000
        truncated = len(transcript) > max_transcript_length
        if truncated:
            transcript = transcript[:max_transcript_length] + "\n\n[Transcript truncated...]"

        title_context = f'titled "{video_title}"' if video_title else ""
        system_prompt = f"""You are a helpful assistant that answers questions about a YouTube video {title_context}.

Here is the video transcript:

{transcript}

---

Answer questions about this video based on the transcript. Be helpful, accurate, and cite specific parts of the transcript when relevant. If asked about something not covered in the transcript, say so."""

        try:
            result = await self.provider.chat(
                system_prompt=system_prompt,
                messages=messages,
                max_tokens=1500,
                temperature=0.7,
            )
            return result
        except Exception as e:
            logger.error(f"LLM chat failed: {e}")
            raise

    def _get_analysis_prompt(self, analysis_type: str, custom_prompt: Optional[str] = None) -> str:
        """Get the system prompt for the analysis type."""
        if custom_prompt:
            return custom_prompt

        prompts = {
            "summary": """You are an expert at summarizing video content. Create a clear, concise summary that captures the main points, key takeaways, and important details from the video transcript. Structure your summary with:
1. A brief overview (2-3 sentences)
2. Main points (bullet points)
3. Key takeaways""",

            "patterns": """You are an expert at identifying patterns and recurring themes. Analyze the video transcript and identify:
1. Recurring themes or topics
2. Patterns in the speaker's arguments or explanations
3. Repeated phrases or concepts
4. Structural patterns in how information is presented
Format your response with clear headings and bullet points.""",

            "insights": """You are an expert analyst. Extract valuable insights from this video transcript including:
1. Non-obvious observations
2. Implications of what's discussed
3. Connections to broader topics
4. Actionable insights viewers can apply
Be specific and reference parts of the transcript.""",

            "key_points": """Extract the most important points from this video transcript. List:
1. The main argument or thesis
2. Supporting points (numbered list)
3. Evidence or examples provided
4. Conclusions drawn
Be concise but comprehensive.""",

            "questions": """Identify all questions raised in this video transcript, including:
1. Explicit questions asked by the speaker
2. Implicit questions the content addresses
3. Questions left unanswered
4. Questions a viewer might have after watching
Format as a numbered list with context for each question.""",

            "action_items": """Extract actionable items and recommendations from this video transcript:
1. Direct advice given
2. Steps or processes explained
3. Recommendations (explicit and implicit)
4. Things the viewer should do, try, or consider
Format as a clear action list with context.""",

            "topics": """Identify and categorize all topics discussed in this video transcript:
1. Main topic
2. Subtopics (with timestamps if mentioned)
3. Related tangents
4. Brief description of each topic
Create a structured topic outline.""",
        }

        return prompts.get(
            analysis_type,
            prompts["summary"]  # Default to summary
        )


# Global service instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get the global LLM service instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
