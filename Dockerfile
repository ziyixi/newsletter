# ─────────────────────────────────────────────
# Newsletter — Docker image: Go backend + Node SEA (email-service)
# Final image: debian:bookworm-slim only (no Node.js; SEA has runtime baked in).
# Node is used only in build stages; image scanners see the final stage.
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

# ── Stage 2: Node.js single executable (SEA) ─
FROM node-deps AS node-sea
COPY packages/email-service packages/email-service/
RUN yarn workspace email-service build:bundle
WORKDIR /app/packages/email-service
RUN node --experimental-sea-config sea-config.json
RUN cp "$(command -v node)" email-service \
  && npx postject email-service NODE_SEA_BLOB sea-prep.blob \
    --sentinel-fuse NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2

# ── Stage 3: Go backend build ────────────────
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

# ── Stage 4: Final image (minimal glibc base; no Node.js runtime) ─
# Node SEA is linked against glibc; Debian slim provides it + shell for entrypoint.
FROM debian:bookworm-slim

WORKDIR /app

# Go binary (static, CGO_ENABLED=0).
COPY --from=go-build /newsletter /usr/local/bin/newsletter

# Node.js single executable (SEA — runtime baked in; needs glibc only).
COPY --from=node-sea /app/packages/email-service/email-service /usr/local/bin/email-service
RUN chmod +x /usr/local/bin/email-service

# Backend config/cache dir and entrypoint script.
COPY packages/backend packages/backend
COPY scripts scripts
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["send"]
