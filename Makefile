-include .env
export

BACKEND_PORT ?= 5002
FRONTEND_PORT ?= 5173

.PHONY: start stop restart start-backend start-frontend stop-backend stop-frontend test lint setup clean clean-all

start: start-backend start-frontend

start-backend:
	@echo "Starting backend on port $(BACKEND_PORT)..."
	@uv run uvicorn src.app.main:app --reload --port $(BACKEND_PORT) &
	@sleep 2
	@echo "Backend running at http://localhost:$(BACKEND_PORT)"

start-frontend:
	@echo "Starting frontend on port $(FRONTEND_PORT)..."
	@cd src/frontend && BACKEND_PORT=$(BACKEND_PORT) FRONTEND_PORT=$(FRONTEND_PORT) npm run dev &
	@sleep 2
	@echo "Frontend running at http://localhost:$(FRONTEND_PORT)"

stop: stop-backend stop-frontend

stop-backend:
	@echo "Stopping backend..."
	@pkill -f "uvicorn src.app.main:app" 2>/dev/null || true

stop-frontend:
	@echo "Stopping frontend..."
	@pkill -f "vite" 2>/dev/null || true

restart: stop
	@sleep 1
	@$(MAKE) start

test:
	uv run pytest tests/ -v

lint:
	@cd src/frontend && npx tsc --noEmit
	@echo "TypeScript check passed"

setup:
	@bash scripts/setup.sh

clean:
	@echo "Cleaning generated files..."
	@rm -rf tools/ && echo "  removed tools/" || true
	@rm -rf eval_reports/ && echo "  removed eval_reports/" || true
	@rm -rf static/ && echo "  removed static/" || true
	@rm -rf src/frontend/node_modules/ && echo "  removed src/frontend/node_modules/" || true
	@rm -rf src/frontend/dist/ && echo "  removed src/frontend/dist/" || true
	@rm -rf .venv/ && echo "  removed .venv/" || true
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null && echo "  removed __pycache__/" || true
	@rm -rf .pytest_cache/ .mypy_cache/ .ruff_cache/ && echo "  removed cache dirs" || true
	@echo "Clean complete. Run 'make setup' to reinstall."

clean-all: clean
	@rm -f mcp_secrets.db && echo "  removed mcp_secrets.db" || true
	@rm -f .env && echo "  removed .env"
	@echo "Full clean complete."
