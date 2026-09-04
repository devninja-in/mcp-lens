# MCP Tools Fetch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python + React application to manage MCP server configurations, authenticate via SSO/DCR/OAuth, fetch tools via JSON-RPC, and store results in per-server YAML files.

**Architecture:** Single FastAPI backend serving REST API endpoints and the built React frontend. Backend handles config CRUD, three auth flows, and MCP JSON-RPC communication. React + Tailwind frontend provides a management UI for servers and tools.

**Tech Stack:** Python 3.14 / FastAPI / httpx / PyYAML / python-dotenv / uv — React 18 / TypeScript / Tailwind CSS / Vite

## Global Constraints

- Python ≥ 3.11, managed with `uv`
- All secrets read from `.env` — never hard-coded
- `tokens.json` and `.env` are gitignored — never committed
- MCP transport is `streamable_http` only (all servers in the spec use it)
- JSON-RPC 2.0 over HTTP for MCP protocol
- Frontend builds to `static/` for production serving by FastAPI

---

## File Map

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Python project config, dependencies |
| `.gitignore` | Ignore .env, tokens.json, node_modules, static/, __pycache__ |
| `mcp.json` | MCP server configurations (user-editable, committed) |
| `.env` | Secrets: JWT tokens, client secrets |
| `tokens.json` | Auto-generated OAuth/DCR tokens + DCR client credentials |
| `src/app/__init__.py` | Package marker |
| `src/app/main.py` | FastAPI app, mount static, CORS, include routers |
| `src/app/models.py` | Pydantic models for server config, OAuth config, API responses |
| `src/app/config.py` | Load/save mcp.json, read .env variables |
| `src/app/auth.py` | Auth engine: SSO token lookup, OAuth flow, DCR registration + flow |
| `src/app/mcp_client.py` | JSON-RPC client: initialize handshake, tools/list call |
| `src/app/tools_store.py` | Read/write per-server YAML to tools/ directory |
| `src/app/routes/__init__.py` | Package marker |
| `src/app/routes/servers.py` | CRUD endpoints for server configurations |
| `src/app/routes/auth_routes.py` | OAuth callback, auth status check |
| `src/app/routes/tools.py` | Fetch tools, read saved tools |
| `tests/test_config.py` | Tests for config loading/saving |
| `tests/test_auth.py` | Tests for auth engine (SSO token lookup, OAuth state) |
| `tests/test_mcp_client.py` | Tests for JSON-RPC client |
| `tests/test_tools_store.py` | Tests for YAML read/write |
| `tests/test_routes_servers.py` | Integration tests for server CRUD API |
| `tests/test_routes_tools.py` | Integration tests for tools API |
| `src/frontend/package.json` | Frontend dependencies |
| `src/frontend/vite.config.ts` | Vite config with API proxy |
| `src/frontend/tailwind.config.js` | Tailwind config |
| `src/frontend/postcss.config.js` | PostCSS for Tailwind |
| `src/frontend/tsconfig.json` | TypeScript config |
| `src/frontend/index.html` | HTML entry point |
| `src/frontend/src/main.tsx` | React entry point |
| `src/frontend/src/App.tsx` | Root component with view routing |
| `src/frontend/src/types.ts` | TypeScript types matching backend models |
| `src/frontend/src/api.ts` | Fetch wrapper functions for all API endpoints |
| `src/frontend/src/components/ServerList.tsx` | Server table with actions |
| `src/frontend/src/components/ServerForm.tsx` | Add/edit server modal |
| `src/frontend/src/components/ToolsViewer.tsx` | Tool cards with collapsible schema |
| `src/frontend/src/components/Toast.tsx` | Simple toast notification component |

---

### Task 1: Project Scaffolding & Configuration Layer

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env`, `mcp.json`, `src/app/__init__.py`, `src/app/models.py`, `src/app/config.py`
- Create: `tests/__init__.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `McpServerConfig(BaseModel)` — fields: `enabled: bool`, `url: str`, `transport: str = "streamable_http"`, `ssl_verify: bool = True`, `auth: bool = False`, `description: str = ""`, `auth_mode: str | None = None`, `oauth: OAuthConfig | None = None`, `timeout: int = 30`
  - `OAuthConfig(BaseModel)` — fields: `grant_type: str = "authorization_code"`, `registration_endpoint: str | None = None`, `authorization_endpoint: str | None = None`, `token_endpoint: str | None = None`, `client_id: str | None = None`, `client_secret_env: str | None = None`, `scopes: list[str] = []`
  - `McpConfig(BaseModel)` — fields: `mcpServers: dict[str, McpServerConfig]`
  - `load_config() -> McpConfig` — reads mcp.json
  - `save_config(config: McpConfig) -> None` — writes mcp.json
  - `get_env_var(name: str) -> str | None` — reads .env variable

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "mcp-tools-fetch"
version = "0.1.0"
description = "MCP server tools fetcher with web UI"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "httpx",
]
```

- [ ] **Step 2: Create .gitignore**

```
.env
tokens.json
__pycache__/
*.pyc
node_modules/
static/
dist/
.venv/
tools/
```

- [ ] **Step 3: Create seed mcp.json with one example server**

```json
{
  "mcpServers": {}
}
```

- [ ] **Step 4: Create .env with placeholder comments**

```
# SSO tokens: MCP_{SERVER_NAME_UPPER}_TOKEN=jwt_value
# OAuth secrets: referenced by client_secret_env field in mcp.json
```

- [ ] **Step 5: Create src/app/__init__.py**

Empty file.

- [ ] **Step 6: Create src/app/models.py**

```python
from pydantic import BaseModel


class OAuthConfig(BaseModel):
    grant_type: str = "authorization_code"
    registration_endpoint: str | None = None
    authorization_endpoint: str | None = None
    token_endpoint: str | None = None
    client_id: str | None = None
    client_secret_env: str | None = None
    scopes: list[str] = []


class McpServerConfig(BaseModel):
    enabled: bool = True
    url: str
    transport: str = "streamable_http"
    ssl_verify: bool = True
    auth: bool = False
    description: str = ""
    auth_mode: str | None = None
    oauth: OAuthConfig | None = None
    timeout: int = 30


class McpConfig(BaseModel):
    mcpServers: dict[str, McpServerConfig] = {}


class ServerCreateRequest(BaseModel):
    name: str
    config: McpServerConfig


class ToolInfo(BaseModel):
    name: str
    description: str | None = None
    inputSchema: dict | None = None


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: dict | None = None
```

- [ ] **Step 7: Create src/app/config.py**

```python
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .models import McpConfig

load_dotenv()

CONFIG_PATH = Path("mcp.json")


def load_config() -> McpConfig:
    if not CONFIG_PATH.exists():
        return McpConfig()
    with open(CONFIG_PATH) as f:
        return McpConfig.model_validate(json.load(f))


def save_config(config: McpConfig) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(config.model_dump(exclude_none=True), f, indent=2)


def get_env_var(name: str) -> str | None:
    return os.environ.get(name)
```

- [ ] **Step 8: Create tests/__init__.py and tests/test_config.py**

```python
import json
from pathlib import Path

from src.app.config import load_config, save_config
from src.app.models import McpConfig, McpServerConfig


def test_load_empty_config(tmp_path, monkeypatch):
    monkeypatch.setattr("src.app.config.CONFIG_PATH", tmp_path / "mcp.json")
    config = load_config()
    assert config.mcpServers == {}


