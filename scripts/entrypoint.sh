#!/usr/bin/env bash
set -euo pipefail

cd /app

case "${1:-send}" in
  fetch)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && newsletter
    ;;

  render)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && newsletter
    echo "🎨  Rendering newsletter…"
    cd /app && email-service e2e
    ;;

  send)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && newsletter
    echo "📨  Rendering and sending newsletter…"
    cd /app && email-service send
    ;;

  e2e)
    echo "📥  Fetching newsletter data…"
    cd packages/backend && newsletter
    echo "🧪  Running E2E validation (no email sent)…"
    cd /app && email-service e2e
    echo "✅  E2E test passed"
    ;;

  *)
    echo "Usage: docker run newsletter [fetch|render|send|e2e]"
    exit 1
    ;;
esac
