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


def load_llm_config() -> dict | None:
    provider = os.environ.get("EVAL_LLM_PROVIDER", "").strip()
    if not provider:
        logger.debug("No EVAL_LLM_PROVIDER configured, LLM eval disabled")
        return None
    logger.info("LLM eval config: provider=%s", provider)
    return {
        "provider": provider,
        "model": os.environ.get("EVAL_LLM_MODEL", "").strip() or None,
        "api_key": os.environ.get("EVAL_LLM_API_KEY", "").strip() or None,
        "project": os.environ.get("EVAL_LLM_PROJECT", "").strip() or None,
        "location": os.environ.get("EVAL_LLM_LOCATION", "").strip() or None,
        "base_url": os.environ.get("EVAL_LLM_BASE_URL", "").strip() or None,
    }


def get_eval_adapter() -> ModelAdapter | None:
    config = load_llm_config()
    if config is None:
        return None
    try:
        adapter = get_adapter(
            name=config["provider"],
            model=config["model"],
            api_key=config["api_key"],
            base_url=config["base_url"],
            project=config["project"],
            location=config["location"],
        )
        logger.info("Created LLM adapter: provider=%s model=%s", config["provider"], config["model"] or "default")
        return adapter
    except ImportError:
        provider = config["provider"]
        hint = _INSTALL_HINTS.get(provider, f"Install the package for '{provider}'")
        logger.error("Missing dependency for LLM provider '%s'", provider)
        raise ImportError(
            f"Missing dependency for LLM provider '{provider}'. "
            f"Install it with: {hint}"
        )


def _resolve_config(cfg: dict) -> dict:
    resolved = {}
    for key, value in cfg.items():
        if key.endswith("_env") and isinstance(value, str):
            base_key = key[:-4]
            resolved[base_key] = os.environ.get(value, "").strip() or None
        else:
            resolved[key] = value
    return resolved


def load_multi_llm_configs() -> dict[str, dict] | None:
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
        return data.get("default")
    except Exception:
        return None


def get_available_llm_configs() -> dict:
    result: dict[str, dict] = {}
    multi = load_multi_llm_configs()
    if multi:
        for name, cfg in multi.items():
            result[name] = {
                "provider": cfg.get("provider", ""),
                "model": cfg.get("model", ""),
                "has_credentials": bool(cfg.get("api_key") or cfg.get("project")),
            }
    env_config = load_llm_config()
    if env_config and "env" not in result:
        result["env"] = {
            "provider": env_config["provider"],
            "model": env_config.get("model") or "default",
            "has_credentials": True,
            "source": "environment",
        }
    return result


def get_adapter_for_config(config_name: str) -> ModelAdapter:
    if config_name == "env":
        adapter = get_eval_adapter()
        if not adapter:
            raise ValueError("No LLM configured via environment variables")
        return adapter
    multi = load_multi_llm_configs()
    if not multi or config_name not in multi:
        raise ValueError(f"Unknown LLM config: '{config_name}'")
    cfg = multi[config_name]
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
    except ImportError:
        logger.error("Missing dependency for LLM config '%s' (provider=%s)", config_name, provider)
        raise ImportError(
            f"Missing dependency for LLM provider '{provider}'. "
            f"Install it with: {hint}"
        )
