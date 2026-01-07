# AGENTS.md

> [!IMPORTANT]
> This file is the primary source of truth for AI agents working on this project.

## Project Summary
FastAPI-based server ("FastYTProxie") for extracting YouTube video data, including metadata, captions, and timestamps. It acts as a middleware between clients and YouTube's internal APIs/oEmbed services, featuring robust proxy support to bypass IP restrictions.

## Critical Non-Obvious Information

### Proxy Configuration (CRITICAL)
- **YouTube Blocking**: `youtube-transcript-api` utilizes unofficial methods that are aggressively IP-blocked by YouTube on cloud providers (AWS, GCP, etc.).
- **Requirement**: You **MUST** configure proxy settings for `/youtube/captions` and `/youtube/timestamps`.
- **Method**: Set `PROXY_TYPE=webshare` with `WEBSHARE_USERNAME` and `WEBSHARE_PASSWORD` in `.env`.
- **Exception**: `/youtube/metadata` uses the official YouTube oEmbed API and **does NOT** require a proxy.

### API Implementation
- **Query Parameters**: All endpoints accept plain query parameters (e.g., `?video=URL`) in addition to JSON bodies. This is often preferred for simple GET-like behavior.
- **Entry Point**: The application entry point is `app.main`. Run with `python -m app.main`.
- **CORS Handling**: `BACKEND_CORS_ORIGINS` env var is parsed via `split(",")` with `.strip()`. Supports `*` for development.

### Deployment & Environment
- **Railway**: Deploys via `Procfile`. `PORT` is auto-set by Railway. Host must be `0.0.0.0`.
- **Docker**: `docker-compose up` is supported for containerized running.

## Project Structure

```text
FastYTProxie/
├── app/
│   ├── main.py            # Application entry point & FastAPI app definition
│   ├── routes/            # API Route handlers (/youtube, /service)
│   ├── utils/             # Core logic (youtube_tools.py)
│   └── models/            # Pydantic data models
├── chrome-extension/      # Companion Chrome extension source
├── tests/                 # Pytest suite (located at root, NOT in app/)
├── AGENTS.md              # This file
├── FRONTEND_TIPS.md       # Comprehensive frontend integration guide
└── requirements.txt       # Python dependencies
```

## Development Workflow

### Running Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Run server (Reload enabled in dev usually)
python -m app.main
```

### Testing
Tests are located in `tests/`.
```bash
# Run all tests
pytest

# Run specific test
pytest tests/test_file.py::test_function_name -v

# Run proxy check
python test_proxy.py
```

### Documentation
- **API Docs**: Available at `/docs` (Swagger) and `/redoc` when running.
- **Frontend**: See `FRONTEND_TIPS.md` for integration patterns.