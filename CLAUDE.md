# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Essential Commands

```bash
# Setup
pip install -e .              # Install package in development mode
cp .env.example .env          # Create config file (edit with your keys)

# Development Server
python -m app.main            # Start FastAPI server (with reload)
uvicorn app.main:app --reload # Alternative start method

# Testing
pytest                                    # Run full test suite
pytest -v                                 # Verbose output
pytest tests/test_unit.py -v              # Unit tests only
pytest tests/test_unit.py::TestVideoIdExtraction::test_extract_from_standard_url -v  # Single test
pytest tests/test_live_server.py          # Integration tests (requires running server)
pytest tests/test_proxy.py -v             # Test proxy configuration

# Linting & Type Checking (matches CI)
ruff check app/                           # Lint Python code
ruff format app/ --check                  # Check formatting
mypy app/ --ignore-missing-imports        # Type checking

# Performance Testing
python test_transcript_speed.py           # Test local server
python test_transcript_speed.py https://transcript.youtubesummaries.cc  # Test production

# Docker
docker-compose up -d                      # Start with Docker Compose

# Changelog (auto-generated from commits)
git-cliff --output CHANGELOG.md           # Regenerate full changelog
git-cliff --unreleased                    # Preview unreleased changes
git-cliff --tag v1.3.0 --output CHANGELOG.md  # Tag a release
```

## Architecture Overview

fast-proxy-api server (built with FastAPI) that extracts YouTube video metadata, captions, timestamps, and provides AI-powered video analysis. Acts as middleware between clients and YouTube APIs.

### Route Structure (`app/routes/`)
| Route File | Prefix | Purpose |
|------------|--------|---------|
| `youtube.py` | `/youtube` | Metadata, captions, timestamps, batch operations |
| `ai.py` | `/youtube/ai` | AI analysis and chat (requires LLM config) |
| `data_api.py` | `/youtube/data` | YouTube Data API v3 proxy (search, channels) |
| `prompts.py` | `/prompts` | Prompt template management |
| `service.py` | `/service` | Status pages, health checks |

### Core Components
- **`app/main.py`**: FastAPI app with lifespan-managed httpx.AsyncClient, middleware (GZip, CORS, rate limiting)
- **`app/core/config.py`**: Settings class reading from environment variables
- **`app/utils/youtube_tools.py`**: YouTubeTools class - video ID extraction, oEmbed calls, transcript fetching with proxy support
- **`app/utils/llm_service.py`**: LLMService - provider abstraction for OpenAI/Anthropic
- **`app/utils/transcript_cache.py`**: TranscriptCache - memory (LRU) or Redis backends

### Prompt Templates (`prompts/`)
Organized by category: `extraction/`, `visualization/`, `review/`, `development/`, `business/`, `ideation/`, `utility/`. Each prompt has a `system.md` and optional `user.md`.

### Cloudflare Edge Cache (`cloudflare-cache-api/`)
Cloudflare Worker that acts as an edge caching layer in front of fast-proxy-api.

```
Client → Cloudflare Edge (KV cache) → fast-proxy-api (upstream)
```

**Stack:** Hono + chanfana (OpenAPI) + D1 + KV + Vitest

```bash
cd cloudflare-cache-api
npm install                              # Install dependencies
npx wrangler d1 create openapi-template-db  # Create D1 database
npx wrangler d1 migrations apply DB --remote # Run migrations
npm run dev                              # Local development (seeds local DB)
npm run test                             # Run Vitest tests
npx wrangler deploy                      # Deploy to Cloudflare
```

**Endpoints:**
| Endpoint | Purpose |
|----------|---------|
| `/youtube/captions?video=...` | Cached captions (KV + edge) |
| `/youtube/metadata?video=...` | Cached metadata (KV + edge) |
| `/youtube/cache/stats` | Cache statistics |
| `/transcripts/*` | Persistent transcript storage (D1) |
| `/tasks/*` | D1 CRUD example |

**Caching:** Checks KV first, then fetches from upstream (`api.youtubesummaries.cc`) and stores with TTL. Response includes `cached: true/false` and `cache_age`.

**D1 Migrations:** Located in `cloudflare-cache-api/migrations/`. Run `npx wrangler d1 migrations apply DB --local` for local dev, `--remote` for production.

## Critical: Proxy Configuration

**YouTube aggressively IP-blocks cloud providers.** Transcript endpoints (`/youtube/captions`, `/youtube/timestamps`) require proxy configuration on Railway/AWS/GCP.

```bash
# .env
PROXY_TYPE=webshare
WEBSHARE_USERNAME=your_username
WEBSHARE_PASSWORD=your_password
```

**Exception**: `/youtube/metadata` uses official oEmbed API and does NOT need proxy.

Verify: `pytest tests/test_proxy.py -v`

## Key Environment Variables

| Variable | Default | Notes |
|----------|---------|-------|
| `LLM_PROVIDER` | openai | "openai" or "anthropic" |
| `OPENAI_API_KEY` | - | Required if using OpenAI |
| `ANTHROPIC_API_KEY` | - | Required if using Anthropic |
| `YOUTUBE_API_KEY` | - | Required for `/youtube/data/*` endpoints |
| `CACHE_BACKEND` | memory | "memory" or "redis" |
| `CACHE_TTL_SECONDS` | 3600 | Cache expiry |
| `RATE_LIMIT_ENABLED` | true | Enable slowapi rate limiting |
| `BACKEND_CORS_ORIGINS` | * | Comma-separated origins |

## API Endpoints

Server: `localhost:8000` (dev) or `https://api.youtubesummaries.cc` (prod). Full docs at `/docs`.

**All endpoints accept query params** (e.g., `?video=URL`) in addition to JSON bodies.

| Endpoint | Proxy? | Notes |
|----------|--------|-------|
| `/youtube/metadata?video=...` | No | oEmbed API |
| `/youtube/captions?video=...` | Yes | Unofficial API |
| `/youtube/timestamps?video=...` | Yes | Unofficial API |
| `/youtube/ai/analyze?video=...&type=summary` | Yes | Requires LLM config |
| `/youtube/data/search?q=...` | No | Requires YOUTUBE_API_KEY |
| `/youtube/data/channel/{id}` | No | Requires YOUTUBE_API_KEY |

## Implementation Details

### Video ID Extraction (`app/utils/youtube_tools.py`)
Handles: standard URLs (`watch?v=`), short URLs (`youtu.be/`), embed URLs (`/embed/`), and plain 11-character IDs.

### Transcript Flow
1. Request to `/youtube/captions` or `/youtube/timestamps`
2. `YouTubeTools._fetch_transcript()` checks cache
3. Cache miss → `YouTubeTranscriptApi` called (with proxy if configured)
4. Blocking call runs via `asyncio.run_in_executor()`
5. Result cached and returned

### Shared HTTP Client
Global `httpx.AsyncClient` initialized in `app/main.py` lifespan. Access via `get_http_client()`.

## Test Fixtures (`tests/conftest.py`)

- `test_client` / `async_test_client` - FastAPI test clients
- `mock_youtube_api` - Patches YouTubeTranscriptApi for offline tests
- `mock_http_client` - Patches httpx client for metadata tests
- `mock_transcript` / `mock_metadata` - Sample data

## Troubleshooting

**"Could not retrieve a transcript"**: YouTube blocking IP. Configure proxy or test locally.

**AI endpoints returning 503**: LLM provider not configured. Check `LLM_PROVIDER` and API key.

**YouTube Data API 403**: `YOUTUBE_API_KEY` missing or quota exceeded.
