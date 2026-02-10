.PHONY: setup setup-frontend setup-backend \
        sync-config fetch preview send \
        dev-email dev-server backend-run backend-test \
        proto-py test-send clean \
        lint lint-ts lint-py lint-proto \
        e2e test-arxiv docker-build docker-e2e docker-send

# ═══════════════════════════════════════════════
# Quick-start workflow:
#   make setup          ← one-time install
#   make preview        ← fetch real data → render → open in browser
#   make send           ← send the previewed newsletter via Resend
#   make lint           ← run all linters (TS + Python + Proto)
#   make e2e            ← end-to-end test (fetch + render, no send)
# ═══════════════════════════════════════════════

# ─── Setup ──────────────────────────────────

setup: setup-frontend setup-backend sync-config
	@echo ""
	@echo "✅  All set up! Next steps:"
	@echo "    make preview   — fetch real data and preview in browser"
	@echo "    make send      — send the newsletter for real"
	@echo "    make lint      — run all linters"
	@echo ""

setup-frontend:
	@echo "📦  Installing Node.js dependencies…"
	yarn install

setup-backend:
	@echo "🐍  Installing Python dependencies…"
	cd packages/backend && uv sync
	@echo "🔧  Generating proto stubs…"
	$(MAKE) proto-py

# ─── Sync Config ────────────────────────────

sync-config:
	@node scripts/sync-config.mjs

# ─── Fetch / Preview / Send ─────────────────

fetch:
	@echo "🔄  Fetching real data from all services…"
	cd packages/backend && uv run python -m src.fetch

preview: sync-config fetch
	@echo "🌐  Rendering and opening preview…"
	yarn workspace email-service preview

send: sync-config fetch
	@echo "📨  Rendering and sending newsletter…"
	yarn workspace email-service send:real

# ─── Development helpers ────────────────────

dev-email:
	yarn workspace email-service dev:email

dev-server:
	yarn workspace email-service dev:server

test-send:
	yarn workspace email-service send:test

backend-run:
	cd packages/backend && uv run python -m src.main

backend-test:
	@echo "Testing all backend services…"
	cd packages/backend && uv run python -c "\
from src.services import *; \
import json; \
w = fetch_weather(); print('✅ Weather:', w['condition']); \
n = fetch_news(); print(f'✅ News: {len(n)} items'); \
s = fetch_stocks(); print(f'✅ Stocks: {len(s)} tickers'); \
h = fetch_hn_stories(); print(f'✅ HN: {len(h)} stories'); \
a = fetch_astronomy(); print('✅ Astronomy:', a['sunrise'], '-', a['sunset']); \
print(); print('All services OK ✅')"

proto-py:
	$(MAKE) -C packages/backend proto

# ─── Cleanup ────────────────────────────────

clean:
	$(MAKE) -C packages/backend clean
	rm -rf packages/email-service/dist
	rm -rf .cache packages/backend/.cache

# ─── Linting ────────────────────────────────

lint: lint-ts lint-py lint-proto
	@echo ""
	@echo "✅  All linters passed"

lint-ts: sync-config
	@echo "🔍  TypeScript…"
	cd packages/email-service && npx tsc --noEmit

lint-py:
	@echo "🔍  Python (ruff)…"
	cd packages/backend && uv run ruff check src/
	@echo "🔍  Python (mypy)…"
	cd packages/backend && uv run mypy src/ --ignore-missing-imports

lint-proto:
	@echo "🔍  Proto (buf)…"
	@command -v buf >/dev/null 2>&1 && cd protos && buf lint || \
		echo "   ⚠️  buf not installed — skipping proto lint (install: https://buf.build/docs/installation)"

# ─── E2E Test ───────────────────────────────

test-arxiv:
	@echo "🧪  Running arXiv E2E test…"
	cd packages/backend && uv run python tests/test_arxiv_e2e.py

e2e: sync-config fetch
	@echo "🧪  Running E2E validation…"
	yarn workspace email-service e2e

# ─── Docker ─────────────────────────────────

docker-build:
	docker build -t newsletter .

docker-e2e: docker-build
	docker run --rm newsletter e2e

docker-send: docker-build
	@echo "📨  Sending newsletter via Docker…"
	docker run --rm \
		-e RESEND_API_KEY=$${RESEND_API_KEY} \
		-e RECIPIENT_EMAIL=$${RECIPIENT_EMAIL} \
		newsletter send
