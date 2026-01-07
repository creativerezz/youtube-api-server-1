# Quick Test

Run a quick automated test of the API server.

## Instructions

1. Check if server is running on localhost:8000, if not start it:
   ```bash
   source .venv/bin/activate && HOST=0.0.0.0 PORT=8000 python -m app.main &
   ```
   Wait 3 seconds for startup.

2. Run these curl commands and collect results:
   ```bash
   curl -s http://localhost:8000/health
   curl -s http://localhost:8000/youtube/metadata?video=dQw4w9WgXcQ
   curl -s "http://localhost:8000/youtube/captions?video=dQw4w9WgXcQ" | head -c 200
   ```

3. Report pass/fail for each endpoint in a concise table.

4. Kill the server when done if you started it.
