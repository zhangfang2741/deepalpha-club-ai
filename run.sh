#claude --dangerously-skip-permissions
uv run uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev