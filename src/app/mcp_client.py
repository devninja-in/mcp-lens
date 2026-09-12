import logging

import httpx

from .auth import clear_oauth_tokens, get_token, refresh_access_token
from .models import McpServerConfig

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"


async def _make_jsonrpc_request(
    url: str,
    method: str,
    params: dict | None = None,
    token: str | None = None,
    ssl_verify: bool = True,
    timeout: int = 30,
    session_id: str | None = None,
    is_notification: bool = False,
    api_key_config: dict | None = None,
) -> tuple[dict, str | None]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if token and not api_key_config:
        headers["Authorization"] = f"Bearer {token}"
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    query_params = {}
    if token and api_key_config:
        location = api_key_config.get("location", "header")
        param_name = api_key_config.get("name", "X-API-Key")
        if location == "query":
            query_params[param_name] = token
        else:
            headers[param_name] = token

    payload: dict = {
        "jsonrpc": "2.0",
        "method": method,
    }
    if not is_notification:
        payload["id"] = 1
    if params:
        payload["params"] = params

    request_url = url
    if query_params:
        from urllib.parse import urlencode
        separator = "&" if "?" in url else "?"
        request_url = f"{url}{separator}{urlencode(query_params)}"

    async with httpx.AsyncClient(verify=ssl_verify, timeout=timeout) as client:
        resp = await client.post(request_url, json=payload, headers=headers)
        resp.raise_for_status()

        new_session_id = resp.headers.get("Mcp-Session-Id", session_id)

        if is_notification:
            return {}, new_session_id

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


def _get_api_key_dict(server_config: McpServerConfig) -> dict | None:
    if server_config.auth_mode == "api_key" and server_config.api_key_config:
        return {
            "location": server_config.api_key_config.location,
            "name": server_config.api_key_config.name,
        }
    return None


class ReAuthRequired(Exception):
    pass


async def _try_request_with_refresh(
    server_name: str,
    server_config: McpServerConfig,
    request_fn,
):
    token = await get_token(server_name, server_config)
    try:
        return await request_fn(token)
    except httpx.HTTPStatusError as e:
        if e.response.status_code not in (401, 403):
            raise
        status = e.response.status_code
    except Exception:
        raise

    if server_config.auth_mode not in ("oauth", "dcr"):
        raise ReAuthRequired(
            f"Server '{server_name}' returned {status}. Check your token."
        )

    logger.info("Got %s for '%s', attempting token refresh", status, server_name)
    new_token = await refresh_access_token(server_name, server_config)
    if not new_token:
        await clear_oauth_tokens(server_name)
        raise ReAuthRequired(
            f"Token expired for '{server_name}'. Re-authentication required."
        )

    try:
        return await request_fn(new_token)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            await clear_oauth_tokens(server_name)
            raise ReAuthRequired(
                f"Token expired for '{server_name}'. Re-authentication required."
            )
        raise


async def mcp_initialize(
    server_name: str, server_config: McpServerConfig
) -> tuple[dict, str | None]:
    akc = _get_api_key_dict(server_config)

    async def do_init(token):
        return await _make_jsonrpc_request(
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
            api_key_config=akc,
        )

    return await _try_request_with_refresh(server_name, server_config, do_init)


async def mcp_list_tools(
    server_name: str, server_config: McpServerConfig
) -> list[dict]:
    akc = _get_api_key_dict(server_config)

    async def do_list_tools(token):
        init_result, session_id = await _make_jsonrpc_request(
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
            api_key_config=akc,
        )

        if "error" in init_result:
            raise RuntimeError(f"Initialize failed: {init_result['error']}")

        await _make_jsonrpc_request(
            url=server_config.url,
            method="notifications/initialized",
            token=token,
            ssl_verify=server_config.ssl_verify,
            timeout=server_config.timeout,
            session_id=session_id,
            is_notification=True,
            api_key_config=akc,
        )

        result, _ = await _make_jsonrpc_request(
            url=server_config.url,
            method="tools/list",
            params={},
            token=token,
            ssl_verify=server_config.ssl_verify,
            timeout=server_config.timeout,
            session_id=session_id,
            api_key_config=akc,
        )

        if "error" in result:
            raise RuntimeError(f"tools/list failed: {result['error']}")

        return result.get("result", {}).get("tools", [])

    return await _try_request_with_refresh(server_name, server_config, do_list_tools)
