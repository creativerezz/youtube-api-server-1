# Run Tests

Run the pytest test suite.

## Instructions

1. Activate the virtual environment and run pytest:
   ```bash
   source .venv/bin/activate && pytest -v
   ```

2. If tests fail, analyze the output and suggest fixes.

3. For specific test files:
   - Unit tests: `pytest tests/test_unit.py -v`
   - Proxy tests: `pytest tests/test_proxy.py -v`
   - Live server tests: `pytest tests/test_live_server.py -v` (requires running server)

4. Report a summary of passed/failed tests.
