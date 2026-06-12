# FastAPI dev server, auto-restarts on changes in highliner/
dev:
    uv run uvicorn highliner.api:app --reload --reload-dir highliner --host 127.0.0.1 --port 8000

# run the test suite
test:
    uv run pytest

# download + transform protected-area boundaries into data/restrictions/
fetch-restrictions:
    uv run python -m highliner.restrictions
