from pathlib import Path

import yaml

TOOLS_DIR = Path("tools")


def save_tools(server_name: str, tools: list[dict]) -> Path:
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
    path = TOOLS_DIR / f"{server_name}.yaml"
    if not path.exists():
        return None
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("tools", [])
