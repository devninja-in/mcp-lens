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
