#!/usr/bin/env bash
# Start both the FastAPI backend and React frontend dev servers.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Starting API on http://127.0.0.1:8000"
cd "$ROOT"
python3 -m uvicorn api.main:app --reload --port 8000 &
API_PID=$!

echo "Starting frontend on http://127.0.0.1:5173"
cd "$ROOT/frontend"
npm run dev &
WEB_PID=$!

trap "kill $API_PID $WEB_PID 2>/dev/null" EXIT
wait
