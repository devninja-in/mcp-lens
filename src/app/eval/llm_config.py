from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .model_adapter import ModelAdapter, get_adapter

logger = logging.getLogger(__name__)

LLM_CONFIG_PATH = Path("llm.json")

_INSTALL_HINTS = {
    "openai": "uv sync --extra eval-openai  (or: pip install openai)",
    "anthropic": "uv sync --extra eval-anthropic  (or: pip install anthropic)",
    "vertexai": "uv sync --extra eval-vertexai  (or: pip install google-genai)",
    "anthropic-vertex": "uv sync --extra eval-anthropic-vertex  (or: pip install 'anthropic[vertex]')",
}


def _resolve_config(cfg: dict) -> dict:
    resolved = {}
    for key, value in cfg.items():
        if key.endswith("_env") and isinstance(value, str):
            base_key = key[:-4]
            resolved[base_key] = os.environ.get(value, "").strip() or None
        else:
            resolved[key] = value
    return resolved


def load_llm_configs() -> dict[str, dict] | None:
    if not LLM_CONFIG_PATH.exists():
        return None
    try:
        with open(LLM_CONFIG_PATH) as f:
            data = json.load(f)
        configs = data.get("configs", {})
        resolved = {}
        for name, cfg in configs.items():
            resolved[name] = _resolve_config(cfg)
        logger.info("Loaded %d LLM configs from llm.json", len(resolved))
        return resolved
    except Exception as e:
        logger.error("Failed to load llm.json: %s", e)
        return None


def get_default_llm_name() -> str | None:
    if not LLM_CONFIG_PATH.exists():
        return None
    try:
        with open(LLM_CONFIG_PATH) as f:
            data = json.load(f)
        default: str | None = data.get("default")
        return default
    except Exception:
        return None


def get_available_llm_configs() -> dict:
    result: dict[str, dict] = {}
    configs = load_llm_configs()
    if configs:
        for name, cfg in configs.items():
            result[name] = {
                "provider": cfg.get("provider", ""),
                "model": cfg.get("model", ""),
                "has_credentials": bool(cfg.get("api_key") or cfg.get("project")),
            }
    return result


def get_adapter_for_config(config_name: str) -> ModelAdapter:
    configs = load_llm_configs()
    if not configs or config_name not in configs:
        raise ValueError(f"Unknown LLM config: '{config_name}'")
    cfg = configs[config_name]
    provider = cfg.get("provider", "")
    hint = _INSTALL_HINTS.get(provider, f"Install the package for '{provider}'")
    try:
        adapter = get_adapter(
            name=provider,
            model=cfg.get("model"),
            api_key=cfg.get("api_key"),
            base_url=cfg.get("base_url"),
            project=cfg.get("project"),
            location=cfg.get("location"),
        )
        logger.info("Created adapter for config '%s': provider=%s model=%s", config_name, provider, cfg.get("model"))
        return adapter
    except ImportError as err:
        logger.error("Missing dependency for LLM config '%s' (provider=%s)", config_name, provider)
        raise ImportError(f"Missing dependency for LLM provider '{provider}'. Install it with: {hint}") from err