def test_load_config_with_server(tmp_path, monkeypatch):
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps({
        "mcpServers": {
            "test-server": {
                "url": "https://example.com/mcp",
                "enabled": True,
                "auth": False,
            }
        }
    }))
    monkeypatch.setattr("src.app.config.CONFIG_PATH", config_path)
    config = load_config()
    assert "test-server" in config.mcpServers
    assert config.mcpServers["test-server"].url == "https://example.com/mcp"


def test_save_config(tmp_path, monkeypatch):
    config_path = tmp_path / "mcp.json"
    monkeypatch.setattr("src.app.config.CONFIG_PATH", config_path)
    config = McpConfig(mcpServers={
        "my-server": McpServerConfig(url="https://example.com/mcp")
    })
    save_config(config)
    loaded = json.loads(config_path.read_text())
    assert loaded["mcpServers"]["my-server"]["url"] == "https://example.com/mcp"


def test_get_env_var(monkeypatch):
    monkeypatch.setenv("MCP_TEST_TOKEN", "abc123")
    from src.app.config import get_env_var
    assert get_env_var("MCP_TEST_TOKEN") == "abc123"
    assert get_env_var("NONEXISTENT") is None
```

- [ ] **Step 9: Initialize uv project and run tests**

```bash
cd /Users/abhiskum/work/code/data_and_ai/dataverse/mcp/mcp-tools-fetch
uv sync --all-extras
uv run pytest tests/test_config.py -v
```

Expected: All 4 tests pass.

- [ ] **Step 10: Commit**

```bash
git init
git add pyproject.toml .gitignore mcp.json .env src/ tests/
git commit -m "feat: project scaffolding with config layer and models"
```

---

### Task 2: Auth Engine

**Files:**
- Create: `src/app/auth.py`, `tests/test_auth.py`

**Interfaces:**
- Consumes: `get_env_var(name)` from `config.py`, `McpServerConfig` / `OAuthConfig` from `models.py`
- Produces:
  - `get_token(server_name: str, server_config: McpServerConfig) -> str` — returns a valid Bearer token for any auth mode
  - `start_oauth_flow(server_name: str, server_config: McpServerConfig) -> str` — returns the authorization URL to open in browser
  - `handle_oauth_callback(state: str, code: str) -> str` — exchanges code for token, stores in tokens.json, returns server_name
  - `get_auth_status(server_name: str) -> dict` — returns `{"authenticated": bool, "auth_mode": str | None}`
  - `_load_tokens() -> dict` — reads tokens.json
  - `_save_tokens(data: dict) -> None` — writes tokens.json

- [ ] **Step 1: Create src/app/auth.py — token storage helpers**

```python
import hashlib
import json
import secrets
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

import httpx

from .config import get_env_var
from .models import McpServerConfig

TOKENS_PATH = Path("tokens.json")
CALLBACK_PORT = 9876
CALLBACK_URL = f"http://localhost:8000/api/auth/callback"

_pending_flows: dict[str, dict] = {}


def _load_tokens() -> dict:
    if not TOKENS_PATH.exists():
        return {}
    with open(TOKENS_PATH) as f:
        return json.load(f)


def _save_tokens(data: dict) -> None:
    with open(TOKENS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _server_name_to_env_key(server_name: str) -> str:
    return f"MCP_{server_name.upper().replace('-', '_')}_TOKEN"
```

- [ ] **Step 2: Implement SSO token lookup**

Add to `src/app/auth.py`:

```python
def _get_sso_token(server_name: str) -> str | None:
    env_key = _server_name_to_env_key(server_name)
    return get_env_var(env_key)
```

- [ ] **Step 3: Implement OAuth authorization flow start**

Add to `src/app/auth.py`:

```python
async def _register_dcr_client(server_config: McpServerConfig) -> tuple[str, str]:
    oauth = server_config.oauth
    async with httpx.AsyncClient(verify=server_config.ssl_verify) as client:
        resp = await client.post(
            oauth.registration_endpoint,
            json={
                "client_name": "mcp-tools-fetch",
                "redirect_uris": [CALLBACK_URL],
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["client_id"], data["client_secret"]


async def start_oauth_flow(server_name: str, server_config: McpServerConfig) -> str:
    oauth = server_config.oauth
    client_id = oauth.client_id
    client_secret = None

    if server_config.auth_mode == "dcr":
        tokens = _load_tokens()
        dcr_key = f"{server_name}_dcr"
        if dcr_key in tokens:
            client_id = tokens[dcr_key]["client_id"]
            client_secret = tokens[dcr_key]["client_secret"]
        else:
            client_id, client_secret = await _register_dcr_client(server_config)
            tokens[dcr_key] = {"client_id": client_id, "client_secret": client_secret}
            _save_tokens(tokens)
    else:
        secret_env = oauth.client_secret_env
        if secret_env:
            client_secret = get_env_var(secret_env)

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = hashlib.sha256(code_verifier.encode()).hexdigest()

    _pending_flows[state] = {
        "server_name": server_name,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
        "token_endpoint": oauth.token_endpoint,
        "ssl_verify": server_config.ssl_verify,
    }

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": CALLBACK_URL,
        "state": state,
    }
    if oauth.scopes:
        params["scope"] = " ".join(oauth.scopes)

    auth_url = f"{oauth.authorization_endpoint}?{urlencode(params)}"
    return auth_url
```

- [ ] **Step 4: Implement OAuth callback handler**

Add to `src/app/auth.py`:

```python
async def handle_oauth_callback(state: str, code: str) -> str:
    flow = _pending_flows.pop(state, None)
    if not flow:
        raise ValueError("Unknown OAuth state — flow expired or invalid")

    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": CALLBACK_URL,
        "client_id": flow["client_id"],
    }
    if flow["client_secret"]:
        token_data["client_secret"] = flow["client_secret"]

    async with httpx.AsyncClient(verify=flow["ssl_verify"]) as client:
        resp = await client.post(flow["token_endpoint"], data=token_data)
        resp.raise_for_status()
        token_resp = resp.json()

    tokens = _load_tokens()
    tokens[flow["server_name"]] = {
        "access_token": token_resp["access_token"],
        "refresh_token": token_resp.get("refresh_token"),
        "token_type": token_resp.get("token_type", "Bearer"),
    }
    _save_tokens(tokens)
    return flow["server_name"]
```

- [ ] **Step 5: Implement get_token and get_auth_status**

Add to `src/app/auth.py`:

```python
async def get_token(server_name: str, server_config: McpServerConfig) -> str | None:
    if not server_config.auth:
        return None

    if server_config.auth_mode == "sso" or server_config.auth_mode is None:
        token = _get_sso_token(server_name)
        if token:
            return token
        raise ValueError(
            f"SSO token not found. Set {_server_name_to_env_key(server_name)} in .env"
        )

    tokens = _load_tokens()
    if server_name in tokens and "access_token" in tokens[server_name]:
        return tokens[server_name]["access_token"]

    return None


def get_auth_status(server_name: str, server_config: McpServerConfig) -> dict:
    if not server_config.auth:
        return {"authenticated": True, "auth_mode": None}

    if server_config.auth_mode == "sso" or server_config.auth_mode is None:
        token = _get_sso_token(server_name)
        return {"authenticated": token is not None, "auth_mode": "sso"}

    tokens = _load_tokens()
    has_token = server_name in tokens and "access_token" in tokens[server_name]
    return {"authenticated": has_token, "auth_mode": server_config.auth_mode}
```

- [ ] **Step 6: Write tests/test_auth.py**

```python
import json

import pytest

from src.app.auth import (
    _load_tokens,
    _save_tokens,
    _server_name_to_env_key,
    get_auth_status,
    get_token,
)
from src.app.models import McpServerConfig


def test_server_name_to_env_key():
    assert _server_name_to_env_key("dataverse-mcp") == "MCP_DATAVERSE_MCP_TOKEN"
    assert _server_name_to_env_key("my-server") == "MCP_MY_SERVER_TOKEN"


def test_load_save_tokens(tmp_path, monkeypatch):
    tokens_path = tmp_path / "tokens.json"
    monkeypatch.setattr("src.app.auth.TOKENS_PATH", tokens_path)

    assert _load_tokens() == {}

    _save_tokens({"server1": {"access_token": "abc"}})
    loaded = _load_tokens()
    assert loaded["server1"]["access_token"] == "abc"


def test_get_auth_status_no_auth():
    config = McpServerConfig(url="https://example.com", auth=False)
    status = get_auth_status("test", config)
    assert status["authenticated"] is True


def test_get_auth_status_sso_missing(monkeypatch):
    monkeypatch.delenv("MCP_TEST_SERVER_TOKEN", raising=False)
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="sso")
    status = get_auth_status("test-server", config)
    assert status["authenticated"] is False


