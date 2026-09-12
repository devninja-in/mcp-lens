# MCP Lens — Architecture

## 1. Overview

MCP Lens is a web application for inspecting, evaluating, and managing MCP (Model Context Protocol) server tools. Users register MCP server endpoints through a web UI, configure authentication credentials, then connect to each server over the MCP protocol (JSON-RPC 2.0 over streamable HTTP) to discover and catalog available tools. When direct server connection is not possible, users can upload tool definitions manually via YAML.

Fetched or uploaded tool definitions are persisted as YAML files and evaluated through a multi-layer engine (protocol compliance, quality, security, and optional LLM-assisted checks). Results are scored, gated, and exportable as JSON, YAML, or PDF. An LLM Tool Selection Comparison tab enables side-by-side evaluation across multiple LLM providers.

## 2. Tech Stack

| Layer | Technology | Version Constraint |
|-------|------------|-------------------|
| Backend runtime | Python | >= 3.11 |
| Web framework | FastAPI | >= 0.115.0 |
| ASGI server | Uvicorn | >= 0.30.0 |
| HTTP client | httpx | >= 0.27.0 |
| ORM / DB toolkit | SQLAlchemy (async) | >= 2.0 |
| SQLite driver | aiosqlite | >= 0.20.0 |
| PostgreSQL driver (optional) | asyncpg | >= 0.30.0 |
| Config loading | python-dotenv | >= 1.0.0 |
| YAML serialization | PyYAML | >= 6.0 |
| Data validation | Pydantic (via FastAPI) | v2 |
| Frontend framework | React | ^18.3.0 |
| Build tool | Vite | ^5.4.0 |
| CSS framework | Tailwind CSS | ^3.4.0 |
| Language (frontend) | TypeScript | ^5.5.0 |
| Testing | pytest + pytest-asyncio | >= 8.0 / >= 0.24.0 |

## 3. Project Structure

```
mcp-tools-fetch/
├── pyproject.toml                  # Python project metadata and dependencies
├── Makefile                        # Setup, start, stop, test, lint, clean targets
├── Dockerfile / docker-compose.yml # Container build and deployment
├── llm.json.example                # Multi-LLM config template (all providers)
├── .env.example                    # Environment variable template
├── src/
│   ├── app/                        # FastAPI backend package
│   │   ├── __init__.py
│   │   ├── main.py                 # Application entry point, lifespan, CORS, static mount
│   │   ├── config.py               # Config load/save helpers, env and DB URL resolution
│   │   ├── models.py               # Pydantic models (server config, OAuth, API key, tool info)
│   │   ├── database.py             # SQLAlchemy async engine, ORM models, CRUD, migrations
│   │   ├── auth.py                 # Auth engine (bearer, API key, OAuth+PKCE, DCR, discovery)
│   │   ├── mcp_client.py           # JSON-RPC 2.0 client with session management and retry
│   │   ├── tools_store.py          # YAML persistence for tool definitions (fetch + upload)
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── servers.py          # CRUD endpoints for server configurations
│   │   │   ├── tools.py            # Tools, evaluation, ground truth, upload, export endpoints
│   │   │   └── auth_routes.py      # Auth status, token save, OAuth start/callback, discovery
│   │   └── eval/                   # Evaluation engine
│   │       ├── models.py           # EvalReport, LayerResult, CheckResult dataclasses
│   │       ├── protocol.py         # Layer 1: MCP spec compliance (12 checks)
│   │       ├── quality.py          # Layer 2: Tool quality & overlap detection (11 checks)
│   │       ├── security.py         # Layer 3: Security analysis (6 checks)
│   │       ├── llm_eval.py         # Layer 4: LLM-assisted evaluation (5+ checks)
│   │       ├── scoring.py          # Scoring weights, gate logic, apply_scoring()
│   │       ├── overlap.py          # Tool overlap detection (name/desc/schema similarity)
│   │       ├── runner.py           # Orchestrates all layers
│   │       ├── model_adapter.py    # LLM provider adapters (Anthropic, OpenAI, VertexAI, Gemini)
│   │       ├── llm_config.py       # Multi-LLM config loader (llm.json + .env fallback)
│   │       └── regression.py       # Report comparison for regression tracking
│   └── frontend/                   # React SPA
│       ├── package.json
│       ├── vite.config.ts          # Vite config with API proxy and build output
│       ├── tsconfig.json
│       ├── index.html
│       └── src/
│           ├── main.tsx            # React DOM entry point
│           ├── App.tsx             # Root component, view routing, toast state
│           ├── api.ts              # HTTP client layer wrapping fetch()
│           ├── types.ts            # TypeScript interfaces mirroring backend models
│           ├── utils/
│           │   └── download.ts     # JSON/YAML/PDF export (jspdf + jspdf-autotable + js-yaml)
│           └── components/
│               ├── ServerList.tsx   # Server cards with status, connect, evaluate
│               ├── ServerForm.tsx   # Modal form for add/edit with OAuth auto-discovery
│               ├── ToolsViewer.tsx  # Tool list, tabs, export, upload/template/delete
│               ├── EvaluationView.tsx  # Evaluation report with false positive marking
│               ├── ComparisonView.tsx  # LLM Tool Selection comparison across providers
│               ├── DownloadModal.tsx   # Export options modal (JSON/YAML/PDF format selector)
│               ├── AboutPage.tsx       # In-app evaluation rules & config reference
│               └── Toast.tsx           # Notification toast component
├── tests/                          # pytest test suite (540+ tests)
│   ├── __init__.py
│   ├── conftest.py                 # Shared fixtures (isolated SQLite DB per test)
│   ├── eval/                       # Evaluation engine tests
│   │   ├── test_protocol.py
│   │   ├── test_quality.py
│   │   ├── test_security.py
│   │   ├── test_llm_eval.py
│   │   ├── test_scoring.py
│   │   ├── test_overlap.py
│   │   └── ...
│   ├── test_auth.py
│   ├── test_config.py
│   ├── test_database.py
│   ├── test_mcp_client.py
│   ├── test_routes_servers.py
│   ├── test_routes_tools.py
│   └── test_tools_store.py
├── tools/                          # YAML files (one per server, fetched or uploaded)
│   └── {server_name}.yaml         # Contains: server, tools_count, source, tools
├── docs/
│   ├── architecture.md             # This file
│   ├── development.md              # Development guide
│   ├── RULES.md                    # Complete evaluation rule reference
│   └── design.md                   # Original design spec
└── static/                         # Production build output (Vite builds here)
    └── index.html
```

