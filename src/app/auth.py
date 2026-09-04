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


def _get_sso_token(server_name: str) -> str | None:
    env_key = _server_name_to_env_key(server_name)
    return get_env_var(env_key)


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