def test_get_auth_status_sso_present(monkeypatch):
    monkeypatch.setenv("MCP_TEST_SERVER_TOKEN", "jwt123")
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="sso")
    status = get_auth_status("test-server", config)
    assert status["authenticated"] is True


@pytest.mark.asyncio
async def test_get_token_sso(monkeypatch):
    monkeypatch.setenv("MCP_MY_MCP_TOKEN", "sso-token-value")
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="sso")
    token = await get_token("my-mcp", config)
    assert token == "sso-token-value"


@pytest.mark.asyncio
async def test_get_token_sso_missing(monkeypatch):
    monkeypatch.delenv("MCP_MISSING_TOKEN", raising=False)
    config = McpServerConfig(url="https://example.com", auth=True, auth_mode="sso")
    with pytest.raises(ValueError, match="SSO token not found"):
        await get_token("missing", config)


@pytest.mark.asyncio
async def test_get_token_no_auth():
    config = McpServerConfig(url="https://example.com", auth=False)
    token = await get_token("test", config)
    assert token is None
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest tests/test_auth.py -v
```

Expected: All 8 tests pass.

- [ ] **Step 8: Commit**

```bash
git add src/app/auth.py tests/test_auth.py
git commit -m "feat: auth engine with SSO, OAuth, and DCR support"
```

---

### Task 3: MCP Client (JSON-RPC)

**Files:**
- Create: `src/app/mcp_client.py`, `tests/test_mcp_client.py`

**Interfaces:**
- Consumes: `get_token(server_name, server_config)` from `auth.py`, `McpServerConfig` from `models.py`
- Produces:
  - `mcp_initialize(server_name: str, server_config: McpServerConfig) -> dict` — sends JSON-RPC `initialize`, returns result
  - `mcp_list_tools(server_name: str, server_config: McpServerConfig) -> list[dict]` — sends `initialize` then `tools/list`, returns list of tool dicts

- [ ] **Step 1: Create src/app/mcp_client.py**

```python
import httpx

from .auth import get_token
from .models import McpServerConfig

MCP_PROTOCOL_VERSION = "2024-11-05"


