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
