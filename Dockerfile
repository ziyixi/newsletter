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

# ── Stage 4: Final image ────────────────────
FROM node:20-slim

WORKDIR /app

# Go binary (from stage 3).
COPY --from=go-build /newsletter /usr/local/bin/newsletter

# Node.js single executable (from stage 2).
COPY --from=node-sea /app/packages/email-service/email-service /usr/local/bin/email-service
RUN chmod +x /usr/local/bin/email-service

# Source only for backend .cache and scripts (entrypoint runs newsletter from packages/backend).
COPY packages/backend packages/backend
COPY scripts scripts

COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["send"]