async def _make_jsonrpc_request(
    url: str,
    method: str,
    params: dict | None = None,
    token: str | None = None,
    ssl_verify: bool = True,
    timeout: int = 30,
    session_id: str | None = None,
) -> tuple[dict, str | None]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
    }
    if params:
        payload["params"] = params

    async with httpx.AsyncClient(verify=ssl_verify, timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()

        new_session_id = resp.headers.get("Mcp-Session-Id", session_id)

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return _parse_sse_response(resp.text), new_session_id
        return resp.json(), new_session_id


def _parse_sse_response(text: str) -> dict:
    import json

    for line in text.strip().split("\n"):
        if line.startswith("data: "):
            data = line[6:]
            try:
                parsed = json.loads(data)
                if "result" in parsed or "error" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
    raise ValueError("No valid JSON-RPC response found in SSE stream")


async def mcp_initialize(
    server_name: str, server_config: McpServerConfig
) -> tuple[dict, str | None]:
    token = await get_token(server_name, server_config)
    result, session_id = await _make_jsonrpc_request(
        url=server_config.url,
        method="initialize",
        params={
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mcp-tools-fetch", "version": "0.1.0"},
        },
        token=token,
        ssl_verify=server_config.ssl_verify,
        timeout=server_config.timeout,
    )
    return result, session_id


async def mcp_list_tools(
    server_name: str, server_config: McpServerConfig
) -> list[dict]:
    init_result, session_id = await mcp_initialize(server_name, server_config)

    if "error" in init_result:
        raise RuntimeError(f"Initialize failed: {init_result['error']}")

    token = await get_token(server_name, server_config)

    await _make_jsonrpc_request(
        url=server_config.url,
        method="notifications/initialized",
        token=token,
        ssl_verify=server_config.ssl_verify,
        timeout=server_config.timeout,
        session_id=session_id,
    )

    result, _ = await _make_jsonrpc_request(
        url=server_config.url,
        method="tools/list",
        params={},
        token=token,
        ssl_verify=server_config.ssl_verify,
        timeout=server_config.timeout,
        session_id=session_id,
    )

    if "error" in result:
        raise RuntimeError(f"tools/list failed: {result['error']}")

    return result.get("result", {}).get("tools", [])
```

- [ ] **Step 2: Create tests/test_mcp_client.py**

```python
import json

import pytest

from src.app.mcp_client import _parse_sse_response


def test_parse_sse_response_valid():
    sse_text = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n'
    result = _parse_sse_response(sse_text)
    assert result["result"]["tools"] == []


def test_parse_sse_response_no_result():
    sse_text = "event: ping\ndata: {}\n\n"
    with pytest.raises(ValueError, match="No valid JSON-RPC response"):
        _parse_sse_response(sse_text)


def test_parse_sse_response_with_error():
    sse_text = 'data: {"jsonrpc":"2.0","id":1,"error":{"code":-32600,"message":"Invalid"}}\n\n'
    result = _parse_sse_response(sse_text)
    assert "error" in result
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_mcp_client.py -v
```

Expected: All 3 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/app/mcp_client.py tests/test_mcp_client.py
git commit -m "feat: MCP JSON-RPC client with initialize and tools/list"
```

---

### Task 4: Tools Store (YAML)

**Files:**
- Create: `src/app/tools_store.py`, `tests/test_tools_store.py`

**Interfaces:**
- Consumes: `ToolInfo` from `models.py`
- Produces:
  - `save_tools(server_name: str, tools: list[dict]) -> Path` — writes to `tools/{server_name}.yaml`, returns path
  - `load_tools(server_name: str) -> list[dict] | None` — reads from YAML, returns None if file doesn't exist

- [ ] **Step 1: Create src/app/tools_store.py**

```python
from pathlib import Path

import yaml

TOOLS_DIR = Path("tools")


def save_tools(server_name: str, tools: list[dict]) -> Path:
    TOOLS_DIR.mkdir(exist_ok=True)
    path = TOOLS_DIR / f"{server_name}.yaml"
    with open(path, "w") as f:
        yaml.dump(
            {"server": server_name, "tools_count": len(tools), "tools": tools},
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    return path


def load_tools(server_name: str) -> list[dict] | None:
    path = TOOLS_DIR / f"{server_name}.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("tools", [])
```

- [ ] **Step 2: Create tests/test_tools_store.py**

```python
from src.app.tools_store import load_tools, save_tools


def test_save_and_load_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("src.app.tools_store.TOOLS_DIR", tmp_path)
    tools = [
        {"name": "search", "description": "Search things", "inputSchema": {"type": "object"}},
        {"name": "create", "description": "Create things"},
    ]
    path = save_tools("test-server", tools)
    assert path.exists()

    loaded = load_tools("test-server")
    assert len(loaded) == 2
    assert loaded[0]["name"] == "search"
    assert loaded[1]["name"] == "create"


def test_load_tools_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("src.app.tools_store.TOOLS_DIR", tmp_path)
    result = load_tools("nonexistent")
    assert result is None
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_tools_store.py -v
```

Expected: All 2 tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/app/tools_store.py tests/test_tools_store.py
git commit -m "feat: YAML tools store for per-server tool persistence"
```

---

### Task 5: API Routes & FastAPI App

**Files:**
- Create: `src/app/routes/__init__.py`, `src/app/routes/servers.py`, `src/app/routes/auth_routes.py`, `src/app/routes/tools.py`, `src/app/main.py`
- Create: `tests/test_routes_servers.py`, `tests/test_routes_tools.py`

**Interfaces:**
- Consumes: All previous modules — `config.py`, `auth.py`, `mcp_client.py`, `tools_store.py`, `models.py`
- Produces: Full FastAPI application at `src.app.main:app`

- [ ] **Step 1: Create src/app/routes/__init__.py**

Empty file.

- [ ] **Step 2: Create src/app/routes/servers.py**

```python
from fastapi import APIRouter, HTTPException

from ..config import load_config, save_config
from ..models import ApiResponse, McpServerConfig

router = APIRouter(prefix="/api/servers", tags=["servers"])


@router.get("")
async def list_servers() -> dict:
    config = load_config()
    return {"servers": {
        name: server.model_dump(exclude_none=True)
        for name, server in config.mcpServers.items()
    }}


@router.get("/{name}")
async def get_server(name: str) -> dict:
    config = load_config()
    if name not in config.mcpServers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    return {"name": name, "config": config.mcpServers[name].model_dump(exclude_none=True)}


@router.post("")
async def create_server(name: str, server: McpServerConfig) -> ApiResponse:
    config = load_config()
    if name in config.mcpServers:
        raise HTTPException(status_code=409, detail=f"Server '{name}' already exists")
    config.mcpServers[name] = server
    save_config(config)
    return ApiResponse(success=True, message=f"Server '{name}' created")


@router.put("/{name}")
async def update_server(name: str, server: McpServerConfig) -> ApiResponse:
    config = load_config()
    if name not in config.mcpServers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    config.mcpServers[name] = server
    save_config(config)
    return ApiResponse(success=True, message=f"Server '{name}' updated")


@router.delete("/{name}")
async def delete_server(name: str) -> ApiResponse:
    config = load_config()
    if name not in config.mcpServers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    del config.mcpServers[name]
    save_config(config)
    return ApiResponse(success=True, message=f"Server '{name}' deleted")
```

- [ ] **Step 3: Create src/app/routes/auth_routes.py**

```python
import webbrowser

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from ..auth import get_auth_status, handle_oauth_callback, start_oauth_flow
from ..config import load_config

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status/{name}")
async def auth_status(name: str) -> dict:
    config = load_config()
    if name not in config.mcpServers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    return get_auth_status(name, config.mcpServers[name])


@router.post("/start/{name}")
async def start_auth(name: str) -> dict:
    config = load_config()
    if name not in config.mcpServers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    server = config.mcpServers[name]
    if server.auth_mode not in ("oauth", "dcr"):
        raise HTTPException(status_code=400, detail="Server does not use OAuth/DCR auth")
    auth_url = await start_oauth_flow(name, server)
    webbrowser.open(auth_url)
    return {"auth_url": auth_url, "message": "Browser opened for authorization"}


@router.get("/callback")
async def oauth_callback(code: str, state: str) -> HTMLResponse:
    try:
        server_name = await handle_oauth_callback(state, code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return HTMLResponse(
        f"<html><body><h2>Authorization successful for {server_name}!</h2>"
        "<p>You can close this tab and return to the app.</p></body></html>"
    )
```

- [ ] **Step 4: Create src/app/routes/tools.py**

```python
from fastapi import APIRouter, HTTPException

from ..config import load_config
from ..mcp_client import mcp_initialize, mcp_list_tools
from ..tools_store import load_tools, save_tools

router = APIRouter(prefix="/api/servers", tags=["tools"])


@router.post("/{name}/test")
async def test_connection(name: str) -> dict:
    config = load_config()
    if name not in config.mcpServers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    try:
        result, _ = await mcp_initialize(name, config.mcpServers[name])
        if "error" in result:
            return {"success": False, "message": f"MCP error: {result['error']}"}
        server_info = result.get("result", {}).get("serverInfo", {})
        return {
            "success": True,
            "message": "Connection successful",
            "server_info": server_info,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/{name}/fetch-tools")
async def fetch_tools(name: str) -> dict:
    config = load_config()
    if name not in config.mcpServers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    try:
        tools = await mcp_list_tools(name, config.mcpServers[name])
        path = save_tools(name, tools)
        return {
            "success": True,
            "message": f"Fetched {len(tools)} tools, saved to {path}",
            "tools": tools,
            "count": len(tools),
        }
    except Exception as e:
        return {"success": False, "message": str(e), "tools": [], "count": 0}


@router.get("/{name}/tools")
async def get_tools(name: str) -> dict:
    tools = load_tools(name)
    if tools is None:
        raise HTTPException(
            status_code=404,
            detail=f"No tools found for '{name}'. Fetch tools first.",
        )
    return {"server": name, "tools": tools, "count": len(tools)}
```

- [ ] **Step 5: Create src/app/main.py**

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import auth_routes, servers, tools

app = FastAPI(title="MCP Tools Fetch", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(servers.router)
app.include_router(auth_routes.router)
app.include_router(tools.router)

static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
```

- [ ] **Step 6: Create tests/test_routes_servers.py**

```python
import json

import pytest
from fastapi.testclient import TestClient

from src.app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps({
        "mcpServers": {
            "test-server": {
                "url": "https://example.com/mcp",
                "enabled": True,
                "auth": False,
            }
        }
    }))
    monkeypatch.setattr("src.app.config.CONFIG_PATH", config_path)
    monkeypatch.setattr("src.app.routes.servers.load_config",
                        lambda: __import__("src.app.config", fromlist=["load_config"]).load_config())
    return TestClient(app)


def test_list_servers(client):
    resp = client.get("/api/servers")
    assert resp.status_code == 200
    assert "test-server" in resp.json()["servers"]


def test_get_server(client):
    resp = client.get("/api/servers/test-server")
    assert resp.status_code == 200
    assert resp.json()["name"] == "test-server"


def test_get_server_not_found(client):
    resp = client.get("/api/servers/nonexistent")
    assert resp.status_code == 404


def test_create_server(client):
    resp = client.post(
        "/api/servers?name=new-server",
        json={"url": "https://new.com/mcp", "enabled": True},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_create_duplicate(client):
    resp = client.post(
        "/api/servers?name=test-server",
        json={"url": "https://dup.com/mcp"},
    )
    assert resp.status_code == 409


def test_update_server(client):
    resp = client.put(
        "/api/servers/test-server",
        json={"url": "https://updated.com/mcp", "enabled": False},
    )
    assert resp.status_code == 200


def test_delete_server(client):
    resp = client.delete("/api/servers/test-server")
    assert resp.status_code == 200
```

- [ ] **Step 7: Create tests/test_routes_tools.py**

```python
import json

import pytest
from fastapi.testclient import TestClient

from src.app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    config_path = tmp_path / "mcp.json"
    config_path.write_text(json.dumps({
        "mcpServers": {
            "test-server": {
                "url": "https://example.com/mcp",
                "enabled": True,
                "auth": False,
            }
        }
    }))
    monkeypatch.setattr("src.app.config.CONFIG_PATH", config_path)
    monkeypatch.setattr("src.app.tools_store.TOOLS_DIR", tmp_path / "tools")
    return TestClient(app)


def test_get_tools_not_fetched(client):
    resp = client.get("/api/servers/test-server/tools")
    assert resp.status_code == 404


def test_get_tools_missing_server(client):
    resp = client.get("/api/servers/nonexistent/tools")
    assert resp.status_code == 404
```

- [ ] **Step 8: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add src/app/routes/ src/app/main.py tests/test_routes_servers.py tests/test_routes_tools.py
git commit -m "feat: FastAPI routes for server CRUD, auth, and tools"
```

---

### Task 6: React Frontend — Scaffolding & Server List

**Files:**
- Create: `src/frontend/package.json`, `src/frontend/vite.config.ts`, `src/frontend/tailwind.config.js`, `src/frontend/postcss.config.js`, `src/frontend/tsconfig.json`, `src/frontend/tsconfig.node.json`, `src/frontend/index.html`, `src/frontend/src/main.tsx`, `src/frontend/src/index.css`, `src/frontend/src/types.ts`, `src/frontend/src/api.ts`, `src/frontend/src/App.tsx`, `src/frontend/src/components/Toast.tsx`, `src/frontend/src/components/ServerList.tsx`

**Interfaces:**
- Consumes: Backend API at `/api/servers`, `/api/auth/status/{name}`, `/api/servers/{name}/test`
- Produces: Working server list page with status indicators and action buttons

- [ ] **Step 1: Create src/frontend/package.json**

```json
{
  "name": "mcp-tools-fetch-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: Create src/frontend/vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: '../../static',
    emptyOutDir: true,
  },
})
```

- [ ] **Step 3: Create Tailwind + PostCSS configs**

`src/frontend/tailwind.config.js`:
```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: { extend: {} },
  plugins: [],
}
```

`src/frontend/postcss.config.js`:
```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 4: Create TypeScript configs**

