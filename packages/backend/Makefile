# Backend Makefile — development helpers

.PHONY: sync run lint clean

# ─── uv package management ──────────────────

sync:
	uv sync

run:
	uv run python -m src.main

# ─── Linting ────────────────────────────────

lint:
	uv run ruff check src/
	uv run mypy src/ --ignore-missing-imports

# ─── Cleanup ────────────────────────────────

clean:
	rm -rf .cache
	@echo "🧹  Cleaned backend cache"
