# MCP Lens — Development Guide

## Prerequisites

- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

## Setup

```bash
git clone <repo-url> && cd mcp-tools-fetch

# Using make (recommended — interactive)
make setup    # installs deps, configures .env

# Or manually
uv sync                                    # Python deps (or: pip install -e ".[dev]")
cd src/frontend && npm install && cd ../..
cp .env.example .env                       # edit with your config
```

`make setup` presents a menu:

1. **Quick setup** — installs dependencies, creates `.env` with defaults
2. **Configure LLM evaluation** — prompts for LLM provider, model, API key
3. **Configure all settings** — ports, database, OAuth persistence, LLM config

## Running the App

```bash
# Using make
make start            # starts both backend and frontend
make stop             # stops both
make restart          # restart both

# Or manually
uv run uvicorn src.app.main:app --reload --port 5002 &
cd src/frontend && npm run dev &
```

- Frontend: http://localhost:5173
- Backend API: http://localhost:5002/api
- API docs: http://localhost:5002/docs (FastAPI auto-generated)

## Testing

```bash
# Full test suite (540+ tests)
make test
# or: uv run pytest tests/ -v

# Specific layer tests
uv run pytest tests/eval/test_protocol.py -v
uv run pytest tests/eval/test_quality.py -v
uv run pytest tests/eval/test_security.py -v
uv run pytest tests/eval/test_llm_eval.py -v
uv run pytest tests/eval/test_scoring.py -v

# Route tests
uv run pytest tests/test_routes_tools.py -v
uv run pytest tests/test_routes_servers.py -v

# Store tests
uv run pytest tests/test_tools_store.py -v

# Run with coverage
uv run pytest tests/ --cov=src.app --cov-report=html
```

### Test Isolation

Every test gets a fresh, isolated SQLite database via the `db` fixture in `conftest.py`. The fixture:

1. Creates a temp SQLite database in `tmp_path`
2. Monkeypatches `get_database_url` to use the temp path
3. Disables legacy migration functions (no filesystem interference)
4. Creates tables, yields, then disposes the engine

Tool store tests use `monkeypatch` to redirect `TOOLS_DIR` to `tmp_path`.

### Writing Tests

- Tests must not mutate production systems or real databases
- Never make actual MCP tool calls in tests — mock the transport layer
- Never include real API keys or tokens — use fixtures or env var stubs
- Use `db` fixture for any test that touches the database
- Use `monkeypatch` for filesystem operations (tools store, config files)

## TypeScript / Frontend

```bash
# Type check
make lint
# or: cd src/frontend && npx tsc --noEmit

# Dev server with hot reload
cd src/frontend && npm run dev

# Production build (outputs to ../../static)
cd src/frontend && npm run build
```

### Key Frontend Patterns

- **State-based routing** — No react-router. `App` manages a `view` state that determines which top-level component renders.
- **API client** — `api.ts` wraps `fetch()` with `/api` prefix. File uploads use `FormData` directly (no JSON content-type header).
- **js-yaml** — Uses named imports: `import { dump as yamlDump } from 'js-yaml'`. Default import causes Vite build errors.
- **Export** — Client-side PDF generation via jspdf + jspdf-autotable. JSON and YAML exports use native serialization.

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Server ports (optional, defaults shown)
BACKEND_PORT=5002
FRONTEND_PORT=5173

# API authentication (optional — when set, all API routes require X-API-Key header)
# MCP_LENS_API_KEY=your-secret-api-key

# Database (optional, defaults to SQLite at ./mcp_secrets.db)
# DATABASE_URL=sqlite+aiosqlite:///mcp_secrets.db

# OAuth token persistence (default: false — tokens deleted after tools fetch)
# PERSIST_OAUTH_TOKENS=true

# LLM evaluation
# EVAL_LLM_PROVIDER=openai
# EVAL_LLM_MODEL=gpt-4o
# EVAL_LLM_API_KEY=sk-...
```

See README.md for full LLM provider configuration options including multi-LLM setup via `llm.json`.

## Multi-LLM Configuration

For evaluating tools across multiple LLMs, create `llm.json` in the project root (see `llm.json.example`):

```json
{
  "default": "gemini-flash",
  "configs": {
    "gemini-flash": {
      "provider": "vertexai",
      "model": "gemini-2.5-flash",
      "project_env": "EVAL_LLM_PROJECT",
      "location_env": "EVAL_LLM_LOCATION"
    },
    "claude": {
      "provider": "anthropic",
      "model": "claude-sonnet-4-20250514",
      "api_key_env": "ANTHROPIC_API_KEY"
    }
  }
}
```

**`_env` suffix convention:** Keys ending in `_env` reference environment variable names from `.env`, not raw values. Never put API keys directly in `llm.json`.

## Docker

```bash
# Build and run with Docker Compose
docker compose up --build