`src/frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"]
}
```

`src/frontend/tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 5: Create src/frontend/index.html**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>MCP Tools Fetch</title>
  </head>
  <body class="bg-gray-50 min-h-screen">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create src/frontend/src/main.tsx and src/frontend/src/index.css**

`src/frontend/src/main.tsx`:
```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

`src/frontend/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 7: Create src/frontend/src/types.ts**

```typescript
export interface OAuthConfig {
  grant_type?: string
  registration_endpoint?: string
  authorization_endpoint?: string
  token_endpoint?: string
  client_id?: string
  client_secret_env?: string
  scopes?: string[]
}

export interface McpServerConfig {
  enabled: boolean
  url: string
  transport: string
  ssl_verify: boolean
  auth: boolean
  description: string
  auth_mode?: string | null
  oauth?: OAuthConfig | null
  timeout: number
}

export interface ToolInfo {
  name: string
  description?: string
  inputSchema?: Record<string, unknown>
}

export interface AuthStatus {
  authenticated: boolean
  auth_mode: string | null
}

export interface ApiResponse {
  success: boolean
  message: string
  data?: Record<string, unknown>
}
```

- [ ] **Step 8: Create src/frontend/src/api.ts**

```typescript
import type { McpServerConfig, AuthStatus, ToolInfo } from './types'

const BASE = '/api'

async function fetchJson<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export async function listServers(): Promise<Record<string, McpServerConfig>> {
  const data = await fetchJson<{ servers: Record<string, McpServerConfig> }>('/servers')
  return data.servers
}

export async function getServer(name: string): Promise<{ name: string; config: McpServerConfig }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}`)
}

export async function createServer(name: string, config: McpServerConfig): Promise<void> {
  await fetchJson(`/servers?name=${encodeURIComponent(name)}`, {
    method: 'POST',
    body: JSON.stringify(config),
  })
}

export async function updateServer(name: string, config: McpServerConfig): Promise<void> {
  await fetchJson(`/servers/${encodeURIComponent(name)}`, {
    method: 'PUT',
    body: JSON.stringify(config),
  })
}

export async function deleteServer(name: string): Promise<void> {
  await fetchJson(`/servers/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export async function testConnection(name: string): Promise<{ success: boolean; message: string; server_info?: Record<string, unknown> }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/test`, { method: 'POST' })
}

export async function fetchTools(name: string): Promise<{ success: boolean; message: string; tools: ToolInfo[]; count: number }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/fetch-tools`, { method: 'POST' })
}

export async function getTools(name: string): Promise<{ server: string; tools: ToolInfo[]; count: number }> {
  return fetchJson(`/servers/${encodeURIComponent(name)}/tools`)
}

export async function getAuthStatus(name: string): Promise<AuthStatus> {
  return fetchJson(`/auth/status/${encodeURIComponent(name)}`)
}

export async function startAuth(name: string): Promise<{ auth_url: string; message: string }> {
  return fetchJson(`/auth/start/${encodeURIComponent(name)}`, { method: 'POST' })
}
```

- [ ] **Step 9: Create src/frontend/src/components/Toast.tsx**

```tsx
import { useEffect } from 'react'

interface ToastProps {
  message: string
  type: 'success' | 'error' | 'info'
  onClose: () => void
}

