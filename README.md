# MCP Lens

Inspect, evaluate, and manage your MCP server tools.

MCP Lens connects to [Model Context Protocol](https://modelcontextprotocol.io/) servers, fetches their tool definitions, and runs a multi-layer evaluation to surface protocol violations, quality issues, security risks, and — when an LLM is configured — real-world usability problems.

## Features

- **Server management** — Add, edit, delete, and test MCP server connections from the web UI
- **Multiple auth flows** — Bearer token, API key, OAuth 2.0 (authorization code + client credentials), and Dynamic Client Registration (DCR)
- **Tool inspection** — Fetch and browse tool definitions with full schema detail, parameter tables, and raw JSON schemas
- **Manual tool upload** — When a server is unreachable, download a YAML template, fill in tool definitions, and upload; source badge shows "Uploaded by user" vs "Fetched from server"
- **Multi-layer evaluation** — 35+ checks across protocol compliance, quality, security, and LLM-assisted layers
- **Scoring and gating** — Weighted overall score with configurable pass/fail thresholds
- **False positive marking** — Mark evaluation failures as false positives with justification; persisted across sessions and reflected in exports
- **Combined export** — Download tools + evaluation data as JSON, YAML, or PDF with selectable sections
- **In-app reference** — About page with all evaluation rules, scoring logic, and LLM configuration docs
- **Regression tracking** — Compare reports over time to catch regressions
- **CLI and API** — Run evaluations headlessly in CI or programmatically via REST
- **SQLite persistence** — Server configs, auth tokens, and evaluation reports stored in a local database
- **Optional LLM evaluation** — Five additional checks that test tools from an AI agent's perspective

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Setup

```bash
git clone <repo-url> && cd mcp-tools-fetch

# Using make (recommended)
make setup    # interactive setup — installs deps, configures .env
make start    # starts backend + frontend
```

`make setup` presents a menu:

1. **Quick setup** — installs dependencies, creates `.env` with defaults
2. **Configure LLM evaluation** — prompts for LLM provider, model, API key
3. **Configure all settings** — ports, database, OAuth persistence, LLM config

If `.env` already exists, it asks whether to overwrite, merge, or keep it.

```bash
# Or set up manually
uv sync                                        # or: pip install -e ".[dev]"
cd src/frontend && npm install && cd ../..
cp .env.example .env                           # edit with your config
```

### Start the app

```bash
# Using make
make start            # starts both backend and frontend
make stop             # stops both
make restart          # restart both

# Or manually
uv run uvicorn src.app.main:app --reload --port 5002 &
cd src/frontend && npm run dev &
```

Open http://localhost:5173 to manage servers and run evaluations.

### CLI

```bash
# Validate a tools YAML file
mcp-eval validate tools.yaml

# Full report (JSON or text)
mcp-eval report tools.yaml --format json --output report.json

# With LLM-assisted evaluation
mcp-eval validate tools.yaml --llm
mcp-eval report tools.yaml --llm

# Compare two reports for regressions
mcp-eval compare baseline.json current.json

# Security-only analysis
mcp-eval security tools.yaml
```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Server ports (optional, defaults shown)
BACKEND_PORT=5002
FRONTEND_PORT=5173

# API authentication (optional — when set, all API routes require X-API-Key header)
# MCP_LENS_API_KEY=your-secret-api-key

# Database (optional, defaults to SQLite at ./mcp_secrets.db)
# DATABASE_URL=sqlite+aiosqlite:///mcp_secrets.db
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/mcp_tools

# OAuth token persistence (default: false — tokens deleted after tools fetch)
# PERSIST_OAUTH_TOKENS=true

# LLM evaluation — see "LLM-Assisted Evaluation" section below
# EVAL_LLM_PROVIDER=openai
# EVAL_LLM_MODEL=gpt-4o
# EVAL_LLM_API_KEY=sk-...
```

### Authentication Modes

MCP Lens supports multiple authentication modes for connecting to MCP servers:

| Mode | Description | Config |
|------|------------|--------|
| **None** | No authentication | `auth: false` |
| **Bearer token** | Static JWT/token sent in `Authorization` header | `auth_mode: bearer_token` — token stored in DB via UI |
| **API key** | Static key sent in a configurable header | `auth_mode: api_key` — key name/location set via `api_key_config` |
| **OAuth** | OAuth 2.0 authorization code flow | `auth_mode: oauth` — endpoints configured in `oauth` block |
| **DCR** | Dynamic Client Registration + OAuth | `auth_mode: dcr` — discovers endpoints via MCP server metadata |

Bearer tokens and API keys are stored encrypted in the SQLite database, not in `.env` files. OAuth tokens can optionally be persisted across sessions with `PERSIST_OAUTH_TOKENS=true`.

### Server Config Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | required | MCP server endpoint URL |
| `transport` | string | `streamable_http` | Transport protocol |
| `auth` | bool | `false` | Whether authentication is required |
| `auth_mode` | string | `null` | Auth type: `bearer_token`, `api_key`, `oauth`, `dcr` |
| `ssl_verify` | bool | `true` | Verify SSL certificates |
| `timeout` | int | `30` | Connection timeout in seconds |
| `description` | string | `""` | Human-readable server description |
| `oauth` | object | `null` | OAuth config (endpoints, client_id, scopes, etc.) |
| `api_key_config` | object | `null` | API key config (`location`: header/query, `name`: header name) |

## Architecture

```
src/
  app/
    eval/           # Evaluation engine
      protocol.py   #   Layer 1: MCP spec compliance
      quality.py    #   Layer 2: Tool quality & overlap detection
      security.py   #   Layer 3: Security analysis
      llm_eval.py   #   Layer 4: LLM-assisted evaluation
      scoring.py    #   Scoring & gate logic
      runner.py     #   Orchestrates all layers
      model_adapter.py  # LLM provider adapters (Anthropic, OpenAI, VertexAI, Gemini)
      llm_config.py #   Multi-LLM config loader (llm.json)
      regression.py #   Report comparison
    routes/
      servers.py    # CRUD endpoints for server configs
      tools.py      # Tool fetch, evaluation, false positive marking
      auth_routes.py # OAuth/DCR flows, token management
    database.py     # SQLAlchemy async models (SQLite/PostgreSQL)
    mcp_client.py   # MCP protocol client (JSON-RPC 2.0 over streamable HTTP)
    auth.py         # OAuth token management, DCR, endpoint discovery
    config.py       # Configuration loader
    models.py       # Pydantic models
  frontend/         # React + Vite + Tailwind UI
    src/
      components/
        ServerList.tsx      # Server cards with status, connect, evaluate
        ServerForm.tsx      # Add/edit server modal
        ToolsViewer.tsx     # Tool list + evaluation tabs, combined export
        EvaluationView.tsx  # Evaluation report with false positive marking
        DownloadModal.tsx   # Export options modal (JSON/PDF)
        AboutPage.tsx       # In-app evaluation rules reference
      utils/
        download.ts         # PDF/JSON export (jspdf + jspdf-autotable)
      api.ts                # API client
      types.ts              # TypeScript interfaces
llm.json.example    # Multi-LLM config template (all providers)
tests/
  eval/             # Evaluation engine tests
  test_*.py         # Route, config, database tests
```

## Manual Tool Upload

When an MCP server is unreachable (firewall, VPN, authentication issues), you can still evaluate its tools by uploading definitions manually:

1. **Download template** — Click "Template" on the Tools tab to get a YAML file with the expected structure
2. **Fill in definitions** — Add your tool names, descriptions, and input schemas
3. **Upload** — Click "Upload" and select the completed YAML file

The YAML format:

```yaml
tools:
  - name: my_tool
    description: Does something useful
    inputSchema:
      type: object
      properties:
        param1:
          type: string
          description: A required parameter
      required:
        - param1
```

Uploaded tools work identically to fetched tools for evaluation. A badge in the UI indicates the source ("Uploaded by user" vs "Fetched from server"). Re-fetching from the server overrides uploaded tools, and uploading overrides previously fetched tools.

## Evaluation Layers

MCP Lens runs four evaluation layers. The first three are static analysis — they examine tool definitions structurally. The fourth (LLM) requires a configured provider and tests tools from an agent's perspective.

See [docs/RULES.md](docs/RULES.md) for the complete rule reference.

| Layer | Checks | What it catches |
|-------|--------|-----------------|
| **Protocol** | 12 | Missing names, invalid schemas, malformed annotations |
| **Quality** | 11 | Vague descriptions, missing parameter docs, naming inconsistencies |
| **Security** | 6 | Annotation mismatches, prompt injection, SQL injection surfaces, data exfil risks |
| **LLM** | 5+ | Description confusion, wrong tool selection, argument hallucination, overlap ambiguity, unsafe tool activation |

### How Tool Selection Evaluation Works

One of the most impactful LLM checks is **tool selection** (`llm.tool_selection`). Here's the process:

1. **Scenario generation** — For each tool, the LLM generates a realistic user request based on the tool's name and description. For example, for a tool called `traverse_lineage_tool`, it might generate: *"Show me the lineage of the 'customer_transactions' table."*

2. **Tool selection test** — The generated scenario is sent to the LLM along with **all** tools from the server (names, descriptions, schemas) using native function-calling / tool-use. The LLM must pick the correct tool.

3. **Verdict** — If the LLM picks the right tool: **PASS**. If it picks a different tool, a follow-up check determines whether the selection was a valid prerequisite step or genuine confusion:
   - **WARN** (medium) — The selected tool is a reasonable prerequisite (e.g., `getAccessibleAtlassianResources` before `updateConfluencePage`). This reflects valid multi-step agent planning.
   - **FAIL** (high) — The LLM genuinely confused the tools. The description needs improvement.

**Important safety note:** The LLM is only asked *which* tool it would select — no tool is ever executed. This is a read-only simulation.

When tool selection fails (not a prerequisite), it means the tool's description isn't distinctive enough for an AI agent to reliably choose it. The fix is on the MCP server side: improve the tool's description to clearly differentiate it from similar tools. When the result is a prerequisite warning, it may be valid agent behavior — mark it as a false positive if so.

### Scoring

Each layer receives a score (0-100) based on check results weighted by severity:

| Severity | Weight |
|----------|--------|
| Critical | 5.0 |
| High | 3.0 |
| Medium | 2.0 |
| Low | 1.0 |
| Info | 0.5 |

The overall score is a weighted combination of active layers. Layers not present in a run (e.g., LLM when not configured) are excluded and weights auto-normalize.

**Gate threshold:** 70.0 (configurable). Any critical failure in the `protocol` or `security` layer forces the gate to fail regardless of score.

### False Positives

Evaluation failures can be marked as false positives from the UI. Each false positive requires a justification explaining why the failure is acceptable.

- False positives are persisted in the evaluation report metadata
- They survive re-runs and are keyed by `{layer}:{tool_name}:{check_id}`
- In the UI, FP-marked checks show with strikethrough and a purple "FP" badge
- In PDF exports, FP checks show as purple "FP" status with the justification text
- The export modal includes an option to include or exclude false positive overrides

### Export

The JSON and PDF buttons in the header export both tools and evaluation data in a single file. The download modal lets you select which sections to include:

**Tools sections:**
- Tool overview table
- Parameter details
- Raw JSON schemas (JSON only)

**Evaluation sections (when a report exists):**
- Summary & Scores
- Protocol Compliance
- Tool Quality
- Security Analysis
- LLM-Assisted Evaluation
- False positive overrides

## LLM-Assisted Evaluation

When `EVAL_LLM_PROVIDER` is set in `.env`, MCP Lens runs five additional checks that probe tool definitions from an AI agent's perspective. No benchmark YAML or test fixtures required — scenarios are auto-generated from tool metadata.

### Configuration

Add to your `.env`:

```bash
# Required — choose one: openai, anthropic, vertexai, anthropic-vertex
EVAL_LLM_PROVIDER=openai
EVAL_LLM_MODEL=gpt-4o
EVAL_LLM_API_KEY=sk-...

# Anthropic direct API
# EVAL_LLM_PROVIDER=anthropic
# EVAL_LLM_MODEL=claude-sonnet-4-20250514
# EVAL_LLM_API_KEY=sk-ant-...

# VertexAI with Gemini (uses ADC or API key)
# EVAL_LLM_PROVIDER=vertexai
# EVAL_LLM_MODEL=gemini-2.5-flash
# EVAL_LLM_PROJECT=my-gcp-project
# EVAL_LLM_LOCATION=us-central1

# Claude on VertexAI (uses ADC / service account)
# EVAL_LLM_PROVIDER=anthropic-vertex
# EVAL_LLM_MODEL=claude-sonnet-4-20250514
# EVAL_LLM_PROJECT=my-gcp-project
# EVAL_LLM_LOCATION=us-east5
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json

# OpenAI-compatible endpoints (Azure, Ollama, vLLM)
# EVAL_LLM_BASE_URL=https://my-proxy.example.com/v1
```

When not configured, the LLM layer is skipped entirely — the app works exactly as before with three static layers.

### Multi-LLM Configuration

For evaluating tools across multiple LLMs simultaneously, create a `llm.json` file in the project root (see `llm.json.example` for a complete template):

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

**`_env` suffix convention:** Keys ending in `_env` (e.g., `api_key_env`, `project_env`) reference environment variable names defined in `.env`, not raw values. This keeps secrets out of `llm.json`.

**How it works:**
- `default` — The LLM config used for single-model evaluation
- `configs` — A map of named configurations, each specifying a `provider`, `model`, and provider-specific auth keys
- When `llm.json` contains 2+ configs, the UI shows an **LLM selector** dropdown in the evaluation panel
- The multi-LLM evaluation endpoint runs all selected configs in parallel and returns comparative results
- Available configs are listed via `GET /api/llm-configs`

Supported providers in `llm.json`: `openai`, `anthropic`, `vertexai`, `anthropic-vertex`. See `llm.json.example` for examples of all providers.

### What LLM Checks Test

| Check | What it does | Why it matters |
|-------|-------------|----------------|
| **Description Clarity** | LLM rates description clarity 1-10 | If an LLM can't understand the tool, no agent can use it |
| **Tool Selection** | Auto-generates a scenario, asks LLM to pick the right tool | Tests if the tool is distinguishable from its neighbors |
| **Argument Generation** | LLM generates arguments; validates against schema | Catches unclear schemas that cause hallucinated or missing params |
| **Overlap Disambiguation** | For overlapping tool pairs, tests if LLM can tell them apart | Surfaces descriptions that need differentiating |
| **Safety Resistance** | Sends benign prompts, checks if LLM avoids destructive tools | Ensures annotations and naming prevent accidental misuse |

See [docs/RULES.md](docs/RULES.md) for detailed rule definitions and examples.

## API Reference

### Server Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/servers` | List all configured MCP servers |
| `GET` | `/api/servers/{name}` | Get a single server config |
| `POST` | `/api/servers` | Add a new server |
| `PUT` | `/api/servers/{name}` | Update server config |
| `DELETE` | `/api/servers/{name}` | Remove a server |

### Tools & Evaluation

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/servers/{name}/test` | Test MCP connection |
| `POST` | `/api/servers/{name}/fetch-tools` | Fetch tools from MCP server |
| `GET` | `/api/servers/{name}/tools` | Get cached tool definitions (includes `source` field) |
| `POST` | `/api/servers/{name}/tools/upload` | Upload tool definitions via YAML |
| `GET` | `/api/servers/{name}/tools/template` | Download YAML template for tool definitions |
| `DELETE` | `/api/servers/{name}/tools/uploaded` | Delete manually uploaded tools |
| `GET` | `/api/servers/{name}/evaluate` | Quick compatibility evaluation |
| `GET` | `/api/servers/{name}/evaluate/full` | Full multi-layer evaluation report |
| `GET` | `/api/servers/{name}/evaluate/report` | Get cached evaluation report |
| `GET` | `/api/servers/{name}/evaluate/llm` | Run LLM-assisted evaluation layer |
| `POST` | `/api/servers/{name}/evaluate/false-positive` | Mark/unmark a check as false positive |
| `POST` | `/api/servers/{name}/ground-truth` | Upload ground truth YAML |
| `GET` | `/api/servers/{name}/ground-truth` | Get ground truth data |
| `DELETE` | `/api/servers/{name}/ground-truth` | Delete ground truth |
| `GET` | `/api/servers/{name}/ground-truth/template` | Download ground truth YAML template |
| `GET` | `/api/llm-configs` | List available LLM configurations from `llm.json` |

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/auth/status/{name}` | Check auth status for a server |
| `POST` | `/api/auth/bearer-token/{name}` | Store a bearer token |
| `POST` | `/api/auth/api-key/{name}` | Store an API key |
| `POST` | `/api/auth/discover` | Discover OAuth/DCR endpoints from server metadata |
| `POST` | `/api/auth/start/{name}` | Start OAuth authorization flow |
| `GET` | `/api/auth/callback` | OAuth callback handler |

## Development

```bash
# Install all dependencies (interactive)
make setup

# Run Python tests (541 tests)
make test
# or: uv run pytest tests/ -v

# Run specific layer tests
uv run pytest tests/eval/test_protocol.py -v
uv run pytest tests/eval/test_llm_eval.py -v

# TypeScript type check
make lint
# or: cd src/frontend && npx tsc --noEmit

# Clean generated files (DB, caches, node_modules, .venv)
make clean

# Full reset (clean + remove .env)
make clean-all
```

### Project Structure

- **Backend**: FastAPI + SQLAlchemy async (aiosqlite for SQLite, asyncpg for PostgreSQL)
- **Frontend**: React 18 + Vite + Tailwind CSS (state-based routing, no react-router)
- **PDF generation**: Client-side using jspdf + jspdf-autotable
- **MCP protocol**: JSON-RPC 2.0 over streamable HTTP transport
- **LLM adapters**: Anthropic, OpenAI, VertexAI (Gemini), Anthropic on VertexAI (Claude)

### Docker

```bash
# Build and run with Docker Compose
docker compose up --build

# Or build manually
docker build -t mcp-lens .
docker run -p 5002:5002 mcp-lens
```

The Docker image builds the frontend and serves it as static files from the backend.

### Security Considerations

- **API authentication**: Set `MCP_LENS_API_KEY` to require `X-API-Key` header on all API routes (health endpoint stays open)
- **SSRF protection**: The `/api/auth/discover` endpoint validates URLs and blocks private/loopback addresses
- **Server name sanitization**: Server names are validated against `^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,254}$`
- **Error hardening**: Unhandled exceptions return generic `Internal server error` — stack traces stay in server logs only
- Bearer tokens and API keys are stored in the database, never in `.env` or config files
- OAuth client secrets are referenced by environment variable name (`client_secret_env`), not stored directly
- The LLM evaluation **never executes MCP tools** — it only simulates tool selection
- Sensitive values (API keys, tokens, passwords) are redacted from logs
- CORS locked to `localhost:{FRONTEND_PORT}` (not wildcard)
- `.gitignore` excludes `.env`, `*.db`, service account files, `tokens.json`, and runtime data
- Pre-commit hooks detect private keys and large files

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
