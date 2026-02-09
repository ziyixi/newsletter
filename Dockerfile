# ─────────────────────────────────────────────
# Newsletter — multi-runtime Docker image
# Python 3.12 (backend) + Node.js 20 (email-service)
#
# Build:  docker build -t newsletter .
# Run:    docker run -e RESEND_API_KEY=... -e RECIPIENT_EMAIL=... newsletter send
# E2E:    docker run newsletter e2e
# ─────────────────────────────────────────────

# ── Stage 1: Node.js dependency install ──────
FROM node:20-slim AS node-deps
WORKDIR /app
COPY package.json yarn.lock ./
COPY packages/email-service/package.json packages/email-service/
RUN yarn install --frozen-lockfile --production=false

# ── Stage 2: Final image ────────────────────
FROM python:3.12-slim

# Install Node.js 20
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates make && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g yarn && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# ── Node.js dependencies (from stage 1) ─────
COPY --from=node-deps /app/node_modules ./node_modules
COPY --from=node-deps /app/packages/email-service/node_modules ./packages/email-service/node_modules

# ── Python dependencies ─────────────────────
COPY packages/backend/pyproject.toml packages/backend/uv.lock packages/backend/
RUN cd packages/backend && uv sync --no-dev

# ── Copy all source files ───────────────────
COPY . .

# ── Build steps ─────────────────────────────
# Sync template config from root YAML
RUN node scripts/sync-config.mjs

# Generate proto stubs
RUN cd packages/backend && mkdir -p generated && \
    uv run python -m grpc_tools.protoc \
      -I../../protos \
      --python_out=generated \
      --pyi_out=generated \
      --grpc_python_out=generated \
      ../../protos/newsletter.proto && \
    touch generated/__init__.py && \
    sed -i 's/^import newsletter_pb2/from generated import newsletter_pb2/' generated/newsletter_pb2_grpc.py

# ── Entrypoint ──────────────────────────────
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["send"]
