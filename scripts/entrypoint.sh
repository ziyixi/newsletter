#!/usr/bin/env bash
set -euo pipefail

cd /app

case "${1:-send}" in
  fetch)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && uv run python -m src.main
    ;;

  render)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && uv run python -m src.main
    echo "🎨  Rendering newsletter…"
    cd /app && yarn workspace email-service e2e
    ;;

  send)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && uv run python -m src.main
    echo "📨  Rendering and sending newsletter…"
    cd /app && yarn workspace email-service send
    ;;

  e2e)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && uv run python -m src.main
    echo "🧪  Running E2E validation (no email sent)…"
    cd /app && yarn workspace email-service e2e
    echo "✅  E2E test passed"
    ;;

  *)
    echo "Usage: docker run newsletter [fetch|render|send|e2e]"
    exit 1
    ;;
esac
