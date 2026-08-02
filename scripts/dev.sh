#!/usr/bin/env bash
#
# Run both halves of the application: the FastAPI service and the Next.js client.
#
# The split is real - the API is usable on its own, and the frontend is a client like any
# other - but during development you almost always want both, so this starts them together
# and shuts both down on Ctrl-C.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

if [ ! -d web/node_modules ]; then
  echo "Installing frontend dependencies (first run only)…"
  (cd web && npm install)
fi

cleanup() {
  echo ""
  echo "Shutting down…"
  # Kill the whole process group so Next's child workers go too.
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "API  → http://localhost:${API_PORT}  (docs at /docs)"
echo "Web  → http://localhost:${WEB_PORT}"
echo ""

# The API's CORS allowlist has to know where the client is, or every request dies in
# preflight and the UI reports it as an unreachable service - which reads like the API is
# down rather than like the two halves disagree about the port.
export RLI_CORS_ORIGINS="http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT}"

uv run uvicorn server.app:app --port "${API_PORT}" --reload &
(cd web && NEXT_PUBLIC_API_BASE="http://localhost:${API_PORT}" npm run dev -- --port "${WEB_PORT}") &

wait
