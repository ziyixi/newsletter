# Proto codegen target
# Generated files: newsletter_pb2.py, newsletter_pb2.pyi, newsletter_pb2_grpc.py

PROTO_DIR := ../../protos
OUT_DIR := ./generated

.PHONY: proto clean sync run

# ─── uv package management ──────────────────

sync:
	uv sync

run:
	uv run python -m src.main

# ─── Proto codegen ──────────────────────────

proto:
	@mkdir -p $(OUT_DIR)
	uv run python -m grpc_tools.protoc \
		-I$(PROTO_DIR) \
		--python_out=$(OUT_DIR) \
		--pyi_out=$(OUT_DIR) \
		--grpc_python_out=$(OUT_DIR) \
		$(PROTO_DIR)/newsletter.proto
	@touch $(OUT_DIR)/__init__.py
	@# Fix import path for grpc stub to use package-relative import
	@sed -i'' -e 's/^import newsletter_pb2/from generated import newsletter_pb2/' $(OUT_DIR)/newsletter_pb2_grpc.py
	@echo "✅  Proto code generated in $(OUT_DIR)/"

clean:
	rm -rf $(OUT_DIR)/*.py $(OUT_DIR)/*.pyi
	@echo "🧹  Cleaned generated proto files"
