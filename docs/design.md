# MCP Tools Fetch -- Design Document

## 1. Design Goals

The architecture is driven by three primary goals:

- **Single deployable unit.** A developer should be able to `pip install` and `uvicorn` a single process that serves both the API and the React UI. The FastAPI app conditionally mounts a `StaticFiles` handler from `static/` when a production build exists, so the same binary works in dev (Vite proxy) and prod (embedded static assets).

- **Multi-auth flexibility.** MCP servers in the wild use a variety of authentication schemes: bearer tokens in environment variables, API keys in headers or query parameters, OAuth 2.0 Authorization Code with PKCE, and Dynamic Client Registration (DCR). The system treats auth mode as a per-server configuration property (`auth_mode` field on `McpServerConfig`) rather than a global setting, so a single instance can manage servers with different auth requirements simultaneously.

- **Extensibility without coupling.** The server config model (`McpServerConfig`) is a flat Pydantic model with optional sub-models (`OAuthConfig`, `ApiKeyConfig`). New auth modes or transport types can be added by extending the model and adding a branch in `get_token()` / `_make_jsonrpc_request()` without restructuring the database schema, since config is stored as serialized JSON.

---

## 2. Key Design Decisions

### 2.1 Why Monolith (FastAPI + React in One Repo)

The backend and frontend live in a single repository (`src/app/` and `src/frontend/`). This is intentional:

- The frontend is a thin management UI, not a standalone product. It exists solely to configure and query the backend.
- A monorepo eliminates version skew between API contracts and TypeScript types. The `types.ts` interface mirrors `models.py` exactly.
- Production deployment mounts the Vite build output at the FastAPI root via `StaticFiles(directory="static", html=True)`, producing a single-process deployment.
- CORS is configured for `localhost:5173` (the Vite dev server) to support the split dev workflow.

### 2.2 Why SQLite as Default DB with PostgreSQL Option

`config.get_database_url()` returns a SQLite path by default (`mcp_secrets.db` in the working directory) and accepts a `DATABASE_URL` environment variable for PostgreSQL:

```python
if url.startswith("postgresql://"):
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)
```

Rationale:

- SQLite requires zero setup for local development and single-user deployments.
- The database stores only server configs and auth secrets (small data, low write concurrency), which is well within SQLite's capabilities.
- PostgreSQL support is a one-line URL swap, using `asyncpg` as the async driver. This matters for team deployments or containerized environments where a shared, durable store is needed.

### 2.3 Why Async Everywhere

All database access uses `sqlalchemy.ext.asyncio` (`create_async_engine`, `async_sessionmaker`). All HTTP calls use `httpx.AsyncClient`. Every route handler is `async def`.

Rationale:

- The primary workload is I/O-bound: HTTP calls to MCP servers and OAuth providers. Async allows the server to handle concurrent connection-test and tool-fetch operations without thread pool exhaustion.
- SQLAlchemy async with `aiosqlite` / `asyncpg` keeps the entire call stack non-blocking, avoiding the need to mix sync and async session management.

### 2.4 Why YAML for Tools Storage

Fetched tools are persisted to `tools/{server_name}.yaml` via `tools_store.py`, not to the database:

```python
yaml.dump(
    {"server": server_name, "tools_count": len(tools), "tools": tools},
    f, default_flow_style=False, sort_keys=False, allow_unicode=True,
)
```

Rationale:

- YAML is human-readable. Operators can inspect, diff, or version-control the tool definitions outside the application.
- Tool definitions are read-only reference data (the app fetches and displays them but does not modify them). Storing them in the database would add schema complexity without benefit.
- The `_validate_server_name()` function enforces `[A-Za-z0-9_-]+` to prevent path-traversal attacks in the filename.

### 2.5 Why OAuth PKCE

Every OAuth flow uses PKCE (Proof Key for Code Exchange) with S256 challenge method, regardless of whether a client secret is available:

```python
code_verifier = secrets.token_urlsafe(64)
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b"=").decode()
```

Rationale:

- PKCE protects against authorization code interception attacks. This is essential because `mcp-tools-fetch` uses a localhost redirect URI (`http://localhost:5002/api/auth/callback`), making the callback susceptible to port-stealing attacks on multi-user machines.
- For DCR clients (which may not have a client secret), PKCE is the only viable proof of the authorization request's origin.
- Including PKCE even when a client secret exists adds defense-in-depth at negligible cost.

### 2.6 Why DCR Support

Dynamic Client Registration (`auth_mode: "dcr"`) allows the app to register itself as an OAuth client at runtime by POSTing to the provider's registration endpoint:

```python
payload = {
    "client_name": "mcp-tools-fetch",
    "redirect_uris": [CALLBACK_URL],
    "grant_types": ["authorization_code", "refresh_token"],
    "response_types": ["code"],
    "token_endpoint_auth_method": "client_secret_post",
}
```

