.PHONY: setup setup-frontend setup-backend \
        fetch preview send \
        dev-email test-send clean \
        lint lint-ts lint-py \
        e2e test docker-build docker-send

# ═══════════════════════════════════════════════
# Quick-start workflow:
#   make setup          ← one-time install
#   make preview        ← fetch real data → render → open in browser
#   make send           ← send the newsletter via Resend
#   make lint           ← run all linters (TS + Python)
#   make test           ← integration test (Docker Compose)
# ═══════════════════════════════════════════════

# ─── Setup ──────────────────────────────────

setup: setup-frontend setup-backend
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

# ─── Fetch / Preview / Send ─────────────────

fetch:
	@echo "🔄  Fetching real data from all services…"
	cd packages/backend && uv run python -m src.main

preview: fetch
	@echo "🌐  Rendering and opening preview…"
	yarn workspace email-service preview

send: fetch
	@echo "📨  Rendering and sending newsletter…"
	yarn workspace email-service send

# ─── Development helpers ────────────────────

dev-email:
	yarn workspace email-service dev:email

test-send:
	yarn workspace email-service send:test

# ─── Cleanup ────────────────────────────────

clean:
	rm -rf packages/backend/.cache
	rm -rf packages/email-service/dist
	rm -rf .cache

# ─── Linting ────────────────────────────────

lint: lint-ts lint-py
	@echo ""
	@echo "✅  All linters passed"

lint-ts:
	@echo "🔍  TypeScript…"
	cd packages/email-service && npx tsc --noEmit

lint-py:
	@echo "🔍  Python (ruff)…"
	cd packages/backend && uv run ruff check src/
	@echo "🔍  Python (mypy)…"
	cd packages/backend && uv run mypy src/ --ignore-missing-imports

# ─── E2E Test ───────────────────────────────

e2e: sync-config fetch
	@echo "🧪  Running E2E validation…"
	yarn workspace email-service e2e

# ─── Integration Test (Docker Compose) ──────

test:
	@echo "🧪  Running integration tests with Docker Compose…"
	docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from newsletter
	docker compose -f docker-compose.test.yml down -v

# ─── Docker ─────────────────────────────────

docker-build:
	docker build -t newsletter .

docker-send: docker-build
	@echo "📨  Sending newsletter via Docker…"
	docker run --rm \
		-e RESEND_API_KEY=$${RESEND_API_KEY} \
		-e RECIPIENT_EMAIL=$${RECIPIENT_EMAIL} \
		-e GEMINI_API_KEY=$${GEMINI_API_KEY} \
		-e TODO_API_USER=$${TODO_API_USER} \
		-e TODO_API_PASSWORD=$${TODO_API_PASSWORD} \
		newsletter send
