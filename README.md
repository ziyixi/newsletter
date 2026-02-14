# 📰 每日简报 — Daily Newsletter

A personal daily newsletter that curates content from multiple sources and delivers a beautifully formatted email every morning.

## Architecture

```
Python backend          Node.js email-service
(fetch data)     →      (render + send)
      │                       │
      ▼                       ▼
  JSON file             React Email → Resend
```

The system is split into two packages:

| Package | Language | Purpose |
|---------|----------|---------|
| `packages/backend` | Python 3.12 | Fetches data from external APIs in parallel |
| `packages/email-service` | TypeScript (Node 20) | Renders React Email templates and sends via Resend |

They communicate through a **JSON file** — the backend writes it, the email-service reads it.

## Content Sources

| Section | Source | API Key? |
|---------|--------|----------|
| 🌤 Weather | Open-Meteo | No |
| 🌅 Astronomy | `astral` library | No |
| 📰 Top News | RSS feeds + Google Translate | No |
| 🔥 Hacker News | Firebase API + Google Translate | No |
| 📈 Stocks | yfinance | No |
| 💱 Exchange Rates | yfinance | No |
| 🐙 GitHub Trending | HTML scraping + Google Translate | No |
| 📄 arXiv Papers | arxiv API + Gemini | Yes (`GEMINI_API_KEY`) |
| ✅ Todo Tasks | daily.ziyixi.science | Yes (`TODO_API_*`) |

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

## Development

```bash
# React Email dev server (hot reload)
make dev-email

# Run all linters (TypeScript + Python)
make lint

# Fetch data only (without sending)
make fetch

# Run integration tests (Docker Compose)
make test
```

## Testing

Integration tests use Docker Compose with a **fake server** that returns canned responses for all external APIs:

```bash
make test
# → docker compose -f docker-compose.test.yml up --build ...
```

The fake server lives in `tests/fake-server/` with fixture files for each API endpoint.

Backend services support configurable base URLs via environment variables (`WEATHER_API_BASE`, `HN_API_BASE`, etc.) and skip flags (`SKIP_STOCKS=true`) for services that use Python libraries instead of HTTP.

## Docker

```bash
# Build
docker build -t newsletter .

# Send
docker run -e RESEND_API_KEY=... -e RECIPIENT_EMAIL=... newsletter send

# E2E validation (no email sent)
docker run newsletter e2e
```

## Project Structure

```
newsletter/
├── newsletter.config.yaml     # All configurable settings
├── Makefile                    # Development commands
├── Dockerfile                  # Multi-runtime image (Python + Node)
├── docker-compose.test.yml     # Integration test with fake server
├── packages/
│   ├── backend/                # Python — data fetching
│   │   └── src/
│   │       ├── main.py         # Orchestrator (parallel fetch → JSON)
│   │       ├── config.py       # YAML + env var configuration
│   │       └── services/       # One module per content source
│   └── email-service/          # TypeScript — rendering & sending
│       ├── emails/
│       │   ├── newsletter.tsx  # Main template (config-driven layout)
│       │   ├── types.ts        # Shared TypeScript interfaces
│       │   ├── section-registry.tsx
│       │   ├── template-config.ts
│       │   ├── components/     # One component per section
│       │   └── fixtures/       # Fake data for dev preview
│       └── src/
│           ├── send-real.ts    # Render + send via Resend
│           ├── e2e.ts          # E2E validation (no send)
│           └── preview.ts      # HTML preview
├── tests/
│   └── fake-server/            # Mock HTTP server for testing
│       ├── server.py
│       ├── Dockerfile
│       └── fixtures/           # Canned API responses
├── scripts/
│   └── entrypoint.sh           # Docker entrypoint
└── .github/workflows/
    ├── ci.yml                  # Lint + integration test
    └── daily.yml               # Scheduled newsletter send
```

## License

MIT