Rationale:

- The MCP ecosystem specification recommends DCR for tool clients that need to authenticate against arbitrary MCP servers without pre-registration.
- DCR eliminates the manual step of creating an OAuth client in the provider's admin console, reducing setup friction.
- Once registered, the `client_id` and `client_secret` are cached in the database under the `"dcr"` secret type, avoiding redundant registrations on subsequent flows.

### 2.7 Why .well-known Auto-Discovery

`discover_oauth_metadata()` probes multiple candidate URLs derived from the server URL against two well-known paths:

```python
_WELL_KNOWN_PATHS = [
    "/.well-known/openid-configuration",
    "/.well-known/oauth-authorization-server",
]
```

The function walks up the URL path hierarchy (e.g., `https://host/a/b/mcp` -> `https://host/a/b` -> `https://host/a` -> `https://host`) trying each path at each level.

Rationale:

- Reduces manual configuration burden. Users often know the MCP server URL but not the OAuth endpoints. Auto-discovery fills in `authorization_endpoint`, `token_endpoint`, `registration_endpoint`, and `scopes_supported` automatically.
- The frontend's "Auto-Discover Endpoints" button calls this endpoint and populates the OAuth form fields, providing immediate feedback.

---

## 3. Auth Design

### 3.1 Token Storage Strategy

All authentication secrets are stored in the `mcp_secrets` table with a composite primary key of `(server_name, secret_type)`. The `secret_type` discriminator supports:

| `secret_type` | `secret_data` shape | Used by |
|---|---|---|
| `"bearer"` | `{"token": "..."}` | Bearer token auth, SSO migration |
| `"apikey"` | `{"key": "..."}` | API key auth |
| `"oauth"` | `{"access_token": "...", "refresh_token": "...", "token_type": "Bearer"}` | OAuth / DCR |
| `"dcr"` | `{"client_id": "...", "client_secret": "..."}` | DCR client credentials cache |

This design allows a single server to have both DCR client credentials and OAuth tokens simultaneously (DCR needs the client registration persisted separately from the access/refresh tokens).

Bearer tokens also have a fallback lookup path: the code checks for an environment variable `MCP_{SERVER_NAME}_TOKEN` before querying the database, allowing deployments to inject tokens without touching the DB.

### 3.2 Token Refresh Flow

The `_try_request_with_refresh()` function in `mcp_client.py` implements a three-step retry strategy:

1. **Try with current token.** Call `get_token()` and execute the MCP request.
2. **On 401/403, attempt refresh.** If `auth_mode` is `"oauth"` or `"dcr"`, call `refresh_access_token()` which posts the refresh token to the token endpoint. If the auth mode is `"bearer_token"` or `"api_key"`, immediately raise `ReAuthRequired` (these tokens cannot be refreshed programmatically).
3. **Retry with new token.** If refresh succeeds, retry the original request with the new access token. If the retry also returns 401/403, clear the stored OAuth tokens and raise `ReAuthRequired`.

When `ReAuthRequired` is raised, the route handlers return `{"reauth": true}` in the response, which the frontend interprets to show auth-mode-specific guidance or open the browser for re-authentication.

### 3.3 DCR Client Caching

DCR registration happens once per server. The registered `client_id` and `client_secret` are stored under `secret_type = "dcr"`. On subsequent OAuth flows, `start_oauth_flow()` checks for existing DCR data before calling `_register_dcr_client()`:

```python
dcr_data = await get_secret(server_name, "dcr")
if dcr_data:
    client_id = dcr_data["client_id"]
    client_secret = dcr_data.get("client_secret")
else:
    client_id, client_secret = await _register_dcr_client(server_config)
    await set_secret(server_name, "dcr", {...})
```

This avoids creating duplicate client registrations on the OAuth provider, which some providers may reject or rate-limit.

### 3.4 OAuth Callback Redirect

The OAuth callback endpoint (`GET /api/auth/callback`) performs the authorization code exchange and then returns an HTML page with a JavaScript redirect:

```javascript
window.location.href = "http://localhost:5173?auth_success={server_name}";
```

The frontend's `App.tsx` checks for the `auth_success` query parameter on load:

```typescript
const authServer = params.get('auth_success')
if (authServer) {
    window.history.replaceState({}, '', window.location.pathname)
    // auto-test connection and fetch tools
}
```

This creates a seamless flow: browser opens for auth -> user approves -> callback exchanges tokens -> redirect back to the app -> app auto-connects to the server.

### 3.5 Auth-Mode-Aware Error Messages

The frontend provides specific error messages based on `auth_mode` when authentication fails. In `ServerList.tsx` and `ToolsViewer.tsx`, the `handleReauth()` function branches on `authMode`:

