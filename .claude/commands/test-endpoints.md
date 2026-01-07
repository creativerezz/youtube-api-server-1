# Test API Endpoints

Test all API endpoints for the FastYouTubeProxy server.

## Instructions

1. Start the server if not running:
   ```bash
   source .venv/bin/activate
   HOST=0.0.0.0 PORT=8000 python -m app.main &
   ```

2. Test all endpoints using the test video `dQw4w9WgXcQ` (Rick Astley - Never Gonna Give You Up):

### Core Endpoints
- `GET /health` - Health check
- `GET /` - Root/API info
- `GET /service/status` - Full service status

### YouTube Endpoints
- `GET /youtube/metadata?video=dQw4w9WgXcQ` - Video metadata (oEmbed)
- `GET /youtube/captions?video=dQw4w9WgXcQ&languages=en` - Plain text captions
- `GET /youtube/timestamps?video=dQw4w9WgXcQ&languages=en` - Timestamped captions
- `GET /youtube/cache/stats` - Cache statistics

### YouTube Data API (requires YOUTUBE_API_KEY)
- `GET /youtube/data/search?q=test&max_results=3` - Search videos
- `GET /youtube/data/channel/{channel_id}` - Channel info

3. Report results in a table showing endpoint, status (pass/fail), and response summary.

4. If any endpoint fails, investigate and report the error.

## Expected Behavior
- All endpoints should return valid JSON (except captions which returns quoted text)
- Health should return `{"status":"healthy"}`
- Metadata should include title, author_name, thumbnail_url
- Captions/timestamps require working transcript API (may fail if YouTube blocks IP)