export default function Toast({ message, type, onClose }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(onClose, 4000)
    return () => clearTimeout(timer)
  }, [onClose])

  const colors = {
    success: 'bg-green-100 border-green-400 text-green-800',
    error: 'bg-red-100 border-red-400 text-red-800',
    info: 'bg-blue-100 border-blue-400 text-blue-800',
  }

  return (
    <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded border ${colors[type]} max-w-md shadow-lg`}>
      <div className="flex justify-between items-start gap-2">
        <p className="text-sm">{message}</p>
        <button onClick={onClose} className="text-lg leading-none font-bold opacity-50 hover:opacity-100">&times;</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 10: Create src/frontend/src/components/ServerList.tsx**

```tsx
import { useState, useEffect } from 'react'
import type { McpServerConfig, AuthStatus } from '../types'
import * as api from '../api'

interface Props {
  onEdit: (name: string, config: McpServerConfig) => void
  onAdd: () => void
  onViewTools: (name: string) => void
  onToast: (message: string, type: 'success' | 'error' | 'info') => void
  refreshKey: number
}

export default function ServerList({ onEdit, onAdd, onViewTools, onToast, refreshKey }: Props) {
  const [servers, setServers] = useState<Record<string, McpServerConfig>>({})
  const [authStatuses, setAuthStatuses] = useState<Record<string, AuthStatus>>({})
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState<Record<string, string>>({})

  useEffect(() => {
    loadServers()
  }, [refreshKey])

  async function loadServers() {
    try {
      const data = await api.listServers()
      setServers(data)
      const statuses: Record<string, AuthStatus> = {}
      for (const name of Object.keys(data)) {
        try {
          statuses[name] = await api.getAuthStatus(name)
        } catch {
          statuses[name] = { authenticated: false, auth_mode: null }
        }
      }
      setAuthStatuses(statuses)
    } catch (e) {
      onToast(`Failed to load servers: ${e}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  async function handleTest(name: string) {
    setActionLoading(prev => ({ ...prev, [name]: 'testing' }))
    try {
      const result = await api.testConnection(name)
      onToast(result.message, result.success ? 'success' : 'error')
    } catch (e) {
      onToast(`Test failed: ${e}`, 'error')
    } finally {
      setActionLoading(prev => { const n = { ...prev }; delete n[name]; return n })
    }
  }

  async function handleFetch(name: string) {
    const status = authStatuses[name]
    if (status && !status.authenticated && servers[name]?.auth) {
      if (servers[name].auth_mode === 'oauth' || servers[name].auth_mode === 'dcr') {
        try {
          await api.startAuth(name)
          onToast('Browser opened for authorization. Complete login and try again.', 'info')
          return
        } catch (e) {
          onToast(`Auth failed: ${e}`, 'error')
          return
        }
      }
      onToast('Server requires authentication. Check your .env token.', 'error')
      return
    }

    setActionLoading(prev => ({ ...prev, [name]: 'fetching' }))
    try {
      const result = await api.fetchTools(name)
      if (result.success) {
        onToast(result.message, 'success')
        onViewTools(name)
      } else {
        onToast(result.message, 'error')
      }
    } catch (e) {
      onToast(`Fetch failed: ${e}`, 'error')
    } finally {
      setActionLoading(prev => { const n = { ...prev }; delete n[name]; return n })
    }
  }

  async function handleDelete(name: string) {
    if (!confirm(`Delete server "${name}"?`)) return
    try {
      await api.deleteServer(name)
      onToast(`Server '${name}' deleted`, 'success')
      loadServers()
    } catch (e) {
      onToast(`Delete failed: ${e}`, 'error')
    }
  }

  if (loading) return <div className="text-center py-12 text-gray-500">Loading servers...</div>

  const entries = Object.entries(servers)

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-semibold text-gray-800">MCP Servers</h2>
        <button
          onClick={onAdd}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
        >
          + Add Server
        </button>
      </div>

      {entries.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          No servers configured. Add one to get started.
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Name</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">URL</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Auth</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Enabled</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">Actions</th>
              </tr>
            </thead>
            <tbody>
              {entries.map(([name, config]) => {
                const status = authStatuses[name]
                const isAuth = status?.authenticated ?? false
                const action = actionLoading[name]

                return (
                  <tr key={name} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <span className={`inline-block w-2.5 h-2.5 rounded-full ${
                        !config.auth ? 'bg-gray-400' : isAuth ? 'bg-green-500' : 'bg-red-400'
                      }`} title={isAuth ? 'Authenticated' : 'Not authenticated'} />
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900">{name}</td>
                    <td className="px-4 py-3 text-gray-500 truncate max-w-xs" title={config.url}>{config.url}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                        {config.auth_mode || (config.auth ? 'sso' : 'none')}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs ${config.enabled ? 'text-green-600' : 'text-gray-400'}`}>
                        {config.enabled ? 'Yes' : 'No'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right space-x-2">
                      <button
                        onClick={() => onEdit(name, config)}
                        className="text-xs px-2 py-1 text-blue-600 hover:bg-blue-50 rounded"
                      >Edit</button>
                      <button
                        onClick={() => handleTest(name)}
                        disabled={!!action}
                        className="text-xs px-2 py-1 text-amber-600 hover:bg-amber-50 rounded disabled:opacity-50"
                      >{action === 'testing' ? 'Testing...' : 'Test'}</button>
                      <button
                        onClick={() => handleFetch(name)}
                        disabled={!!action}
                        className="text-xs px-2 py-1 text-green-600 hover:bg-green-50 rounded disabled:opacity-50"
                      >{action === 'fetching' ? 'Fetching...' : 'Fetch Tools'}</button>
                      <button
                        onClick={() => handleDelete(name)}
                        className="text-xs px-2 py-1 text-red-500 hover:bg-red-50 rounded"
                      >Delete</button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 11: Create src/frontend/src/App.tsx (initial version — server list only)**

```tsx
import { useState, useCallback } from 'react'
import type { McpServerConfig } from './types'
import ServerList from './components/ServerList'
import Toast from './components/Toast'

type ToastState = { message: string; type: 'success' | 'error' | 'info' } | null

export default function App() {
  const [toast, setToast] = useState<ToastState>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [_editingServer, setEditingServer] = useState<{ name: string; config: McpServerConfig } | null>(null)
  const [_showForm, setShowForm] = useState(false)
  const [_viewingTools, setViewingTools] = useState<string | null>(null)

  const handleToast = useCallback((message: string, type: 'success' | 'error' | 'info') => {
    setToast({ message, type })
  }, [])

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">MCP Tools Fetch</h1>
        <p className="text-sm text-gray-500 mt-1">Manage MCP server configurations and fetch available tools</p>
      </header>

      <ServerList
        onEdit={(name, config) => { setEditingServer({ name, config }); setShowForm(true) }}
        onAdd={() => { setEditingServer(null); setShowForm(true) }}
        onViewTools={(name) => setViewingTools(name)}
        onToast={handleToast}
        refreshKey={refreshKey}
      />

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  )
}
```

- [ ] **Step 12: Install frontend dependencies and verify it compiles**

```bash
cd /Users/abhiskum/work/code/data_and_ai/dataverse/mcp/mcp-tools-fetch/src/frontend
npm install
npx tsc --noEmit
```

Expected: No type errors.

- [ ] **Step 13: Commit**

```bash
git add src/frontend/
git commit -m "feat: React frontend scaffolding with server list component"
```

---

### Task 7: React Frontend — Server Form & Tools Viewer

**Files:**
- Create: `src/frontend/src/components/ServerForm.tsx`, `src/frontend/src/components/ToolsViewer.tsx`
- Modify: `src/frontend/src/App.tsx` — wire in form and tools viewer

**Interfaces:**
- Consumes: `api.ts` functions, `types.ts` types, `ServerList` callbacks
- Produces: Complete working UI with add/edit modal and tools viewer

- [ ] **Step 1: Create src/frontend/src/components/ServerForm.tsx**

```tsx
import { useState, useEffect } from 'react'
import type { McpServerConfig, OAuthConfig } from '../types'

interface Props {
  name?: string
  config?: McpServerConfig
  onSave: (name: string, config: McpServerConfig) => void
  onCancel: () => void
}

const DEFAULT_CONFIG: McpServerConfig = {
  enabled: true,
  url: '',
  transport: 'streamable_http',
  ssl_verify: true,
  auth: false,
  description: '',
  auth_mode: null,
  oauth: null,
  timeout: 30,
}

export default function ServerForm({ name: editName, config: editConfig, onSave, onCancel }: Props) {
  const [name, setName] = useState(editName || '')
  const [config, setConfig] = useState<McpServerConfig>(editConfig || DEFAULT_CONFIG)
  const [oauth, setOauth] = useState<OAuthConfig>(editConfig?.oauth || {})
  const isEdit = !!editName

  useEffect(() => {
    if (editConfig?.oauth) setOauth(editConfig.oauth)
  }, [editConfig])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const finalConfig: McpServerConfig = {
      ...config,
      oauth: (config.auth_mode === 'oauth' || config.auth_mode === 'dcr') ? oauth : undefined,
    }
    onSave(name, finalConfig)
  }

  function updateConfig<K extends keyof McpServerConfig>(key: K, value: McpServerConfig[K]) {
    setConfig(prev => ({ ...prev, [key]: value }))
  }

  function updateOauth<K extends keyof OAuthConfig>(key: K, value: OAuthConfig[K]) {
    setOauth(prev => ({ ...prev, [key]: value }))
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <h3 className="text-lg font-semibold text-gray-900">
            {isEdit ? `Edit: ${editName}` : 'Add MCP Server'}
          </h3>

          {!isEdit && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Server Name</label>
              <input
                required
                value={name}
                onChange={e => setName(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                placeholder="my-mcp-server"
              />
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
            <input
              required
              value={config.url}
              onChange={e => updateConfig('url', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              placeholder="https://example.com/mcp"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <input
              value={config.description}
              onChange={e => updateConfig('description', e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Transport</label>
              <select
                value={config.transport}
                onChange={e => updateConfig('transport', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              >
                <option value="streamable_http">Streamable HTTP</option>
                <option value="sse">SSE</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Timeout (s)</label>
              <input
                type="number"
                value={config.timeout}
                onChange={e => updateConfig('timeout', parseInt(e.target.value) || 30)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={config.enabled}
                onChange={e => updateConfig('enabled', e.target.checked)}
                className="rounded"
              /> Enabled
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={config.ssl_verify}
                onChange={e => updateConfig('ssl_verify', e.target.checked)}
                className="rounded"
              /> SSL Verify
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={config.auth}
                onChange={e => updateConfig('auth', e.target.checked)}
                className="rounded"
              /> Auth Required
            </label>
          </div>

          {config.auth && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Auth Mode</label>
              <select
                value={config.auth_mode || 'sso'}
                onChange={e => updateConfig('auth_mode', e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
              >
                <option value="sso">SSO (JWT from .env)</option>
                <option value="oauth">OAuth (Authorization Code)</option>
                <option value="dcr">DCR (Dynamic Client Registration)</option>
              </select>
            </div>
          )}

          {config.auth && config.auth_mode === 'sso' && (
            <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
              Token will be read from env variable: <code className="font-mono bg-gray-200 px-1 rounded">
                MCP_{name.toUpperCase().replace(/-/g, '_')}_TOKEN
              </code>
            </div>
          )}

          {config.auth && (config.auth_mode === 'oauth' || config.auth_mode === 'dcr') && (
            <div className="border border-gray-200 rounded-lg p-4 space-y-3">
              <h4 className="text-sm font-medium text-gray-700">OAuth Configuration</h4>

              {config.auth_mode === 'dcr' && (
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Registration Endpoint</label>
                  <input
                    value={oauth.registration_endpoint || ''}
                    onChange={e => updateOauth('registration_endpoint', e.target.value)}
                    className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                  />
                </div>
              )}

              {config.auth_mode === 'oauth' && (
                <>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Client ID</label>
                    <input
                      value={oauth.client_id || ''}
                      onChange={e => updateOauth('client_id', e.target.value)}
                      className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-gray-500 mb-1">Client Secret Env Variable</label>
                    <input
                      value={oauth.client_secret_env || ''}
                      onChange={e => updateOauth('client_secret_env', e.target.value)}
                      className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                      placeholder="MCP_MY_SERVER_CLIENT_SECRET"
                    />
                  </div>
                </>
              )}

              <div>
                <label className="block text-xs text-gray-500 mb-1">Authorization Endpoint</label>
                <input
                  value={oauth.authorization_endpoint || ''}
                  onChange={e => updateOauth('authorization_endpoint', e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Token Endpoint</label>
                <input
                  value={oauth.token_endpoint || ''}
                  onChange={e => updateOauth('token_endpoint', e.target.value)}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Scopes (comma-separated)</label>
                <input
                  value={(oauth.scopes || []).join(', ')}
                  onChange={e => updateOauth('scopes', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                  className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm"
                  placeholder="openid, profile, email"
                />
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg"
            >Cancel</button>
            <button
              type="submit"
              className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium"
            >Save</button>
          </div>
        </form>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create src/frontend/src/components/ToolsViewer.tsx**

```tsx
import { useState, useEffect } from 'react'
import type { ToolInfo } from '../types'
import * as api from '../api'

interface Props {
  serverName: string
  onBack: () => void
  onToast: (message: string, type: 'success' | 'error' | 'info') => void
}

export default function ToolsViewer({ serverName, onBack, onToast }: Props) {
  const [tools, setTools] = useState<ToolInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  useEffect(() => { loadTools() }, [serverName])

  async function loadTools() {
    try {
      const data = await api.getTools(serverName)
      setTools(data.tools)
    } catch {
      setTools([])
    } finally {
      setLoading(false)
    }
  }

  async function handleRefetch() {
    setLoading(true)
    try {
      const result = await api.fetchTools(serverName)
      if (result.success) {
        setTools(result.tools)
        onToast(result.message, 'success')
      } else {
        onToast(result.message, 'error')
      }
    } catch (e) {
      onToast(`Fetch failed: ${e}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  function toggleExpand(name: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

  if (loading) return <div className="text-center py-12 text-gray-500">Loading tools...</div>

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="text-sm text-gray-500 hover:text-gray-700"
          >&larr; Back</button>
          <h2 className="text-xl font-semibold text-gray-800">
            Tools: {serverName}
            <span className="text-sm font-normal text-gray-500 ml-2">({tools.length} tools)</span>
          </h2>
        </div>
        <button
          onClick={handleRefetch}
          disabled={loading}
          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium disabled:opacity-50"
        >Re-fetch</button>
      </div>

      {tools.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          No tools found. Try fetching tools first.
        </div>
      ) : (
        <div className="space-y-2">
          {tools.map(tool => (
            <div key={tool.name} className="bg-white border border-gray-200 rounded-lg overflow-hidden">
              <button
                onClick={() => toggleExpand(tool.name)}
                className="w-full text-left px-4 py-3 flex justify-between items-start hover:bg-gray-50"
              >
                <div>
                  <span className="font-mono text-sm font-medium text-gray-900">{tool.name}</span>
                  {tool.description && (
                    <p className="text-sm text-gray-500 mt-0.5">{tool.description}</p>
                  )}
                </div>
                <span className="text-gray-400 text-xs mt-1">
                  {expanded.has(tool.name) ? '▼' : '▶'}
                </span>
              </button>
              {expanded.has(tool.name) && tool.inputSchema && (
                <div className="px-4 pb-3 border-t border-gray-100">
                  <pre className="text-xs bg-gray-50 rounded p-3 overflow-x-auto mt-2 text-gray-700">
                    {JSON.stringify(tool.inputSchema, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 3: Update src/frontend/src/App.tsx — wire in ServerForm and ToolsViewer**

Replace the entire App.tsx:

```tsx
import { useState, useCallback } from 'react'
import type { McpServerConfig } from './types'
import ServerList from './components/ServerList'
import ServerForm from './components/ServerForm'
import ToolsViewer from './components/ToolsViewer'
import Toast from './components/Toast'
import * as api from './api'

type ToastState = { message: string; type: 'success' | 'error' | 'info' } | null

export default function App() {
  const [toast, setToast] = useState<ToastState>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [editingServer, setEditingServer] = useState<{ name: string; config: McpServerConfig } | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [viewingTools, setViewingTools] = useState<string | null>(null)

  const handleToast = useCallback((message: string, type: 'success' | 'error' | 'info') => {
    setToast({ message, type })
  }, [])

  async function handleSave(name: string, config: McpServerConfig) {
    try {
      if (editingServer) {
        await api.updateServer(name, config)
        handleToast(`Server '${name}' updated`, 'success')
      } else {
        await api.createServer(name, config)
        handleToast(`Server '${name}' created`, 'success')
      }
      setShowForm(false)
      setEditingServer(null)
      setRefreshKey(k => k + 1)
    } catch (e) {
      handleToast(`Save failed: ${e}`, 'error')
    }
  }

  if (viewingTools) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <header className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">MCP Tools Fetch</h1>
          <p className="text-sm text-gray-500 mt-1">Manage MCP server configurations and fetch available tools</p>
        </header>
        <ToolsViewer
          serverName={viewingTools}
          onBack={() => setViewingTools(null)}
          onToast={handleToast}
        />
        {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">MCP Tools Fetch</h1>
        <p className="text-sm text-gray-500 mt-1">Manage MCP server configurations and fetch available tools</p>
      </header>

      <ServerList
        onEdit={(name, config) => { setEditingServer({ name, config }); setShowForm(true) }}
        onAdd={() => { setEditingServer(null); setShowForm(true) }}
        onViewTools={(name) => setViewingTools(name)}
        onToast={handleToast}
        refreshKey={refreshKey}
      />

      {showForm && (
        <ServerForm
          name={editingServer?.name}
          config={editingServer?.config}
          onSave={handleSave}
          onCancel={() => { setShowForm(false); setEditingServer(null) }}
        />
      )}

      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}
    </div>
  )
}
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /Users/abhiskum/work/code/data_and_ai/dataverse/mcp/mcp-tools-fetch/src/frontend
npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add src/frontend/src/components/ServerForm.tsx src/frontend/src/components/ToolsViewer.tsx src/frontend/src/App.tsx
git commit -m "feat: server form modal and tools viewer components"
```

---

### Task 8: Integration Test & Polish

**Files:**
- Modify: `src/app/mcp_client.py` — handle `notifications/initialized` as a notification (no id)
- Modify: `src/app/main.py` — add a health check endpoint for quick validation

**Interfaces:**
- Consumes: Everything built so far
- Produces: Fully runnable application

- [ ] **Step 1: Fix notifications/initialized to send as a notification (no id field)**

In `src/app/mcp_client.py`, update `_make_jsonrpc_request` to accept `is_notification` parameter:

```python
async def _make_jsonrpc_request(
    url: str,
    method: str,
    params: dict | None = None,
    token: str | None = None,
    ssl_verify: bool = True,
    timeout: int = 30,
    session_id: str | None = None,
    is_notification: bool = False,
) -> tuple[dict, str | None]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    payload: dict = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if not is_notification:
        payload["id"] = 1
    if params:
        payload["params"] = params

    async with httpx.AsyncClient(verify=ssl_verify, timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()

        new_session_id = resp.headers.get("Mcp-Session-Id", session_id)

        if is_notification:
            return {}, new_session_id

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return _parse_sse_response(resp.text), new_session_id
        return resp.json(), new_session_id
```

Update the `mcp_list_tools` function to pass `is_notification=True`:

```python
    await _make_jsonrpc_request(
        url=server_config.url,
        method="notifications/initialized",
        token=token,
        ssl_verify=server_config.ssl_verify,
        timeout=server_config.timeout,
        session_id=session_id,
        is_notification=True,
    )
```

- [ ] **Step 2: Add health check to main.py**

Add before the static mount:

```python
@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/abhiskum/work/code/data_and_ai/dataverse/mcp/mcp-tools-fetch
uv run pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Manual smoke test — start backend**

```bash
uv run uvicorn src.app.main:app --reload --port 8000
```

In another terminal:
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/servers
```

Expected: `{"status":"ok"}` and `{"servers":{}}`.

- [ ] **Step 5: Manual smoke test — start frontend**

```bash
cd src/frontend
npm run dev
```

Open `http://localhost:5173` in browser. Verify:
- Page loads with "MCP Tools Fetch" header
- "No servers configured" message shows
- "Add Server" button is visible and opens the form modal

- [ ] **Step 6: Commit**

```bash
git add src/app/mcp_client.py src/app/main.py
git commit -m "fix: notification handling and add health endpoint"
```

---

### Task 9: End-to-End Validation with Sample Config

**Files:**
- Modify: `mcp.json` — add sample server configs from the spec

- [ ] **Step 1: Load sample mcp.json**

Replace `mcp.json` with representative entries from the spec (at least one SSO, one OAuth, one DCR):

```json
{
  "mcpServers": {
    "dataverse-mcp": {
      "enabled": true,
      "url": "https://mcp-dataverse.apps.int.spoke.preprod.us-west-2.aws.paas.redhat.com/mcp/",
      "transport": "streamable_http",
      "ssl_verify": false,
      "auth": true,
      "description": "Dataverse MCP Server",
      "auth_mode": "sso",
      "timeout": 30
    },
    "jira-mcp": {
      "enabled": true,
      "url": "https://mcp.atlassian.com/v1/mcp/authv2",
      "transport": "streamable_http",
      "ssl_verify": true,
      "auth": true,
      "description": "Hosted JIRA MCP",
      "auth_mode": "dcr",
      "oauth": {
        "registration_endpoint": "https://cf.mcp.atlassian.com/v1/register",
        "authorization_endpoint": "https://mcp.atlassian.com/v1/authorize",
        "token_endpoint": "https://cf.mcp.atlassian.com/v1/token"
      }
    },
    "slack-mcp": {
      "enabled": true,
      "url": "https://mcp.slack.com/mcp",
      "transport": "streamable_http",
      "ssl_verify": true,
      "auth": true,
      "description": "Slack MCP Sandbox",
      "auth_mode": "oauth",
      "oauth": {
        "grant_type": "authorization_code",
        "token_endpoint": "https://slack.com/api/oauth.v2.user.access",
        "client_id": "3956724112500.11611864741076",
        "client_secret_env": "MCP_SLACK_MCP_CLIENT_SECRET",
        "authorization_endpoint": "https://slack.com/oauth/v2_user/authorize",
        "scopes": ["channels:history", "channels:read", "chat:write", "search:read.public"]
      }
    }
  }
}
```

- [ ] **Step 2: Verify servers load in the UI**

Start backend and frontend. Open browser to `http://localhost:5173`. Verify:
- 3 servers appear in the table
- SSO server shows red dot (no token in .env)
- DCR and OAuth servers show red dot (no token yet)
- Edit opens pre-filled form with correct auth mode sections
- Auth mode badge shows correctly per server

- [ ] **Step 3: Test connection on an SSO server**

Add a token to `.env`:
```
MCP_DATAVERSE_MCP_TOKEN=your-jwt-token-here
```

Click "Test" on dataverse-mcp. Verify it attempts connection (may fail if token is invalid, but the flow should work — no crashes, proper error message in toast).

- [ ] **Step 4: Commit final state**

```bash
git add mcp.json
git commit -m "feat: sample MCP server configurations for validation"
```
