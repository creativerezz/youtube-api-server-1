import os
from dotenv import load_dotenv  # pyright: ignore[reportMissingImports]

# Load environment variables from .env file
load_dotenv()

class Settings:
    """
    Application settings
    
    Reads settings from environment variables or .env file
    """
    # API settings
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "YouTube Tools API"
    
    # Server settings
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # CORS settings - add specific origins in production
    # Parse comma-separated origins from environment variable
    BACKEND_CORS_ORIGINS: list = (
        [origin.strip() for origin in os.getenv("BACKEND_CORS_ORIGINS", "*").split(",")]
        if os.getenv("BACKEND_CORS_ORIGINS")
        else ["*"]
    )
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Proxy settings for YouTube API (to work around IP blocking)
    PROXY_TYPE: str = os.getenv("PROXY_TYPE", "")  # "generic" or "webshare"
    PROXY_URL: str = os.getenv("PROXY_URL", "")  # For generic proxies
    PROXY_HTTP: str = os.getenv("PROXY_HTTP", "")
    PROXY_HTTPS: str = os.getenv("PROXY_HTTPS", "") 
    WEBSHARE_USERNAME: str = os.getenv("WEBSHARE_USERNAME", "")
    WEBSHARE_PASSWORD: str = os.getenv("WEBSHARE_PASSWORD", "")
    
    # Cache settings for transcripts
    CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "3600"))  # Default: 1 hour
    CACHE_MAX_SIZE: int = int(os.getenv("CACHE_MAX_SIZE", "1000"))  # Maximum number of cached transcripts
    CACHE_BACKEND: str = os.getenv("CACHE_BACKEND", "memory")  # "memory" or "redis"

    # Redis settings (for cache backend)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Rate limiting settings
    RATE_LIMIT_ENABLED: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))  # requests per window
    RATE_LIMIT_WINDOW: str = os.getenv("RATE_LIMIT_WINDOW", "minute")  # second, minute, hour, day

    # LLM settings for video analysis and chat
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "openai")  # "openai" or "anthropic"
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

    # YouTube Data API v3 settings (for search and channel endpoints)
    YOUTUBE_API_KEY: str = os.getenv("YOUTUBE_API_KEY", "")

    # ElevenLabs settings (for dubbing/translation)
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")

    # Clerk authentication settings
    CLERK_SECRET_KEY: str = os.getenv("CLERK_SECRET_KEY", "")
    CLERK_ISSUER_URL: str = os.getenv("CLERK_ISSUER_URL", "")  # e.g., https://your-domain.clerk.accounts.dev
    CLERK_AUTH_ENABLED: bool = os.getenv("CLERK_AUTH_ENABLED", "false").lower() == "true"

# Create settings instance
settings = Settings()