## 4. Backend Architecture

### 4.1 FastAPI Application (`main.py`)

The application is created with an async lifespan context manager that initializes the database on startup and disposes the engine on shutdown.

```
Startup:  init_db()  -->  create tables  -->  migrate tokens.json  -->  migrate mcp.json
Shutdown: dispose_db()
```

Three routers are mounted on the app:

| Router | Prefix | Tags |
|--------|--------|------|
| `servers.router` | `/api/servers` | servers |
| `auth_routes.router` | `/api/auth` | auth |
| `tools.router` | `/api/servers` | tools |

CORS is configured to allow the Vite dev server origin (`http://localhost:5173`). If a `static/` directory exists at the project root, it is mounted as a catch-all for serving the production frontend build.

### 4.2 Database Layer (`database.py`)

Uses SQLAlchemy 2.0 async with `create_async_engine` and `async_sessionmaker`. The database URL is resolved at startup:

1. If `DATABASE_URL` is set, use it (auto-converting `postgresql://` to `postgresql+asyncpg://`).
2. Otherwise, default to `sqlite+aiosqlite:///mcp_secrets.db` in the working directory.

Tables are created via `Base.metadata.create_all` on startup. Two migration functions run once (when their target table is empty):

- `_migrate_tokens_json()` -- imports legacy `tokens.json` into `mcp_secrets`.
- `_migrate_mcp_json()` -- imports legacy `mcp.json` into `mcp_servers`.

CRUD functions (`get_secret`, `set_secret`, `delete_secret`, `get_all_servers`, `get_server_config`, `set_server_config`, `delete_server_config`) each open their own session via the session factory, using `async with session.begin()` for write operations.

### 4.3 Auth Engine (`auth.py`)

Supports four authentication modes:

| Mode | `auth_mode` value | Credential Source |
|------|-------------------|-------------------|
| Bearer Token | `bearer_token` (or `None`) | Env var `MCP_<NAME>_TOKEN` or DB `mcp_secrets` |
| API Key | `api_key` | DB `mcp_secrets` (type `apikey`) |
| OAuth Authorization Code | `oauth` | OAuth flow with PKCE; tokens in DB `mcp_secrets` |
| Dynamic Client Registration | `dcr` | DCR endpoint registers client; then OAuth flow |

