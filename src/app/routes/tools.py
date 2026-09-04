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