- `"oauth"` / `"dcr"`: Opens the browser for re-authentication automatically.
- `"bearer_token"` / `null`: Tells the user to edit the server and update the token.
- `"api_key"`: Tells the user to edit the server and update the key.

This avoids generic "authentication failed" messages that leave the user unsure what to do next.

---

## 4. MCP Protocol Integration

### 4.1 JSON-RPC 2.0 Message Format

All MCP communication uses JSON-RPC 2.0 over HTTP POST. The `_make_jsonrpc_request()` function constructs the payload:

```python
payload = {"jsonrpc": "2.0", "method": method}
if not is_notification:
    payload["id"] = 1
if params:
    payload["params"] = params
```

Notifications (like `notifications/initialized`) omit the `id` field per JSON-RPC 2.0 spec, and their responses are not parsed.

### 4.2 Session Management

The MCP protocol uses session IDs to correlate requests within a connection lifecycle. The `Mcp-Session-Id` header is:

- Captured from the response to `initialize` (`resp.headers.get("Mcp-Session-Id")`).
- Passed to subsequent requests (`notifications/initialized`, `tools/list`) via the `session_id` parameter.

This ensures the MCP server can maintain state across the three-step protocol sequence.

### 4.3 SSE Response Parsing

The `Accept` header includes `text/event-stream` alongside `application/json`. When the response content type is `text/event-stream`, the `_parse_sse_response()` function extracts the first `data:` line that contains a valid JSON-RPC response (one with a `result` or `error` key):

```python
for line in text.strip().split("\n"):
    if line.startswith("data: "):
        data = line[6:]
        parsed = json.loads(data)
        if "result" in parsed or "error" in parsed:
            return parsed
```

This handles MCP servers that use SSE transport for responses, including those that may send intermediate events before the final result.

### 4.4 Initialize -> Notification -> tools/list Sequence

The `mcp_list_tools()` function implements the full MCP protocol handshake:

1. **`initialize`** -- Sends client info and protocol version (`2024-11-05`), receives server capabilities.
2. **`notifications/initialized`** -- Sent as a notification (no `id`, response ignored) to signal the client is ready.
3. **`tools/list`** -- Requests the list of available tools from the server.

All three requests use the same session ID and authentication token, and the entire sequence is wrapped in `_try_request_with_refresh()` to handle token expiry mid-sequence.

---

## 5. Frontend Design

### 5.1 Component Responsibilities and Data Flow

| Component | Responsibility |
|---|---|
| `App.tsx` | Top-level layout, view routing (server list vs. tools viewer), form modal state, toast state, OAuth redirect handling |
| `ServerList.tsx` | Fetches and displays all servers, shows auth status indicators, handles connect/delete/edit actions, delegates re-auth flow |
| `ServerForm.tsx` | Modal form for creating/editing server configs, handles OAuth auto-discovery, collects secret values (bearer token / API key) |
| `ToolsViewer.tsx` | Displays tools for a single server, supports search/filter, expand/collapse, JSON download, re-fetch with auth error handling |
| `Toast` | Transient notification display |

Data flows down through props. `App.tsx` owns the state for which view to show (`viewingTools`, `showForm`, `editingServer`) and passes callbacks to children.

### 5.2 State Management Approach

The application uses React local state exclusively -- no Redux, Zustand, or Context providers. Each component manages its own data:

- `ServerList` owns the `servers` map and `authStatuses` map, fetched on mount and when `refreshKey` changes.
- `ServerForm` owns the form field state, initialized from props when editing.
- `ToolsViewer` owns the `tools` array and `expanded` set.

Cross-component coordination is handled through:

- `refreshKey` (number): Incremented by `App.tsx` to trigger `ServerList` to re-fetch.
- `onServersLoaded` callback: `ServerList` pushes its loaded data to `App.tsx`'s `serversCache` so `ToolsViewer` can access `authMode` without a separate API call.
- Prop callbacks: `onEdit`, `onAdd`, `onViewTools`, `onToast`.

This approach is appropriate given the low component count and the absence of deeply nested state consumers.

### 5.3 Toast Notification Pattern

Toast state is a single `{message, type}` object or `null`, managed in `App.tsx`. Components receive an `onToast` callback and call it with a message and severity level (`"success"`, `"error"`, `"info"`). Only one toast is shown at a time; setting a new toast replaces any existing one. The `Toast` component handles its own dismiss behavior via `onClose`.

### 5.4 Server List Refresh Mechanism

Rather than polling or WebSocket-based updates, the app uses a `refreshKey` counter pattern. When an operation modifies server state (create, update, delete, OAuth callback redirect), `App.tsx` increments `refreshKey`:

```typescript
setRefreshKey(k => k + 1)
```

`ServerList` has a `useEffect` dependency on `refreshKey`, causing it to re-fetch the server list and auth statuses whenever the key changes. This is a simple, predictable mechanism that avoids stale data after mutations.