**OAuth flow with PKCE:**

1. `start_oauth_flow()` generates a `code_verifier`, derives a S256 `code_challenge`, creates a random `state`, and builds the authorization URL.
2. For DCR mode, the client is first registered via `_register_dcr_client()` (POST to `registration_endpoint`). Registration data is cached in `mcp_secrets` (type `dcr`).
3. In-progress flows are held in an in-memory `_pending_flows` dict keyed by `state`.
4. `handle_oauth_callback()` exchanges the authorization code for tokens at the token endpoint, including the `code_verifier` for PKCE validation.
5. Access token, refresh token, and token type are persisted in `mcp_secrets` (type `oauth`).

**Token refresh:** `refresh_access_token()` uses the stored refresh token to obtain a new access token. On success, the new tokens replace the old ones in the database. On failure, it returns `None` (caller clears tokens and requires re-authentication).

**OAuth auto-discovery:** `discover_oauth_metadata()` probes `.well-known/openid-configuration` and `.well-known/oauth-authorization-server` at progressively shorter path prefixes derived from the server URL. Returns authorization, token, and registration endpoints plus supported scopes and grant types.

### 4.4 MCP Client (`mcp_client.py`)

Implements JSON-RPC 2.0 over streamable HTTP, targeting MCP protocol version `2024-11-05`.

**Request construction (`_make_jsonrpc_request`):**
- Sets `Content-Type: application/json` and `Accept: application/json, text/event-stream`.
- Attaches `Authorization: Bearer <token>` header for bearer/OAuth auth.
- For API key auth, places the key in a header or query parameter based on `api_key_config.location`.
- Tracks `Mcp-Session-Id` header across requests within a session.
- Handles both JSON and SSE response formats (SSE is parsed by scanning `data:` lines for JSON-RPC results).

**Connection flow (`mcp_list_tools`):**
1. Send `initialize` request with client info and protocol version.
2. Send `notifications/initialized` notification (no `id` field, no response expected).
3. Send `tools/list` request to retrieve available tools.

**Token refresh with retry (`_try_request_with_refresh`):**
1. Attempt the request with the current token.
2. On 401/403 for OAuth/DCR servers, call `refresh_access_token()` to get a new token.
3. Retry the request with the refreshed token.
4. If refresh fails or the retry still returns 401/403, clear tokens and raise `ReAuthRequired`.
5. For bearer/API key modes, 401/403 immediately raises `ReAuthRequired` (no auto-refresh).

### 4.5 Tools Store (`tools_store.py`)

Persists tool definitions as YAML files in a `tools/` directory. Each server gets one file named `<server_name>.yaml` containing `server`, `tools_count`, `source`, and `tools` keys. Server names are validated against `[A-Za-z0-9_-]+` to prevent path traversal.

| Function | Description |
|----------|-------------|
| `save_tools(name, tools, source="fetched")` | Write tools to YAML. `source` is `"fetched"` (from server) or `"uploaded"` (manual). |
| `load_tools(name)` | Returns `{"tools": [...], "source": "fetched"|"uploaded"}` or `None` if no file exists. Defaults `source` to `"fetched"` for legacy files without the field. |
| `delete_tools(name)` | Removes the YAML file. Returns `True` if deleted, `False` if not found. |

Both fetch and upload write to the same file — whichever runs last wins. Re-fetching from the server overrides uploaded tools; uploading overrides previously fetched tools.

### 4.6 Evaluation Engine (`eval/`)

The evaluation engine runs four layers of checks against tool definitions:

```
tools ──> protocol.check_protocol_all()  ──┐
      ──> quality.check_quality_all()    ──┤
      ──> security.check_security_all()  ──┼──> EvalReport ──> apply_scoring() ──> scored report
      ──> llm_eval.check_llm_all()       ──┘                                       (with gate)
```

**Layer results** (`models.py`): Each layer returns a `LayerResult` containing per-tool `CheckResult` objects, a catalog-level check list, and a score (computed by `apply_scoring()`).

