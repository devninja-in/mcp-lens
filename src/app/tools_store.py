import re
from pathlib import Path

import yaml

TOOLS_DIR = Path("tools")


def _validate_server_name(server_name: str) -> None:
    if not re.fullmatch(r'[A-Za-z0-9_\-]+', server_name):
        raise ValueError(f"Invalid server name: {server_name!r}")


def save_tools(server_name: str, tools: list[dict]) -> Path:
    _validate_server_name(server_name)
    TOOLS_DIR.mkdir(exist_ok=True)
    path = TOOLS_DIR / f"{server_name}.yaml"
    with open(path, "w") as f:
        yaml.dump(
            {"server": server_name, "tools_count": len(tools), "tools": tools},
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
    return path


def load_tools(server_name: str) -> list[dict] | None:
    _validate_server_name(server_name)
    path = TOOLS_DIR / f"{server_name}.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("tools", [])