# Or build manually
docker build -t mcp-lens .
docker run -p 5002:5002 mcp-lens
```

The Docker image builds the frontend and serves it as static files from the backend.

## Project Conventions

### Backend

- **FastAPI + async** — All route handlers are `async def`. Database uses SQLAlchemy async with `aiosqlite`.
- **Pydantic v2** — Request/response validation via Pydantic models.
- **YAML storage** — Tool definitions stored as `tools/{server_name}.yaml` on disk, not in the database. Eval reports and ground truth are in the database.
- **Logging** — Use `logging.getLogger(__name__)`. Never log secrets or credentials — redact API keys, tokens, passwords, cookies, authorization headers.
- **Error handling** — Routes raise `HTTPException` for client errors. Unhandled exceptions return generic `Internal server error` (stack traces only in server logs).
- **Server name validation** — `^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,254}$` for route params, `[A-Za-z0-9_-]+` for filesystem paths.

### Frontend

- **React 18 + Vite + Tailwind** — Functional components with hooks.
- **No external state management** — `useState` and prop drilling. State is local to components.
- **TypeScript strict** — `npx tsc --noEmit` must pass with zero errors.
- **Tailwind utility classes** — No custom CSS files. All styling via Tailwind classes.

### Security

- API keys and tokens are stored in the database, never in `.env` or config files
- OAuth client secrets referenced by env var name (`client_secret_env`), not stored directly
- LLM evaluation never executes MCP tools — it only simulates tool selection
- CORS locked to `localhost:{FRONTEND_PORT}` (not wildcard)
- SSRF protection on `/api/auth/discover` — validates URLs, blocks private/loopback addresses
- `.gitignore` excludes `.env`, `*.db`, service account files, `tokens.json`, runtime data
- Pre-commit hooks detect private keys and large files

## Makefile Targets

| Target | Description |
|--------|-------------|
| `make setup` | Interactive setup (deps, .env config) |
| `make start` | Start backend + frontend |
| `make stop` | Stop both services |
| `make restart` | Restart both services |
| `make test` | Run full pytest suite |
| `make lint` | TypeScript type check |
| `make clean` | Remove DB, caches, node_modules, .venv |
| `make clean-all` | Full reset (clean + remove .env) |

## Adding New Evaluation Checks

1. Add the check function in the appropriate layer module (`eval/protocol.py`, `eval/quality.py`, `eval/security.py`, or `eval/llm_eval.py`)
2. The check should return a `CheckResult` with `check_id`, `tool_name`, `status` (pass/fail/warn/skip), `severity`, and `message`
3. Add the check call in the layer's `check_*_all()` function
4. Add a test in `tests/eval/test_{layer}.py`
5. Update `docs/RULES.md` with the rule definition
6. Update the rules table in `src/frontend/src/components/AboutPage.tsx`

## Adding New API Endpoints

1. Add the route handler in the appropriate router (`routes/tools.py`, `routes/servers.py`, or `routes/auth_routes.py`)
2. Add corresponding frontend API function in `src/frontend/src/api.ts`
3. Add tests in the appropriate test module
4. Update the API Reference in `README.md` and the endpoints table in `docs/architecture.md`

## Manual Tool Upload Flow

When direct server connection is not possible:

```
User clicks "Template"  ──>  GET /tools/template  ──>  Downloads YAML template
                                                         (uses existing tools if available,
                                                          otherwise generic 2-tool example)

User fills in YAML       ──>  (offline editing)

User clicks "Upload"     ──>  POST /tools/upload   ──>  Validates YAML structure
                                                         Checks: name required, inputSchema
                                                         format, warns on missing description
                                                         Saves with source="uploaded"

Tools tab shows:          ──>  Source badge: "Uploaded by user" (amber)
                               "Remove" button appears

User clicks "Re-fetch"   ──>  POST /fetch-tools    ──>  Overrides uploaded tools
                               Source badge changes to "Fetched from server" (green)
                               "Remove" button disappears
```

Both fetch and upload write to the same `tools/{server_name}.yaml` file — whichever runs last wins.
