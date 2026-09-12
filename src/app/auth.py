import base64
import hashlib
import ipaddress
import logging
import re
import secrets
import socket
import time
from urllib.parse import urlencode, urlparse

import httpx

from .config import get_backend_port, get_env_var
from .database import delete_secret, get_secret, set_secret
from .models import McpServerConfig

logger = logging.getLogger(__name__)

_SERVER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,254}$")

_FLOW_TTL_SECONDS = 600
_MAX_PENDING_FLOWS = 100


def validate_server_name(name: str) -> str:
    if not _SERVER_NAME_RE.match(name):
        raise ValueError(
            "Server name must start with alphanumeric and contain only "
            "alphanumeric, hyphens, underscores, and dots (max 255 chars)"
        )
    return name


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL must use http or https scheme")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must have a valid hostname")
    try:
        resolved = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in resolved:
            addr = ipaddress.ip_address(sockaddr[0])
            if addr.is_private or addr.is_loopback or addr.is_link_local:
                raise ValueError("URL must not resolve to a private/loopback address")
    except socket.gaierror as err:
        raise ValueError(f"Cannot resolve hostname: {hostname}") from err
    return url


def _get_callback_url() -> str:
    return f"http://localhost:{get_backend_port()}/mcp/oauth/callback"


_pending_flows: dict[str, dict] = {}


def _cleanup_expired_flows() -> None:
    now = time.monotonic()
    expired = [k for k, v in _pending_flows.items() if now - v.get("created_at", 0) > _FLOW_TTL_SECONDS]
    for k in expired:
        _pending_flows.pop(k, None)


def _server_name_to_env_key(server_name: str) -> str:
    return f"MCP_{server_name.upper().replace('-', '_')}_TOKEN"


async def _get_bearer_token(server_name: str) -> str | None:
    env_key = _server_name_to_env_key(server_name)
    token = get_env_var(env_key)
    if token:
        return token
    bearer_entry = await get_secret(server_name, "bearer")
    if bearer_entry and "token" in bearer_entry:
        token_val: str | None = bearer_entry["token"]
        return token_val
    return None


async def set_bearer_token(server_name: str, token: str) -> None:
    await set_secret(server_name, "bearer", {"token": token})


async def _get_api_key(server_name: str) -> str | None:
    entry = await get_secret(server_name, "apikey")
    if entry and "key" in entry:
        key_val: str | None = entry["key"]
        return key_val
    return None


async def set_api_key(server_name: str, key: str) -> None:
    await set_secret(server_name, "apikey", {"key": key})


async def _register_dcr_client(server_config: McpServerConfig) -> tuple[str, str | None]:
    oauth = server_config.oauth
    assert oauth is not None
    payload = {
        "client_name": "mcp-tools-fetch",
        "redirect_uris": [_get_callback_url()],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
    }
    if oauth.scopes:
        payload["scope"] = " ".join(oauth.scopes)
    assert oauth.registration_endpoint is not None
    async with httpx.AsyncClient(verify=server_config.ssl_verify) as client:
        resp = await client.post(oauth.registration_endpoint, json=payload)
        if resp.status_code >= 400:
            logger.error("DCR registration failed (%s): %s", resp.status_code, resp.text)
        resp.raise_for_status()
        data = resp.json()
        return data["client_id"], data.get("client_secret")


