# ─────────────────────────────────────────────
# Newsletter — multi-runtime Docker image
# Go (backend) + Node.js 20 (email-service)
#
# Build:  docker build -t newsletter .
# Run:    docker run -e RESEND_API_KEY=... newsletter send
# E2E:    docker run newsletter e2e
# ─────────────────────────────────────────────

# ── Stage 1: Node.js dependency install ──────
FROM node:20-slim AS node-deps
WORKDIR /app
COPY package.json yarn.lock ./
COPY packages/email-service/package.json packages/email-service/
RUN yarn install --frozen-lockfile --production=false

# ── Stage 2: Go backend build ───────────────
FROM golang:1.24-bookworm AS go-build
WORKDIR /build
RUN apt-get update && apt-get install -y protobuf-compiler && rm -rf /var/lib/apt/lists/*
RUN go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
ENV PATH=$PATH:/go/bin
COPY packages/backend/go.mod packages/backend/go.sum ./
RUN go mod download
COPY packages/backend/ .
RUN make proto
RUN CGO_ENABLED=0 go build -o /newsletter ./cmd/newsletter/

# ── Stage 3: Final image ────────────────────
FROM node:20-slim

WORKDIR /app

# Go binary (from stage 2).
COPY --from=go-build /newsletter /usr/local/bin/newsletter

# Node.js dependencies (from stage 1).
COPY --from=node-deps /app/node_modules ./node_modules
COPY --from=node-deps /app/packages/email-service/node_modules ./packages/email-service/node_modules

# Source files.
COPY . .

COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["send"]
