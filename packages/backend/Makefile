.PHONY: build run lint clean proto

# ─── Build ──────────────────────────────────

build: proto
	go build -o newsletter ./cmd/newsletter/

run: proto
	go run ./cmd/newsletter/

# ─── Proto ──────────────────────────────────

proto:
	protoc --go_out=. --go_opt=module=newsletter-backend \
		-I proto proto/newsletter.proto

# ─── Linting ────────────────────────────────

lint:
	go vet ./...

# ─── Cleanup ────────────────────────────────

clean:
	rm -rf .cache newsletter
	@echo "🧹  Cleaned backend cache"
