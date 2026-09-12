import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

TOOLS_DIR = Path("tools")


def _validate_server_name(server_name: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_\-]+", server_name):
        raise ValueError(f"Invalid server name: {server_name!r}")


def save_tools(server_name: str, tools: list[dict], source: str = "fetched") -> Path:
    _validate_server_name(server_name)
    TOOLS_DIR.mkdir(exist_ok=True)
    path = TOOLS_DIR / f"{server_name}.yaml"
    with open(path, "w") as f:
        yaml.dump(
            {"server": server_name, "tools_count": len(tools), "source": source, "tools": tools},
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    logger.info("Saved %d tools for '%s' (source=%s) to %s", len(tools), server_name, source, path)
    return path


def load_tools(server_name: str) -> dict | None:
    """Return {"tools": [...], "source": "fetched"|"uploaded"} or None."""
    _validate_server_name(server_name)
    path = TOOLS_DIR / f"{server_name}.yaml"
    if not path.exists():
        logger.debug("No tools file found for '%s' at %s", server_name, path)
        return None
    with open(path) as f:
        data = yaml.safe_load(f)
    tools = data.get("tools", [])
    source = data.get("source", "fetched")
    logger.debug("Loaded %d tools for '%s' (source=%s)", len(tools), server_name, source)
    return {"tools": tools, "source": source}


def delete_tools(server_name: str) -> bool:
    _validate_server_name(server_name)
    path = TOOLS_DIR / f"{server_name}.yaml"
    if path.exists():
        path.unlink()
        logger.info("Deleted tools file for '%s'", server_name)
        return True
    return False
