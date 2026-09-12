import logging

from fastapi import APIRouter, HTTPException

from ..auth import validate_server_name
from ..config import load_config
from ..database import delete_server_config, get_server_config, set_server_config
from ..models import ApiResponse, McpServerConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/servers", tags=["servers"])


@router.get("")
async def list_servers() -> dict:
    config = await load_config()
    return {"servers": {
        name: server.model_dump(exclude_none=True)
        for name, server in config.mcpServers.items()
    }}


@router.get("/{name}")
async def get_server(name: str) -> dict:
    data = await get_server_config(name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    return {"name": name, "config": McpServerConfig.model_validate(data).model_dump(exclude_none=True)}


@router.post("")
async def create_server(name: str, server: McpServerConfig) -> ApiResponse:
    try:
        validate_server_name(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    existing = await get_server_config(name)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Server '{name}' already exists")
    await set_server_config(name, server.model_dump(exclude_none=True))
    logger.info("Created server '%s' (url=%s)", name, server.url)
    return ApiResponse(success=True, message=f"Server '{name}' created")


@router.put("/{name}")
async def update_server(name: str, server: McpServerConfig) -> ApiResponse:
    existing = await get_server_config(name)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    await set_server_config(name, server.model_dump(exclude_none=True))
    logger.info("Updated server '%s'", name)
    return ApiResponse(success=True, message=f"Server '{name}' updated")


@router.delete("/{name}")
async def delete_server(name: str) -> ApiResponse:
    existing = await get_server_config(name)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Server '{name}' not found")
    await delete_server_config(name)
    logger.info("Deleted server '%s'", name)
    return ApiResponse(success=True, message=f"Server '{name}' deleted")