async def start_oauth_flow(server_name: str, server_config: McpServerConfig) -> str:
    oauth = server_config.oauth
    assert oauth is not None
    client_id = oauth.client_id
    client_secret = None

    if server_config.auth_mode == "dcr":
        dcr_data = await get_secret(server_name, "dcr")
        if dcr_data:
            client_id = dcr_data["client_id"]
            client_secret = dcr_data.get("client_secret")
        else:
            client_id, client_secret = await _register_dcr_client(server_config)
            await set_secret(
                server_name,
                "dcr",
                {
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
    else:
        secret_env = oauth.client_secret_env
        if secret_env:
            client_secret = get_env_var(secret_env)

    _cleanup_expired_flows()
    if len(_pending_flows) >= _MAX_PENDING_FLOWS:
        raise ValueError("Too many pending OAuth flows. Please try again later.")

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()

    _pending_flows[state] = {
        "server_name": server_name,
        "client_id": client_id,
        "client_secret": client_secret,
        "code_verifier": code_verifier,
        "token_endpoint": oauth.token_endpoint,
        "ssl_verify": server_config.ssl_verify,
        "created_at": time.monotonic(),
    }

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": _get_callback_url(),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
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
        "redirect_uri": _get_callback_url(),
        "client_id": flow["client_id"],
        "code_verifier": flow["code_verifier"],
    }
    if flow["client_secret"]:
        token_data["client_secret"] = flow["client_secret"]

    async with httpx.AsyncClient(verify=flow["ssl_verify"]) as client:
        resp = await client.post(flow["token_endpoint"], data=token_data)
        resp.raise_for_status()
        token_resp = resp.json()

    await set_secret(
        flow["server_name"],
        "oauth",
        {
            "access_token": token_resp["access_token"],
            "refresh_token": token_resp.get("refresh_token"),
            "token_type": token_resp.get("token_type", "Bearer"),
        },
    )
    server: str = flow["server_name"]
    return server


async def get_token(server_name: str, server_config: McpServerConfig) -> str | None:
    if not server_config.auth:
        return None

    if server_config.auth_mode == "bearer_token" or server_config.auth_mode is None:
        token = await _get_bearer_token(server_name)
        if token:
            return token
        raise ValueError(f"Bearer token not found. Set {_server_name_to_env_key(server_name)} in .env")

    if server_config.auth_mode == "api_key":
        key = await _get_api_key(server_name)
        if key:
            return key
        raise ValueError(f"API key not found for '{server_name}'. Set it via the UI.")

    oauth_data = await get_secret(server_name, "oauth")
    if oauth_data and "access_token" in oauth_data:
        access_token: str | None = oauth_data["access_token"]
        return access_token

    return None


async def refresh_access_token(server_name: str, server_config: McpServerConfig) -> str | None:
    if server_config.auth_mode not in ("oauth", "dcr"):
        return None

    oauth_data = await get_secret(server_name, "oauth")
    if not oauth_data or not oauth_data.get("refresh_token"):
        logger.info("No refresh token for '%s', re-auth required", server_name)
        return None

    oauth = server_config.oauth
    if not oauth or not oauth.token_endpoint:
        return None

    client_id = oauth.client_id
    client_secret = None

    if server_config.auth_mode == "dcr":
        dcr_data = await get_secret(server_name, "dcr")
        if dcr_data:
            client_id = dcr_data["client_id"]
            client_secret = dcr_data.get("client_secret")
        else:
            return None
    else:
        if oauth.client_secret_env:
            client_secret = get_env_var(oauth.client_secret_env)

    token_data = {
        "grant_type": "refresh_token",
        "refresh_token": oauth_data["refresh_token"],
        "client_id": client_id,
    }
    if client_secret:
        token_data["client_secret"] = client_secret

    try:
        async with httpx.AsyncClient(verify=server_config.ssl_verify) as client:
            resp = await client.post(oauth.token_endpoint, data=token_data)
            if resp.status_code >= 400:
                logger.warning(
                    "Token refresh failed for '%s' (%s): %s",
                    server_name,
                    resp.status_code,
                    resp.text,
                )
                return None
            token_resp = resp.json()
    except Exception:
        logger.exception("Token refresh request failed for '%s'", server_name)
        return None

    await set_secret(
        server_name,
        "oauth",
        {
            "access_token": token_resp["access_token"],
            "refresh_token": token_resp.get("refresh_token", oauth_data["refresh_token"]),
            "token_type": token_resp.get("token_type", "Bearer"),
        },
    )
    logger.info("Token refreshed successfully for '%s'", server_name)
    refreshed_token: str | None = token_resp["access_token"]
    return refreshed_token


async def clear_oauth_tokens(server_name: str) -> None:
    await delete_secret(server_name, "oauth")


async def get_auth_status(server_name: str, server_config: McpServerConfig) -> dict:
    if not server_config.auth:
        return {"authenticated": True, "auth_mode": None}

    if server_config.auth_mode == "bearer_token" or server_config.auth_mode is None:
        token = await _get_bearer_token(server_name)
        return {"authenticated": token is not None, "auth_mode": "bearer_token"}

    if server_config.auth_mode == "api_key":
        key = await _get_api_key(server_name)
        return {"authenticated": key is not None, "auth_mode": "api_key"}

    oauth_data = await get_secret(server_name, "oauth")
    has_token = oauth_data is not None and "access_token" in oauth_data
    return {"authenticated": has_token, "auth_mode": server_config.auth_mode}


def _derive_base_urls(url: str) -> list[str]:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    candidates = []
    while path:
        candidates.append(f"{base}{path}")
        path = path.rsplit("/", 1)[0]
    candidates.append(base)
    return candidates


_WELL_KNOWN_PATHS = [
    "/.well-known/openid-configuration",
    "/.well-known/oauth-authorization-server",
]


async def discover_oauth_metadata(url: str, ssl_verify: bool = True) -> dict:
    candidates = _derive_base_urls(url)
    async with httpx.AsyncClient(verify=ssl_verify, timeout=5.0) as client:
        for base_url in candidates:
            for wk_path in _WELL_KNOWN_PATHS:
                probe = f"{base_url}{wk_path}"
                try:
                    resp = await client.get(probe)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    if not isinstance(data, dict) or "authorization_endpoint" not in data:
                        continue
                    return {
                        "issuer": data.get("issuer"),
                        "authorization_endpoint": data.get("authorization_endpoint"),
                        "token_endpoint": data.get("token_endpoint"),
                        "registration_endpoint": data.get("registration_endpoint"),
                        "scopes_supported": data.get("scopes_supported", []),
                        "grant_types_supported": data.get("grant_types_supported", []),
                        "response_types_supported": data.get("response_types_supported", []),
                        "discovery_url": probe,
                    }
                except Exception:
                    logger.debug("Discovery probe failed: %s", probe)
    raise ValueError(f"No OAuth metadata found. Tried {len(candidates) * len(_WELL_KNOWN_PATHS)} URLs.")