**Scoring** (`scoring.py`): Each check result is weighted by severity (Critical=5, High=3, Medium=2, Low=1, Info=0.5). Layer scores are combined with configurable weights (protocol=0.15, quality=0.10, security=0.10, llm=0.10), auto-normalizing based on which layers are present. The gate passes when the overall score >= 70.0 AND there are no critical failures in protocol or security layers.

**LLM evaluation** (`llm_eval.py`): Five checks that probe tools from an AI agent's perspective — description clarity, tool selection, argument generation, overlap disambiguation, and safety resistance. Uses `model_adapter.py` for provider-agnostic LLM calls (OpenAI, Anthropic, VertexAI, Gemini). Tool selection asks the LLM which tool it would choose — **no tool is ever executed**.

**Multi-LLM** (`llm_config.py`): Loads named LLM configurations from `llm.json` (with `_env` suffix convention for secrets). The evaluation endpoint accepts a `llms` query parameter for running multiple configs in parallel. Results are stored as `per_llm` in the eval report metadata.

**Ground truth**: Users can upload YAML test cases with expected tool selections and prompts. When present, these are used alongside auto-generated scenarios in LLM tool selection checks.

**Overlap detection** (`overlap.py`): Detects similar tools using weighted name (30%), description (40%), and schema (30%) similarity. Pairs exceeding threshold (0.6) are flagged.

## 5. Frontend Architecture

### 5.1 Build and Dev Setup

The frontend is a React SPA built with Vite. During development, the Vite dev server runs on port 5173 and proxies `/api` requests to the FastAPI backend on port 5002. For production, `vite build` outputs to `../../static` (project root `static/`), which FastAPI serves as static files.

### 5.2 Component Hierarchy

```
App
├── ServerList              # Main view: server cards with actions
│   └── (inline)            # Status indicator, connect/edit/delete buttons
├── ServerForm              # Modal overlay for creating/editing servers
│   └── (inline)            # OAuth auto-discover button, auth mode fields
├── ToolsViewer             # Full-page view for a selected server
│   ├── [Tools tab]         # Search, expand/collapse, parameter table, raw schema
│   │   └── (inline)        # Upload/Template/Remove/Re-fetch buttons, source badge
│   ├── [Evaluate tab]
│   │   └── EvaluationView  # Multi-layer report with false positive marking, gate hints
│   ├── [LLM Tool Selection tab]
│   │   └── ComparisonView  # Side-by-side LLM tool selection comparison
│   └── DownloadModal       # Export options (JSON/YAML/PDF format, section selection)
├── AboutPage               # In-app evaluation rules & configuration reference
└── Toast                   # Floating notification
```

**View routing:** `App` maintains a `view` state. Renders `ServerList` (default), `ToolsViewer` (when a server is selected), or `AboutPage`. `ServerForm` is shown as a modal overlay. No react-router — state-based routing only.

### 5.3 API Client Layer (`api.ts`)

A thin wrapper around `fetch()` that prefixes all URLs with `/api`, sets JSON content-type headers, and throws on non-OK responses with the server's error detail. Functions map 1:1 to backend endpoints:

| Function | Method | Endpoint |
|----------|--------|----------|
| `listServers()` | GET | `/api/servers` |
| `getServer(name)` | GET | `/api/servers/{name}` |
| `createServer(name, config)` | POST | `/api/servers?name={name}` |
| `updateServer(name, config)` | PUT | `/api/servers/{name}` |
| `deleteServer(name)` | DELETE | `/api/servers/{name}` |
| `testConnection(name)` | POST | `/api/servers/{name}/test` |
| `fetchTools(name)` | POST | `/api/servers/{name}/fetch-tools` |
| `getTools(name)` | GET | `/api/servers/{name}/tools` |
| `uploadTools(name, file)` | POST | `/api/servers/{name}/tools/upload` |
| `downloadToolsTemplate(name)` | GET | `/api/servers/{name}/tools/template` |
| `deleteUploadedTools(name)` | DELETE | `/api/servers/{name}/tools/uploaded` |
| `evaluateTools(name)` | GET | `/api/servers/{name}/evaluate` |
| `evaluateToolsFull(name)` | GET | `/api/servers/{name}/evaluate/full` |
| `getEvalReport(name)` | GET | `/api/servers/{name}/evaluate/report` |
| `evaluateLlm(name, llms?)` | GET | `/api/servers/{name}/evaluate/llm` |
| `markFalsePositive(name, key, justification)` | POST | `/api/servers/{name}/evaluate/false-positive` |
| `uploadGroundTruth(name, file)` | POST | `/api/servers/{name}/ground-truth` |
| `getGroundTruth(name)` | GET | `/api/servers/{name}/ground-truth` |
| `deleteGroundTruth(name)` | DELETE | `/api/servers/{name}/ground-truth` |
| `downloadGroundTruthTemplate(name)` | GET | `/api/servers/{name}/ground-truth/template` |
| `getLlmConfigs()` | GET | `/api/llm-configs` |
| `getAuthStatus(name)` | GET | `/api/auth/status/{name}` |
| `startAuth(name)` | POST | `/api/auth/start/{name}` |
| `saveBearerToken(name, token)` | POST | `/api/auth/bearer-token/{name}` |
| `saveApiKey(name, key)` | POST | `/api/auth/api-key/{name}` |
| `discoverOAuthEndpoints(url)` | POST | `/api/auth/discover` |

