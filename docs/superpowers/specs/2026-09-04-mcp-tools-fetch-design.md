# MCP Tools Fetch — Design Spec

## Overview

A Python + React application that reads MCP server configurations from `mcp.json`, authenticates using multiple auth flows (SSO, DCR, OAuth), fetches available tools via JSON-RPC `tools/list`, and stores results in per-server YAML files. Includes a web UI for managing configurations, testing connections, and browsing fetched tools.

## Architecture

Single FastAPI application serving both REST API endpoints and the built React frontend.

```
Browser (React + Tailwind CSS)
    ↕ REST API
FastAPI Backend
    ├── Config Manager     → reads/writes mcp.json
    ├── Secrets Manager    → reads .env (python-dotenv)
    ├── Auth Engine        → handles SSO / DCR / OAuth flows
    ├── MCP Client         → JSON-RPC over streamable HTTP
    └── Tools Store        → writes per-server YAML to tools/
```

### Data Flow — Fetching Tools

1. User clicks "Fetch Tools" for a server in the UI
2. Frontend calls `POST /api/servers/{name}/fetch-tools`
3. Backend resolves auth for that server (token from .env for SSO, OAuth dance for DCR/OAuth)
4. Backend sends JSON-RPC `initialize` → `tools/list` to the MCP server
5. Response is saved to `tools/{server-name}.yaml`
6. Result returned to frontend for display

## Auth Flows

### SSO
- Read JWT from `.env` variable using convention `MCP_{SERVER_NAME_UPPER}_TOKEN`
- Pass as `Authorization: Bearer <token>` header on all requests

### OAuth (authorization_code)
- `client_id` from mcp.json, `client_secret` from `.env` via the `client_secret_env` field
- Backend starts local callback server, opens browser for user authorization
- Exchanges authorization code for access + refresh tokens
- Tokens stored in `tokens.json` (gitignored)
- Refresh tokens used when access tokens expire

### DCR (Dynamic Client Registration)
- Backend POSTs to `registration_endpoint` to obtain `client_id` / `client_secret`
- Registered credentials stored in `tokens.json` alongside OAuth tokens so re-registration isn't needed each time
- Then follows the same OAuth authorization_code flow for authorization/token exchange

### Token Storage
After a successful OAuth/DCR flow, tokens (access + refresh) are stored in `tokens.json` (gitignored). On subsequent requests, the backend checks for a valid token before initiating a new auth flow.

## API Endpoints

```
GET    /api/servers                      → list all MCP server configs
GET    /api/servers/{name}               → get single server config
POST   /api/servers                      → add new server config
PUT    /api/servers/{name}               → update server config
DELETE /api/servers/{name}               → delete server config

POST   /api/servers/{name}/test          → test connection (auth + initialize)
POST   /api/servers/{name}/fetch-tools   → fetch tools/list, save to YAML
GET    /api/servers/{name}/tools         → read saved tools from YAML

GET    /api/auth/callback                → OAuth/DCR redirect callback handler
GET    /api/auth/status/{name}           → check if server has a valid token
```

### .env Variable Naming

- SSO tokens: `MCP_{SERVER_NAME_UPPER}_TOKEN` (e.g., `MCP_DATAVERSE_MCP_TOKEN`)
- OAuth client secrets: use the `client_secret_env` field from mcp.json (e.g., `MCP_SLACK_MCP_GOLDEN_GATE_CLIENT_SECRET`)

## Frontend UI

Single-page React + Tailwind CSS app with three views:

### Server List (home page)
- Table of configured MCP servers: name, URL, auth_mode, enabled status
- Status indicator (colored dot) — connected/disconnected/unknown
- Action buttons per row: Edit, Test Connection, Fetch Tools
- "Add Server" button at top

### Server Form (modal)
- Fields: name, URL, transport, description, enabled toggle, ssl_verify toggle, auth toggle, auth_mode dropdown (sso/dcr/oauth)
- Conditional sections based on auth_mode:
  - **SSO:** shows the env variable name it will look for
  - **OAuth:** client_id, client_secret_env, authorization_endpoint, token_endpoint, scopes (tag input), grant_type
  - **DCR:** registration_endpoint, authorization_endpoint, token_endpoint, scopes (tag input)
- Save / Cancel buttons

### Tools Viewer (expandable section)
- After fetching tools, shows the list of tools with name, description, and input schema
- Collapsible cards per tool showing the full JSON schema
- "Re-fetch" button

### Interactions
- "Test Connection" → calls `/api/servers/{name}/test`, shows success/error toast
- "Fetch Tools" → calls `/api/servers/{name}/fetch-tools`, on success shows tools view
- For OAuth/DCR: backend opens browser for auth, UI polls `/api/auth/status/{name}` until token is available, then proceeds

## Project Structure

```
mcp-tools-fetch/
├── pyproject.toml              # uv project — FastAPI, httpx, python-dotenv, pyyaml
├── mcp.json                    # MCP server configurations
├── .env                        # Secrets (JWT tokens, client secrets)
├── .gitignore                  # .env, tokens.json, node_modules, static/
├── tokens.json                 # OAuth/DCR tokens (auto-generated, gitignored)
├── tools/                      # YAML output per MCP server
│   ├── atlan-mcp.yaml
│   └── jira-mcp.yaml
├── src/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app, static file serving, CORS
│   │   ├── config.py           # Load/save mcp.json, .env reading
│   │   ├── auth.py             # SSO, OAuth, DCR auth engines
│   │   ├── mcp_client.py       # JSON-RPC client (initialize + tools/list)
│   │   ├── tools_store.py      # Read/write YAML tool files
│   │   ├── routes/
│   │   │   ├── servers.py      # CRUD endpoints for server configs
│   │   │   ├── auth_routes.py  # OAuth callback, auth status
│   │   │   └── tools.py        # Fetch tools, read tools endpoints
│   │   └── models.py           # Pydantic models for API request/response
│   └── frontend/
│       ├── package.json        # React, Tailwind, Vite
│       ├── vite.config.ts      # Proxy /api → FastAPI dev server
│       ├── tailwind.config.js
│       ├── index.html
│       └── src/
│           ├── App.tsx
│           ├── api.ts          # API client functions
│           ├── components/
│           │   ├── ServerList.tsx
│           │   ├── ServerForm.tsx
│           │   └── ToolsViewer.tsx
│           └── types.ts
└── static/                     # Built frontend (served by FastAPI in prod)
```

## Dependencies

### Backend
- `fastapi` — web framework
- `uvicorn` — ASGI server
- `httpx` — async HTTP client for MCP calls
- `python-dotenv` — .env file loading
- `pyyaml` — YAML read/write for tools output
- `pydantic` — data models (bundled with FastAPI)

### Frontend
- `react`, `react-dom` — UI framework
- `tailwindcss` — utility CSS
- `vite` — build tool
- `typescript` — type safety

## Running the App

- **Dev:** `uv run uvicorn src.app.main:app --reload` + `cd src/frontend && npm run dev` (Vite proxies `/api` to FastAPI on port 8000)
- **Prod:** `cd src/frontend && npm run build` (output to `../../static/`), then `uv run uvicorn src.app.main:app`
