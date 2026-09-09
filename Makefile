SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

# macOS /usr/bin/make is GNU Make 3.81. It execs simple recipe lines with
# execvp and does not apply Makefile PATH exports. Resolve absolute tool
# paths instead of depending on PATH inside recipes.
# macOS /usr/bin/make is GNU Make 3.81. It execs simple recipe lines with
# execvp and does not apply Makefile PATH exports. Resolve an executable
# path that can report its version, then invoke that path in recipes.
# Search inherited PATH first, then common install locations.
ifeq ($(origin UV),undefined)
  UV := $(shell for c in $$(command -v uv 2>/dev/null) "$(HOME)/.local/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do if [ -n "$$c" ] && [ -x "$$c" ] && "$$c" --version >/dev/null 2>&1; then printf '%s' "$$c"; break; fi; done)
  ifeq ($(strip $(UV)),)
    UV := $(HOME)/.local/bin/uv
  endif
endif
ifeq ($(origin PNPM),undefined)
  PNPM := $(shell for c in $$(command -v pnpm 2>/dev/null) /usr/local/bin/pnpm /opt/homebrew/bin/pnpm "$(HOME)/.local/bin/pnpm"; do if [ -n "$$c" ] && [ -x "$$c" ] && "$$c" --version >/dev/null 2>&1; then printf '%s' "$$c"; break; fi; done)
  ifeq ($(strip $(PNPM)),)
    PNPM := $(HOME)/.local/bin/pnpm
  endif
endif
ifeq ($(origin NODE),undefined)
  NODE := $(shell for c in $$(command -v node 2>/dev/null) /usr/local/bin/node /opt/homebrew/bin/node "$(HOME)/.local/bin/node"; do if [ -n "$$c" ] && [ -x "$$c" ] && "$$c" --version >/dev/null 2>&1; then printf '%s' "$$c"; break; fi; done)
  ifeq ($(strip $(NODE)),)
    NODE := $(HOME)/.local/bin/node
  endif
endif

.PHONY: help require-uv require-pnpm require-node setup format format-check lint typecheck test \
	validate-contracts generate-contracts openapi-drift secrets deps-up deps-down db-health \
	compose-config web-integration check

help:
	@printf '%s\n' \
	  'ITAA developer commands' \
	  '  make setup              Install Python 3.12 and TypeScript workspace dependencies' \
	  '  make format             Apply Python and TypeScript formatters' \
	  '  make format-check       Verify formatting without writing' \
	  '  make lint               Lint Python and TypeScript workspaces' \
	  '  make typecheck          Strict type-check Python and TypeScript workspaces' \
	  '  make test               Run Python, UI-kit, contracts, and UI-01 web tests' \
	  '  make validate-contracts Validate JSON Schema, fixtures, invariants, and generated drift' \
	  '  make generate-contracts Regenerate Python and TypeScript contract representations' \
	  '  make openapi-drift      Non-mutating check of apps/api/openapi/itaa-v1.json' \
	  '  make secrets            Scan the workspace for credential patterns' \
	  '  make compose-config     Validate Docker Compose configuration' \
	  '  make deps-up            Start local PostgreSQL and wait until healthy' \
	  '  make db-health          Check local PostgreSQL readiness' \
	  '  make deps-down          Stop local PostgreSQL' \
	  '  make web-integration    Run the UI-01 WP-06 HTTP golden-path integration target' \
	  '  make check              Run the complete local quality gate'

require-uv:
	@if [ ! -x "$(UV)" ]; then \
	  printf '%s\n' \
	    "error: uv was not found (looked for: $(UV))." \
	    "Install: curl -LsSf https://astral.sh/uv/install.sh | sh"; \
	  exit 1; \
	fi

require-pnpm:
	@if [ ! -x "$(PNPM)" ]; then \
	  printf '%s\n' \
	    "error: pnpm was not found (looked for: $(PNPM))." \
	    "Enable with: corepack enable && corepack prepare pnpm@11.9.0 --activate"; \
	  exit 1; \
	fi

require-node:
	@if [ ! -x "$(NODE)" ]; then \
	  printf '%s\n' \
	    "error: node was not found (looked for: $(NODE))." \
	    "Install Node.js 22+ so node --version succeeds."; \
	  exit 1; \
	fi

setup: require-uv require-pnpm
	$(UV) python pin 3.12
	$(UV) sync --group dev
	$(PNPM) install

format: require-uv require-pnpm
	$(UV) run ruff format packages apps tests tools adapters
	$(UV) run ruff check --fix packages apps tests tools adapters
	$(PNPM) format

format-check: require-uv require-pnpm
	$(UV) run ruff format --check packages apps tests tools adapters
	$(PNPM) format:check

lint: require-uv require-pnpm
	$(UV) run ruff check packages apps tests tools adapters
	$(PNPM) lint

typecheck: require-uv require-pnpm
	$(UV) run mypy
	$(PNPM) typecheck

test: require-uv require-pnpm
	$(UV) run pytest
	$(PNPM) test

validate-contracts: require-uv require-pnpm require-node
	$(UV) run itaa-validate-contracts --node-bin $(NODE) --pnpm-bin $(PNPM)

generate-contracts: require-uv require-pnpm require-node
	$(UV) run itaa-validate-contracts --generate --node-bin $(NODE) --pnpm-bin $(PNPM)

openapi-drift: require-uv
	$(UV) run python -m itaa_api.export_openapi --check

secrets: require-uv
	$(UV) run itaa-redact-check

compose-config:
	docker compose -f compose.yaml config --quiet

deps-up:
	docker compose up -d --wait

db-health:
	docker compose exec postgres pg_isready -U itaa -d itaa_dev

deps-down:
	docker compose down

web-integration: require-pnpm require-uv
	bash apps/web/scripts/run-integration.sh

check: format-check lint typecheck test validate-contracts openapi-drift secrets compose-config
	@printf '%s\n' 'PASS: local quality gate'
