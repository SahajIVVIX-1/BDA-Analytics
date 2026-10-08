#!/usr/bin/env bash
# Start the API (port 8000) and the dashboard (port 5173) together. Ctrl+C stops both.
# Assumes MongoDB is running and backend/.venv exists (see README).
set -euo pipefail
cd "$(dirname "$0")/.."
( cd backend && .venv/bin/uvicorn app.main:app --reload --reload-dir app ) &
API=$!
trap 'kill $API 2>/dev/null' EXIT
cd frontend && npm run dev
