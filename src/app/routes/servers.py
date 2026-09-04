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
