#!/usr/bin/env bash
# Start both the FastAPI backend and React frontend dev servers.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT="${API_PORT:-8800}"

for venv_dir in .venv venv; do
  if [ -f "$ROOT/$venv_dir/bin/activate" ]; then
    # shellcheck source=/dev/null
    source "$ROOT/$venv_dir/bin/activate"
    break
  fi
done

echo "Starting API on http://127.0.0.1:${API_PORT}"
cd "$ROOT"
python3 -m uvicorn api.main:app --reload --port "$API_PORT" &
API_PID=$!

echo "Starting frontend on http://127.0.0.1:5173 (proxying /api -> :${API_PORT})"
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  echo "Installing frontend dependencies..."
  npm install
fi
npm run dev &
WEB_PID=$!

trap "kill $API_PID $WEB_PID 2>/dev/null" EXIT
wait
