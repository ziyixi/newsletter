# 每日简报 — Daily Newsletter

A personal daily newsletter that curates content from multiple sources and delivers a beautifully formatted email every morning.

## Architecture

```mermaid
flowchart LR
    Backend[Go backend] --> JSON[JSON file]
    JSON --> Email[Email service]
    Email --> Resend[Resend API]
```

| Package | Language | Purpose |
|---------|----------|---------|
| `packages/backend` | Go 1.24 + Protobuf | Fetches, ranks, and batch-translates content |
| `packages/email-service` | TypeScript (Node 20) | Renders React Email templates and sends via Resend |

They communicate through a **JSON file** — the backend writes it (via `protojson`), the email-service reads it.

## Content Sources

| Section | Source | API Key? |
|---------|--------|----------|
| Weather | Open-Meteo | No |
| Astronomy | `go-sunrise` | No |
| Top News | RSS feeds + Gemini batch translation | Yes (`GEMINI_API_KEY`) |
| Hacker News | Firebase API + Gemini batch translation | Yes (`GEMINI_API_KEY`) |
| Stocks | Yahoo Finance HTTP API | No |
| Exchange Rates | Yahoo Finance HTTP API | No |
| GitHub Trending | HTML scraping + Gemini batch translation | Yes (`GEMINI_API_KEY`) |
| arXiv Papers | arXiv Atom API + Gemini | Yes (`GEMINI_API_KEY`) |
| Todo Tasks | daily.ziyixi.science | Yes (`TODO_API_*`) |

## Quick Start

```bash
# 1. Install dependencies
make setup

# 2. Configure secrets
cp .env.example .env   # edit with your API keys

# 3. Preview in browser (fetches real data)
make preview

# 4. Send the newsletter
make send
```

## Configuration

All settings live in **`newsletter.config.yaml`** — a single source of truth for both packages.

Secrets go in **`.env`** (local) or **GitHub Secrets** (CI):

```
RESEND_API_KEY=re_...
RECIPIENT_EMAIL=you@example.com
RECIPIENT_NAME=Ziyi
GEMINI_API_KEY=AIza...
TODO_API_USER=...
TODO_API_PASSWORD=...
```

Gemini uses the stable `gemini-3.8-flash` model for ranking, translation, and
arXiv summarisation. News, Hacker News, and GitHub candidates are ranked in
English first; only selected items are translated in one structured-output
request. The backend validates every response ID and retries only missing or
invalid fields. A failed field remains in English instead of failing the run.
Use `GEMINI_MODEL` to override the model configured under `arxiv.geminiModel`.
The automatic fallbacks are `gemini-3.7-flash` and `gemini-3.5-flash-lite`.

## Development

```bash
# React Email dev server (hot reload)
make dev-email

# Run all linters (TypeScript + Go)
make lint

# Fetch data only (without sending; generates proto if needed)
make fetch

# Run integration tests (Docker Compose)
make test
```

## Testing

Go unit tests cover structured translation parsing, ID validation, and
missing-field retry behavior without calling Gemini. Integration tests use
**mocks only**: Docker Compose runs a Go fake server (`tests/fake-server/`)
that implements the non-LLM external endpoints with canned responses. No real
external services are called.

```bash
make test
# → docker compose -f docker-compose.test.yml up --build ...
```

Run just the offline Go tests with `make test-go`. To explicitly test the
configured primary Gemini model using your local `.env` (API usage is billed,
and no email is sent):

```bash
cd packages/backend
RUN_GEMINI_INTEGRATION=1 go test ./internal/service -run TestGeminiStructuredTranslationIntegration -count=1 -v
```

This opt-in test disables fallback models and checks response IDs, Chinese
text, URL/code preservation, and translation of text containing instructions.

The backend points to the fake server via environment variables
(`WEATHER_API_BASE`, `YAHOO_CHART_BASE`, `ARXIV_API_BASE`, etc.) and disables
Gemini in the integration environment. See `docker-compose.test.yml` for the
full list.

## Docker

The image contains two binaries: the **Go backend** (`newsletter`) and the **Node.js email-service** as a **single executable** (Node SEA). The final stage uses **Debian Bookworm Slim** (minimal glibc base)—no Node.js runtime or `node_modules` in the image.

```bash
# Build
docker build -t newsletter .

# Send
docker run -e RESEND_API_KEY=... -e RECIPIENT_EMAIL=... newsletter send

# E2E validation (no email sent)
docker run newsletter e2e
```

## Project Structure

```mermaid
flowchart TB
    subgraph backend["packages/backend (Go)"]
        Proto[proto/newsletter.proto]
        CMD[cmd/newsletter]
        Internal[internal/config, fetcher, service]
    end

    subgraph email["packages/email-service (TypeScript)"]
        Template[emails/newsletter.tsx]
        Scripts[src: send, e2e, preview, cli]
    end

    Root[newsletter.config.yaml, Makefile, Dockerfile] --> backend
    Proto --> Internal
    CMD --> Internal
    Internal --> Template
```

## License

MIT
