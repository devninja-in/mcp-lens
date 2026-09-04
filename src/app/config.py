import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .models import McpConfig

load_dotenv()

CONFIG_PATH = Path("mcp.json")


def load_config() -> McpConfig:
    if not CONFIG_PATH.exists():
        return McpConfig()
    with open(CONFIG_PATH) as f:
        return McpConfig.model_validate(json.load(f))


def save_config(config: McpConfig) -> None:
    with open(CONFIG_PATH, "w") as f:
        json.dump(config.model_dump(exclude_none=True), f, indent=2)


def get_env_var(name: str) -> str | None:
    return os.environ.get(name)
