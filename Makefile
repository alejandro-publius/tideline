# Dev shortcuts. One-time setup is in the README:
#   backend:  python -m venv backend/.venv && backend/.venv/bin/pip install -e "backend[dev]"
#   frontend: npm install --prefix frontend

.PHONY: help setup backend frontend mcp dev test test-backend test-frontend typecheck cov lint format

help: ## list available targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

setup: ## one-time: create the backend venv and install both toolchains
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -e "backend[dev]"
	npm install --prefix frontend

backend: ## run the API with auto-reload on 127.0.0.1:8000
	cd backend && .venv/bin/uvicorn app.main:app --reload

frontend: ## run the Vite dev server on localhost:5173
	npm run dev --prefix frontend

mcp: ## run the MCP server (Tideline as agent tools, over stdio)
	cd backend && .venv/bin/python -m app.mcp_server

dev: backend ## run the API (start `make frontend` alongside in a second terminal)

test: test-backend test-frontend ## run both test suites

test-backend: ## backend suite (NOAA mocked, runs offline)
	cd backend && .venv/bin/pytest -q

test-frontend: ## frontend logic tests (Vitest)
	npm test --prefix frontend

typecheck: ## mypy over the backend, same as CI
	cd backend && .venv/bin/mypy

cov: ## backend suite with a coverage report
	cd backend && .venv/bin/pytest --cov=app --cov-report=term-missing

lint: ## ruff + oxlint, same checks as CI
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	npm run lint --prefix frontend

format: ## auto-format the backend
	cd backend && .venv/bin/ruff format .