### 5.4 Export System (`utils/download.ts`)

Client-side export supporting three formats:

| Format | Library | Details |
|--------|---------|---------|
| JSON | Native | Structured dump of tools, eval report, comparison data |
| YAML | js-yaml | Same structure as JSON, serialized via `dump()` |
| PDF | jspdf + jspdf-autotable | Formatted tables with color-coded status cells |

The `DownloadModal` component lets users select which sections to include (tool overview, parameters, schemas, eval layers, false positives, LLM comparison) and which format to export. Comparison data is built from `per_llm` in the eval report metadata.

### 5.4 Post-OAuth Redirect Handling

After a successful OAuth callback, the backend redirects the browser to `http://localhost:5173?auth_success=<server_name>`. The `App` component detects this query parameter on mount, strips it from the URL, and automatically runs the connect flow (test connection then fetch tools) for that server.

## 6. Auth Flows

### 6.1 Bearer Token

```
User enters token in ServerForm
  --> POST /api/auth/bearer-token/{name}  (token saved to mcp_secrets)
  --> Connect button triggers POST /api/servers/{name}/test
  --> Authorization: Bearer <token> header sent to MCP server
```

The token is also checked from the environment variable `MCP_<SERVER_NAME>_TOKEN` (with hyphens converted to underscores, uppercased).

### 6.2 API Key

```
User enters API key in ServerForm
  --> POST /api/auth/api-key/{name}  (key saved to mcp_secrets)
  --> Connect button triggers POST /api/servers/{name}/test
  --> Key sent as header (default X-API-Key) or query parameter per api_key_config
```

### 6.3 OAuth (Authorization Code + PKCE)

```
1. User clicks Connect (or re-auth triggered by 401)
2. Frontend: POST /api/auth/start/{name}
3. Backend:
   a. Generate code_verifier + S256 code_challenge
   b. Generate random state
   c. Build authorization URL with response_type=code, client_id, redirect_uri,
      state, code_challenge, code_challenge_method=S256, scope
   d. Store flow data in _pending_flows[state]
   e. Open browser to authorization URL
4. User authenticates with OAuth provider
5. Provider redirects to GET /api/auth/callback?code=...&state=...
6. Backend:
   a. Look up flow by state
   b. POST to token_endpoint with grant_type=authorization_code, code,
      redirect_uri, client_id, code_verifier (and client_secret if available)
   c. Save access_token + refresh_token to mcp_secrets
7. Backend redirects browser to http://localhost:5173?auth_success=<name>
8. Frontend detects auth_success, runs test + fetch-tools automatically
```

### 6.4 DCR (Dynamic Client Registration)

Same as OAuth flow above, with an additional first step:

```
0. Backend checks mcp_secrets for cached DCR data (client_id, client_secret)
   If not found:
     a. POST to registration_endpoint with client_name, redirect_uris,
        grant_types, response_types, token_endpoint_auth_method, scope
     b. Cache client_id + client_secret in mcp_secrets (type "dcr")
   Then proceed with OAuth flow using the registered client credentials
```

## 7. Data Flow -- Connect Operation

When a user clicks "Connect" on a server in the UI:

