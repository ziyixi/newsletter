# Fake server (Go)

HTTP server that mocks all non-LLM external APIs used by the newsletter backend. Used for integration tests only; no real external services are called.

## Endpoints mocked

| Path | Fixture | Service |
|------|---------|---------|
| `GET /health` | — | Healthcheck |
| `GET /v1/forecast` | weather.json | Open-Meteo (weather) |
| `GET /v0/topstories.json` | hn_topstories.json | Hacker News |
| `GET /v0/item/{1-5}.json` | hn_item_*.json | Hacker News |
| `GET /trending`, `/trending/{lang}` | github_trending.html | GitHub Trending |
| `GET /api/recommendation` | todo.json | Todo API |
| `GET /rss/feed` | rss_feed.xml | News RSS |
| `GET /v8/finance/chart/:symbol` | yahoo_chart.json | Yahoo (stocks & exchange) |
| `GET /api/query?search_query=...` | arxiv_query.xml | arXiv |

## Run locally

```bash
go run .   # port 8080, or FAKE_SERVER_PORT=9090 go run .
```

## Build for Docker

The Dockerfile builds a static binary and runs it; fixtures are embedded at compile time.