---

## 6. Database Migration Strategy

### 6.1 Auto-Migration from Legacy Files

The application previously stored configuration in flat JSON files. On startup, `init_db()` runs two migration functions:

**`_migrate_tokens_json()`** reads `tokens.json` (if present) and migrates entries to the `mcp_secrets` table. It parses key suffixes to determine the secret type:

- `*_bearer` -> `secret_type = "bearer"`
- `*_apikey` -> `secret_type = "apikey"`
- `*_dcr` -> `secret_type = "dcr"`
- `*_sso` -> `secret_type = "bearer"` (with token extraction)
- no suffix -> `secret_type = "oauth"`

**`_migrate_mcp_json()`** reads `mcp.json` and migrates `mcpServers` entries to the `mcp_servers` table.

Both migrations are idempotent: they check whether the target table already has data (`select(...).limit(1)`) and skip if rows exist. The original files are not deleted, allowing rollback.

### 6.2 Schema Creation on Startup

`init_db()` calls `Base.metadata.create_all` via the async engine on every startup. SQLAlchemy's `create_all` is inherently idempotent (it creates tables only if they do not already exist), so no separate migration tool (Alembic) is needed for the current simple schema.

---

## 7. Testing Strategy

### 7.1 File-Based Temp SQLite for Test Isolation

The `conftest.py` fixture creates a temporary SQLite database per test using `tmp_path`:

```python
db_path = tmp_path / "test.db"
monkeypatch.setattr(db_module, "get_database_url", lambda: f"sqlite+aiosqlite:///{db_path}")
```

Each test gets its own database file, ensuring complete isolation without cleanup logic. The fixture also resets the module-level `_engine` and `_session_factory` globals before calling `init_db()`.

### 7.2 Monkeypatch Strategy

Tests patch at the module-level import site, not at the definition site:

- `db_module.get_database_url` is patched on the `database` module, ensuring `init_db()` sees the test URL even though `get_database_url` is defined in `config.py`.
- Migration functions (`_migrate_tokens_json`, `_migrate_mcp_json`) are replaced with async no-ops to prevent tests from reading stale `tokens.json` or `mcp.json` files that may exist in the working directory.

### 7.3 Migration No-Op in Tests

The `conftest.py` fixture replaces both migration functions with `_noop` (an async function that does nothing):

```python
monkeypatch.setattr(db_module, "_migrate_tokens_json", _noop)
monkeypatch.setattr(db_module, "_migrate_mcp_json", _noop)
```

This ensures tests start with a clean database and are not affected by legacy files in the developer's working directory.

### 7.4 Test Coverage Areas

The test suite covers:

- **`test_database.py`**: CRUD operations for secrets and server configs, including upsert behavior, missing-key handling, and multi-type discrimination.
- **`test_auth.py`**: Authentication logic and token management.
- **`test_mcp_client.py`**: SSE response parsing, including valid responses, error responses, and malformed streams.
- **`test_tools_store.py`**: YAML file read/write operations.
- **`test_config.py`**: Config loading from database.
- **`test_routes_servers.py`**: Server CRUD API endpoints.
- **`test_routes_tools.py`**: Tool fetch and retrieval endpoints.

---

## 8. Future Enhancement Areas

Based on patterns in the current code, the following areas are identified for potential improvement:

- **Token expiry tracking.** The `oauth` secret stores `access_token` and `refresh_token` but not `expires_at`. Adding expiry timestamps would allow proactive refresh before a request fails with 401, reducing latency on the first request after token expiry.

- **WebSocket/SSE for real-time auth status updates.** Auth status is currently polled by the frontend on each `refreshKey` change. A server-sent event stream could push status updates (e.g., after OAuth callback completes) to connected clients immediately.

- **Server health monitoring.** The `test_connection` endpoint (`POST /{name}/test`) is user-initiated. Background health checks with status caching would allow the UI to show server availability without manual testing.

- **Tool execution.** The application currently fetches and displays tool definitions but does not execute tools (`tools/call`). Adding execution support would require input validation against `inputSchema`, result display, and potentially streaming for long-running tools.

- **Multi-user support.** Token storage is currently global (no user context on `mcp_secrets`). Supporting multiple users would require user identity, per-user token isolation, and session management.

- **Batch connect all servers.** The UI connects to servers one at a time. A "Connect All" action would allow fetching tools from all configured servers in parallel.

- **Import/export server configs.** The `mcp_servers` table stores configs as JSON blobs, but there is no API to export all configs to a file or import from one. This would support backup, migration between environments, and sharing configurations across teams.

- **API key in query parameter security warning.** The frontend shows a warning when API key location is set to `"query"`, but the backend does not enforce or log this. Adding a server-side advisory log could help operators audit their configurations.
