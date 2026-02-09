#!/usr/bin/env bash
set -euo pipefail

cd /app

case "${1:-send}" in
  fetch)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && uv run python -m src.fetch
    ;;

  render)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && uv run python -m src.fetch
    echo "🎨  Rendering newsletter…"
    cd /app && yarn workspace email-service e2e
    ;;

  send)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && uv run python -m src.fetch
    echo "📨  Rendering and sending newsletter…"
    cd /app && yarn workspace email-service send:real
    ;;

  e2e)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && uv run python -m src.fetch
    echo "🧪  Running E2E validation (no email sent)…"
    cd /app && yarn workspace email-service e2e
    echo "✅  E2E test passed"
    ;;

  lint)
    echo "🔍  Running all linters…"
    cd /app && make lint
    ;;

  *)
    echo "Usage: docker run newsletter [fetch|render|send|e2e|lint]"
    exit 1
    ;;
esac
