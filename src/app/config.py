import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .models import McpConfig, McpServerConfig

logger = logging.getLogger(__name__)

load_dotenv()


async def load_config() -> McpConfig:
    from .database import get_all_servers

    servers_data = await get_all_servers()
    servers = {name: McpServerConfig.model_validate(data) for name, data in servers_data.items()}
    logger.debug("Loaded config with %d servers", len(servers))
    return McpConfig(**{"mcpServers": servers})


async def save_config(config: McpConfig) -> None:
    from .database import delete_server_config, get_all_servers, set_server_config

    existing = await get_all_servers()
    for name in existing:
        if name not in config.mcp_servers:
            await delete_server_config(name)
    for name, server in config.mcp_servers.items():
        await set_server_config(name, server.model_dump(exclude_none=True))
    logger.info("Saved config with %d servers", len(config.mcp_servers))


def get_env_var(name: str) -> str | None:
    return os.environ.get(name)


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    db_path = Path("mcp_secrets.db").resolve()
    return f"sqlite+aiosqlite:///{db_path}"


def get_backend_port() -> int:
    return int(os.environ.get("BACKEND_PORT", "5002"))


def get_frontend_port() -> int:
    return int(os.environ.get("FRONTEND_PORT", "5173"))


def persist_oauth_tokens() -> bool:
    return os.environ.get("PERSIST_OAUTH_TOKENS", "false").lower() in ("true", "1", "yes")
