# zed-monorepo: orchestrate the retained submodules under apps/.
.DEFAULT_GOAL := help
API_REVISION := $(shell git -C apps/zed-api-server.rs rev-parse HEAD)
API_INTERFACES_REVISION := 4b87e425b04777b0ee413971dc1df805d24f295f
API_LIB_CORE_REVISION := c3d486a1519381276fbec02aa25247f542924443
WEB_REVISION := $(shell git -C apps/zed-web-server.rs rev-parse HEAD)
WEB_INTERFACES_REVISION := 7d31f80dd8a310f218931165a3ad636a2f32b932
WEB_LIB_CORE_REVISION := c3d486a1519381276fbec02aa25247f542924443

.PHONY: help init pull status validate test build images site

help: ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | sort

init: ## Sync and initialize all retained submodules
	git submodule sync --recursive
	git submodule update --init --recursive

pull: ## Advance retained submodules using their configured remotes
	git submodule sync --recursive
	git submodule update --init --recursive --remote --merge

status: ## Show recursive pinned-submodule status
	git submodule status --recursive

validate: ## Enforce package, inventory, and gitlink invariants
	python3 scripts/check-portfolio-inventory.py

test: validate ## Run retained repos' tests
	cd apps/zed-interfaces && cargo test
	cd apps/zed-lib-core && cargo test --workspace
	cd apps/zed-api-server.rs && cargo test --workspace
	cd apps/zed-web-server.rs && cargo test
	cd apps/zed-clients/clients/rust && cargo test
	cd apps/zed-clients/clients/typescript && npm ci && npm run build && npm test
	cd apps/zed-clients/clients/python && python3 -m unittest
	cd apps/zed-clients/clients/go && go test ./...
	cd apps/zed-sync && cargo test
	cd apps/zed-sync/sdk && npm ci && npm run typecheck && npm test

build: validate ## Build retained Rust services and TypeScript packages
	cd apps/zed-lib-core && cargo build --release --workspace
	cd apps/zed-api-server.rs && cargo build --release --workspace
	cd apps/zed-web-server.rs && cargo build --release
	cd apps/zed-clients/clients/typescript && npm ci && npm run build
	cd apps/zed-sync && cargo build --release
	cd apps/zed-sync/sdk && npm ci && npm run typecheck

images: validate ## Build the api/web container images (context = apps/)
	docker build -f apps/zed-api-server.rs/Dockerfile \
		--build-arg ZED_API_REVISION=$(API_REVISION) \
		--build-arg ZED_INTERFACES_REVISION=$(API_INTERFACES_REVISION) \
		--build-arg ZED_LIB_CORE_REVISION=$(API_LIB_CORE_REVISION) \
		-t ghcr.io/zed-pkg/zed-api-server:dev apps
	docker build -f apps/zed-web-server.rs/Dockerfile \
		--build-arg ZED_WEB_REVISION=$(WEB_REVISION) \
		--build-arg ZED_INTERFACES_REVISION=$(WEB_INTERFACES_REVISION) \
		--build-arg ZED_LIB_CORE_REVISION=$(WEB_LIB_CORE_REVISION) \
		-t ghcr.io/zed-pkg/zed-web-server:dev apps

site: validate ## Build the marketing site
	cd apps/zed-pkg.github.io && npm ci && npm run build
