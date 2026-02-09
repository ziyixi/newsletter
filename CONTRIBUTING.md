# Contributing

Thanks for your interest in contributing! This is a personal newsletter project,
but PRs and issues are welcome.

## Development Setup

```bash
# 1. Clone the repo
git clone https://github.com/<your-user>/newsletter.git && cd newsletter

# 2. Install everything
make setup

# 3. Preview with live data
make preview

# 4. Run all linters
make lint
```

## Code Style

| Language   | Tool                | Config                     |
| ---------- | ------------------- | -------------------------- |
| TypeScript | `tsc --noEmit`      | `tsconfig.json`            |
| Python     | `ruff` + `mypy`     | `pyproject.toml`           |
| Proto      | `buf lint`          | `protos/buf.yaml`          |

Run `make lint` before submitting a PR — CI enforces all three.

## Adding a New Section

1. Add an entry to `newsletter.config.yaml` → `sections`
2. Create a component in `packages/email-service/emails/components/`
3. Register it in `packages/email-service/emails/section-registry.tsx`
4. Add data types in `emails/types.ts` and a backend service in `packages/backend/src/services/`
5. Run `make sync-config` then `make preview` to verify
