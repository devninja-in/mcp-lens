import html as html_lib
import logging
import webbrowser

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from ..auth import (
    discover_oauth_metadata,
    get_auth_status,
    handle_oauth_callback,
    set_api_key,
    set_bearer_token,
    start_oauth_flow,
    validate_url,
)
from ..config import get_frontend_port, load_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
oauth_callback_router = APIRouter(tags=["oauth"])


@router.get("/status/{name}")
async def auth_status(name: str) -> dict:
    config = await load_config()
    if name not in config.mcp_servers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    return await get_auth_status(name, config.mcp_servers[name])


@router.post("/bearer-token/{name}")
async def save_bearer_token(name: str, body: dict) -> dict:
    config = await load_config()
    if name not in config.mcp_servers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    server = config.mcp_servers[name]
    if server.auth_mode not in ("bearer_token", None):
        raise HTTPException(status_code=400, detail="Server does not use Bearer Token auth")
    token = body.get("token", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")
    await set_bearer_token(name, token)
    return {"success": True, "message": f"Bearer token saved for '{name}'"}


@router.post("/api-key/{name}")
async def save_api_key_endpoint(name: str, body: dict) -> dict:
    config = await load_config()
    if name not in config.mcp_servers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    server = config.mcp_servers[name]
    if server.auth_mode != "api_key":
        raise HTTPException(status_code=400, detail="Server does not use API Key auth")
    key = body.get("key", "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key is required")
    await set_api_key(name, key)
    return {"success": True, "message": f"API key saved for '{name}'"}


@router.post("/discover")
async def discover_endpoints(body: dict) -> dict:
    url = (body.get("url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    try:
        validate_url(url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    ssl_verify = body.get("ssl_verify", True)
    try:
        return await discover_oauth_metadata(url, ssl_verify)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.exception("OAuth discovery failed")
        raise HTTPException(status_code=502, detail="Discovery failed. Check server logs.") from e


@router.post("/start/{name}")
async def start_auth(name: str) -> dict:
    config = await load_config()
    if name not in config.mcp_servers:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    server = config.mcp_servers[name]
    if server.auth_mode not in ("oauth", "dcr"):
        raise HTTPException(status_code=400, detail="Server does not use OAuth/DCR auth")
    try:
        auth_url = await start_oauth_flow(name, server)
    except Exception as e:
        logger.exception("Auth flow failed for server %s", name)
        raise HTTPException(status_code=502, detail="Auth flow failed. Check server logs for details.") from e
    webbrowser.open(auth_url)
    return {"auth_url": auth_url, "message": "Browser opened for authorization"}


@oauth_callback_router.get("/mcp/oauth/callback")
async def oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> HTMLResponse:
    if error:
        msg = html_lib.escape(error_description or error)
        logger.error("OAuth callback error: %s — %s", error, error_description)
        return HTMLResponse(
            f"<html><body><h2>Authorization failed</h2>"
            f"<p>{msg}</p>"
            "<p>You can close this tab and try again.</p></body></html>",
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(
            "<html><body><h2>Authorization failed</h2>"
            "<p>Missing code or state parameter from OAuth provider.</p>"
            "<p>You can close this tab and try again.</p></body></html>",
            status_code=400,
        )
    try:
        server_name = await handle_oauth_callback(state, code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        logger.exception("OAuth token exchange failed")
        return HTMLResponse(
            "<html><body><h2>Authorization failed</h2>"
            "<p>Token exchange failed. Check server logs for details.</p></body></html>",
            status_code=502,
        )
    safe_name = html_lib.escape(server_name)
    fe_port = get_frontend_port()
    return HTMLResponse(
        f"<html><body><h2>Authorization successful for {safe_name}!</h2>"
        "<p>Redirecting back to the app...</p>"
        f'<script>window.location.href="http://localhost:{fe_port}?auth_success={safe_name}";</script>'
        "</body></html>"
    )
