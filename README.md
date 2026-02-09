<h1 align="center">📰 每日简报 — Daily Briefing Newsletter</h1>

<p align="center">
  A fully automated, self-hosted Chinese-language morning newsletter<br>
  delivered to your inbox every day at 8 AM.
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#configuration">Configuration</a> •
  <a href="#secrets--api-keys">Secrets</a> •
  <a href="#docker">Docker</a> •
  <a href="#github-actions">GitHub Actions</a>
</p>

---

## What It Does

Every morning, the newsletter:

1. **Fetches** live data — weather, world news, Hacker News, stock prices, astronomy
2. **Translates** headlines and summaries to Chinese (Google Translate)
3. **Renders** a beautiful HTML email using React Email (calligraphy fonts, warm ivory paper, NYT-style layout)
4. **Sends** the email via [Resend](https://resend.com)

All content sources are **free and keyless** (Open-Meteo, RSS, yfinance, HN Firebase) — the only API key required is Resend for email delivery.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    newsletter.config.yaml                │
│              (single source of truth for all settings)   │
└──────────────┬──────────────────────┬───────────────────┘
               │  sync-config.mjs     │  config.py reads
               ▼                      ▼
┌──────────────────────────┐  ┌───────────────────────────┐
│   packages/email-service │  │    packages/backend       │
│   (Node.js / TypeScript) │  │    (Python / uv)          │
│                          │  │                           │
│  ┌────────────────────┐  │  │  ┌─────────────────────┐  │
│  │  React Email        │  │  │  │  Service Layer      │  │
│  │  Components (TSX)   │  │  │  │                     │  │
│  │                     │  │  │  │  • weather (meteo)  │  │
│  │  • header           │  │  │  │  • news (RSS)       │  │
│  │  • weather          │  │  │  │  • stocks (yfinance)│  │
│  │  • top-news         │  │  │  │  • hn (Firebase)    │  │
│  │  • hacker-news      │  │  │  │  • astronomy        │  │
│  │  • stocks           │  │  │  │  • translator       │  │
│  │  • footer           │  │  │  └─────────┬───────────┘  │
│  └────────┬───────────┘  │  │            │               │
│           │ render       │  │            │ fetch          │
│           ▼              │  │            ▼               │
│  ┌────────────────────┐  │  │  ┌─────────────────────┐  │
│  │  @react-email/render│  │  │  │  fetch.py → JSON    │  │
│  │  → HTML string      │  │  │  │  main.py → gRPC     │  │
│  └────────┬───────────┘  │  │  └─────────┬───────────┘  │
│           │              │  │            │               │
│           ▼              │  │            │               │
│  ┌────────────────────┐  │  │            │               │
│  │  Resend API         │  │  │            │               │
│  │  → Email delivery   │  │  │            │               │
│  └────────────────────┘  │  │            │               │
└──────────────────────────┘  └────────────┘───────────────┘
                                           │
              ┌────────────────────────────┘
              ▼
     .cache/newsletter-data.json
     (intermediate data, gitignored)
```

**Two delivery paths:**

| Path | Command | Flow |
|------|---------|------|
| **Preview** (local dev) | `make preview` | Python fetches → JSON → Node renders → opens in browser |
| **Send** (production) | `make send` | Python fetches → JSON → Node renders → Resend API → inbox |

---

## Quick Start

### Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| **Node.js** | ≥ 20 | [nodejs.org](https://nodejs.org) |
| **Yarn** | ≥ 1.22 | `npm install -g yarn` |
| **Python** | ≥ 3.11 | [python.org](https://python.org) |
| **uv** | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

### Install & Preview

```bash
# 1. Clone
git clone https://github.com/<your-user>/newsletter.git
cd newsletter

# 2. Install all dependencies (Node + Python + proto stubs)
make setup

# 3. Fetch live data and open a preview in the browser
make preview
```

### Send a Real Email

```bash
# 4. Copy the example env file and add your Resend API key
cp .env.example .env
# Edit .env → set RESEND_API_KEY and RECIPIENT_EMAIL

# 5. Copy .env into the email-service package too
cp .env packages/email-service/.env

# 6. Send!
make send
```

---

## Configuration

All settings live in **one file**: [`newsletter.config.yaml`](newsletter.config.yaml)

YAML was chosen over JSON because it supports **comments** — making it easy to document each setting inline.

```yaml
# Change your location
weather:
  latitude: 37.3688
  longitude: -122.0363
  location: "圣尼维尔，加州"

# Add or remove stocks
stocks:
  symbols: [AAPL, GOOGL, MSFT, TSLA, NVDA]

# Reorder or remove newsletter sections
sections:
  - id: header
  - id: weather
  - id: top-news
  # - id: hacker-news   ← comment out to remove
  - id: stocks
  - id: footer
```

After editing, run `make sync-config` (or just `make preview` — it syncs automatically).

---

## Secrets & API Keys

> **Rule:** Secrets are NEVER stored in the config file or committed to git.

### Local Development

Create a `.env` file in the project root (and/or `packages/email-service/.env`):

```bash
cp .env.example .env
```

Then fill in:

```dotenv
# Required — get yours at https://resend.com/api-keys
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Required — delivery address
RECIPIENT_EMAIL=you@example.com
```

### GitHub Actions

Add these as **Repository Secrets** in your GitHub repo:

1. Go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Add each:

| Secret Name | Description | Required |
|------------|-------------|----------|
| `RESEND_API_KEY` | Resend API key for email delivery | Yes |
| `RECIPIENT_EMAIL` | Email address to receive the newsletter | Yes |

The CI workflow reads these automatically — no code changes needed.

### Environment Variable Reference

All settings from `newsletter.config.yaml` can be overridden via environment variables:

| Env Var | Overrides | Default |
|---------|-----------|---------|
| `RESEND_API_KEY` | — | *(none, required for send)* |
| `RECIPIENT_EMAIL` | `recipient.email` | `you@example.com` |
| `RECIPIENT_NAME` | `recipient.name` | `子逸` |
| `WEATHER_LAT` | `weather.latitude` | `37.3688` |
| `WEATHER_LON` | `weather.longitude` | `-122.0363` |
| `WEATHER_LOCATION` | `weather.location` | `圣尼维尔，加州` |
| `NEWS_FEEDS` | `news.feeds` (comma-separated) | *(5 feeds)* |
| `NEWS_MAX_ITEMS` | `news.maxItems` | `5` |
| `STOCK_SYMBOLS` | `stocks.symbols` (comma-separated) | `AAPL,GOOGL,...` |
| `HN_MAX_STORIES` | `hackerNews.maxStories` | `5` |
| `TIMEZONE` | `schedule.timezone` | `America/Los_Angeles` |
| `GRPC_PORT` | `grpc.port` | `50051` |

---

## Docker

```bash
# Build the image
make docker-build

# Run E2E test (fetch + render, no email sent)
make docker-e2e

# Send the newsletter
RESEND_API_KEY=re_xxx RECIPIENT_EMAIL=you@example.com make docker-send
```

Or use the Docker CLI directly:

```bash
docker build -t newsletter .
docker run --rm newsletter e2e                          # validate
docker run --rm -e RESEND_API_KEY=... newsletter send   # send
```

---

## GitHub Actions

Two workflows are included:

### CI — Lint & E2E ([`.github/workflows/ci.yml`](.github/workflows/ci.yml))

Runs on every push/PR to `main`:

1. **Lint** — TypeScript (`tsc`), Python (`ruff` + `mypy`), Proto (`buf`)
2. **E2E** — Fetch live data → render → validate HTML output
3. **Docker** — Build & push image to GHCR (on main branch only)

### Daily Send ([`.github/workflows/daily.yml`](.github/workflows/daily.yml))

Runs every day at **8 AM PST** (16:00 UTC) via cron:

- Pulls the latest Docker image from GHCR
- Runs `newsletter send` with secrets from GitHub

Can also be triggered manually via **Actions → Daily Newsletter → Run workflow**.

---

## Available Make Targets

```
make setup          Install all dependencies
make preview        Fetch → render → open in browser
make send           Fetch → render → send via Resend
make lint           Run all linters (TS + Python + Proto)
make e2e            End-to-end test (no email sent)
make fetch          Fetch data only (saves to JSON)
make sync-config    Regenerate template-config.ts from YAML
make docker-build   Build Docker image
make docker-e2e     Run E2E in Docker
make docker-send    Send newsletter via Docker
make clean          Remove caches and build artifacts
```

---

## Project Structure

```
newsletter/
├── newsletter.config.yaml     ← All settings (edit this!)
├── .env.example               ← Secrets template
├── Makefile                   ← All commands
├── Dockerfile                 ← Multi-runtime image
├── protos/
│   └── newsletter.proto       ← gRPC schema
├── scripts/
│   ├── sync-config.mjs        ← YAML → TypeScript codegen
│   └── entrypoint.sh          ← Docker entrypoint
├── packages/
│   ├── email-service/         ← Node.js / TypeScript
│   │   ├── emails/
│   │   │   ├── newsletter.tsx         ← Main template
│   │   │   ├── components/            ← Section components
│   │   │   ├── fixtures/fake-data.ts  ← Preview data
│   │   │   ├── template-config.ts     ← (auto-generated)
│   │   │   ├── section-registry.tsx   ← Section → component map
│   │   │   └── types.ts              ← TypeScript interfaces
│   │   └── src/
│   │       ├── preview.ts     ← Local preview script
│   │       ├── send-real.ts   ← Production send script
│   │       ├── e2e.ts         ← E2E validation
│   │       ├── render.ts      ← React Email → HTML
│   │       └── server.ts      ← gRPC server
│   └── backend/               ← Python / uv
│       ├── src/
│       │   ├── config.py      ← Reads YAML + env vars
│       │   ├── fetch.py       ← Data → JSON pipeline
│       │   ├── main.py        ← Orchestrator
│       │   └── services/      ← Data fetchers
│       │       ├── weather_service.py
│       │       ├── news_service.py
│       │       ├── stocks_service.py
│       │       ├── hn_service.py
│       │       ├── astronomy_service.py
│       │       └── translator.py
│       └── generated/         ← Proto stubs (gitignored)
└── .github/workflows/
    ├── ci.yml                 ← Lint + E2E + Docker
    └── daily.yml              ← 8 AM cron send
```

---

## License

[MIT](LICENSE) — Ziyi Xi