```
Frontend (ServerList)                Backend                          Remote MCP Server
─────────────────────               ───────                          ─────────────────
1. Check auth status
   GET /api/auth/status/{name}  --> get_auth_status()
                                    Check mcp_secrets for token

2. If not authenticated + OAuth:
   POST /api/auth/start/{name}  --> start_oauth_flow()
                                    [OAuth browser flow - see section 6.3]

3. Test connection
   POST /api/servers/{name}/test -> mcp_initialize()
                                    JSON-RPC: initialize  ----------> MCP server
                                                          <---------- serverInfo

4. Fetch tools
   POST /api/servers/{name}/     -> mcp_list_tools()
        fetch-tools                 JSON-RPC: initialize  ----------> MCP server
                                                          <---------- capabilities
                                    JSON-RPC: notifications/
                                              initialized ----------> MCP server
                                    JSON-RPC: tools/list  ----------> MCP server
                                                          <---------- tool definitions
                                    save_tools()
                                    Write tools/<name>.yaml

5. Display tools
   Frontend navigates to ToolsViewer
   (tools returned inline from fetch-tools response)
```

If a 401/403 occurs during steps 3 or 4 for OAuth/DCR servers, the backend attempts a token refresh. If the refresh fails, the frontend is notified via `reauth: true` in the response and triggers re-authentication.

## 8. Database Schema

### Table: `mcp_secrets`

Stores authentication credentials (tokens, API keys, OAuth data, DCR registrations).

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `server_name` | `String(255)` | PK (composite) | Name of the MCP server |
| `secret_type` | `String(50)` | PK (composite) | One of: `bearer`, `apikey`, `oauth`, `dcr` |
| `secret_data` | `Text` | NOT NULL | JSON-encoded secret payload |
| `updated_at` | `DateTime` | NOT NULL | Last modification timestamp (UTC) |

**`secret_data` payloads by `secret_type`:**

| `secret_type` | JSON structure |
|----------------|---------------|
| `bearer` | `{"token": "..."}` |
| `apikey` | `{"key": "..."}` |
| `oauth` | `{"access_token": "...", "refresh_token": "...", "token_type": "Bearer"}` |
| `dcr` | `{"client_id": "...", "client_secret": "..."}` |

### Table: `mcp_servers`

Stores MCP server configurations.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `name` | `String(255)` | PK | Unique server name |
| `config_data` | `Text` | NOT NULL | JSON-encoded `McpServerConfig` |
| `updated_at` | `DateTime` | NOT NULL | Last modification timestamp (UTC) |

**`config_data` structure** (matches `McpServerConfig` Pydantic model):

```json
{
  "enabled": true,
  "url": "https://example.com/mcp",
  "transport": "streamable_http",
  "ssl_verify": true,
  "auth": false,
  "description": "",
  "auth_mode": null,
  "oauth": null,
  "api_key_config": null,
  "timeout": 30
}
```

## 9. API Endpoints

### Servers (`/api/servers`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/servers` | List all server configurations |
| `GET` | `/api/servers/{name}` | Get a single server configuration |
| `POST` | `/api/servers?name={name}` | Create a new server (409 if exists) |
| `PUT` | `/api/servers/{name}` | Update an existing server (404 if not found) |
| `DELETE` | `/api/servers/{name}` | Delete a server (404 if not found) |

### Tools (`/api/servers`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/servers/{name}/test` | Test MCP connection (initialize handshake) |
| `POST` | `/api/servers/{name}/fetch-tools` | Fetch tools from MCP server and save to YAML |
| `GET` | `/api/servers/{name}/tools` | Get cached tools (includes `source` field) |
| `POST` | `/api/servers/{name}/tools/upload` | Upload tool definitions via YAML (max 2MB) |
| `GET` | `/api/servers/{name}/tools/template` | Download YAML template for tool definitions |
| `DELETE` | `/api/servers/{name}/tools/uploaded` | Delete manually uploaded tools (rejects fetched) |

### Evaluation (`/api/servers`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/servers/{name}/evaluate` | Quick compatibility evaluation |
| `GET` | `/api/servers/{name}/evaluate/full` | Full multi-layer evaluation (protocol + quality + security) |
| `GET` | `/api/servers/{name}/evaluate/report` | Get cached evaluation report |
| `GET` | `/api/servers/{name}/evaluate/llm` | LLM-assisted evaluation (accepts `?llms=name1,name2`) |
| `POST` | `/api/servers/{name}/evaluate/false-positive` | Mark/unmark a check as false positive |

