# Dev shortcuts. One-time setup is in the README:
#   backend:  python -m venv backend/.venv && backend/.venv/bin/pip install -e "backend[dev]"
#   frontend: npm install --prefix frontend

.PHONY: help backend frontend test test-backend test-frontend lint format

help: ## list available targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

backend: ## run the API with auto-reload on 127.0.0.1:8000
	cd backend && .venv/bin/uvicorn app.main:app --reload

frontend: ## run the Vite dev server on localhost:5173
	npm run dev --prefix frontend

test: test-backend test-frontend ## run both test suites

test-backend: ## backend suite (NOAA mocked, runs offline)
	cd backend && .venv/bin/pytest -q

test-frontend: ## frontend logic tests (Vitest)
	npm test --prefix frontend

lint: ## ruff + oxlint, same checks as CI
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	npm run lint --prefix frontend

format: ## auto-format the backend
	cd backend && .venv/bin/ruff format .