### Ground Truth (`/api/servers`)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/servers/{name}/ground-truth` | Upload ground truth YAML (max 1MB) |
| `GET` | `/api/servers/{name}/ground-truth` | Get ground truth data |
| `DELETE` | `/api/servers/{name}/ground-truth` | Delete ground truth |
| `GET` | `/api/servers/{name}/ground-truth/template` | Download ground truth YAML template |

### LLM Configuration

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/llm-configs` | List available LLM configurations from `llm.json` |

### Auth (`/api/auth`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/auth/status/{name}` | Get authentication status for a server |
| `POST` | `/api/auth/bearer-token/{name}` | Save a bearer token |
| `POST` | `/api/auth/api-key/{name}` | Save an API key |
| `POST` | `/api/auth/discover` | Auto-discover OAuth endpoints from .well-known URLs |
| `POST` | `/api/auth/start/{name}` | Start OAuth/DCR flow (opens browser) |
| `GET` | `/api/auth/callback` | OAuth callback handler (receives code + state) |

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check (returns `{"status": "ok"}`) |

## 10. Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | No | `sqlite+aiosqlite:///mcp_secrets.db` | Database connection string. Supports SQLite and PostgreSQL. |
| `MCP_<NAME>_TOKEN` | No | -- | Bearer token for a server (name uppercased, hyphens to underscores) |
| `<client_secret_env>` | No | -- | OAuth client secret, referenced by server config's `oauth.client_secret_env` |

Environment variables are loaded from a `.env` file via `python-dotenv`.

### Ports

| Service | Default Port |
|---------|-------------|
| FastAPI backend (Uvicorn) | 5002 |
| Vite dev server | 5173 |

### Database URL Resolution

1. Check `DATABASE_URL` environment variable.
2. If it starts with `postgresql://`, rewrite to `postgresql+asyncpg://`.
3. If `DATABASE_URL` is not set, use `sqlite+aiosqlite:///<cwd>/mcp_secrets.db`.

### Legacy File Migration

On first startup with an empty database, the application automatically migrates data from:

- `tokens.json` -- bearer tokens, API keys, OAuth tokens, DCR registrations (keyed by `<server>_bearer`, `<server>_apikey`, etc.)
- `mcp.json` -- server configurations under `mcpServers` key

Migration runs only when the corresponding table is empty, so it is safe on subsequent startups.

## 11. Testing

### Framework

Tests use `pytest` with `pytest-asyncio` for async test support.

### Test Isolation (`conftest.py`)

The `db` fixture provides a fully isolated database per test:

1. Creates a temporary SQLite database in `tmp_path` (pytest-provided temp directory).
2. Monkeypatches `get_database_url` to return the temp database path.
3. Monkeypatches `_migrate_tokens_json` and `_migrate_mcp_json` to no-ops (prevents interference from filesystem files).
4. Resets the module-level `_engine` and `_session_factory` to `None`.
5. Calls `init_db()` to create tables.
6. Yields for the test to run.
7. Calls `dispose_db()` for cleanup.

This ensures each test gets a fresh, empty database with the schema created but no migrated data.

### Test Modules

| Module | Coverage Area |
|--------|---------------|
| `test_database.py` | CRUD operations for secrets, server configs, eval reports, ground truth |
| `test_auth.py` | Token resolution, bearer/API key storage, auth status |
| `test_config.py` | Config load/save round-trip through database |
| `test_mcp_client.py` | JSON-RPC request construction, SSE parsing, retry logic |
| `test_routes_servers.py` | Server CRUD endpoint behavior (create, get, update, delete, conflict/404) |
| `test_routes_tools.py` | Tool fetching, caching, evaluation, false positive, ground truth endpoints |
| `test_tools_store.py` | YAML save/load, source tracking, delete, server name validation |
| `eval/test_protocol.py` | Protocol compliance checks |
| `eval/test_quality.py` | Tool quality checks |
| `eval/test_security.py` | Security analysis checks |
| `eval/test_llm_eval.py` | LLM-assisted evaluation checks |
| `eval/test_scoring.py` | Scoring weights, gate logic |
| `eval/test_overlap.py` | Tool overlap detection |
| `eval/test_runner.py` | Full evaluation orchestration |
