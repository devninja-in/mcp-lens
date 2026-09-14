"""Tests for multi-LLM configuration loading and adapter creation."""

import json

import pytest

from src.app.eval.llm_config import (
    _resolve_config,
    get_adapter_for_config,
    get_available_llm_configs,
    get_default_llm_name,
    load_llm_configs,
)
from src.app.eval.model_adapter import MockAdapter


class TestResolveConfig:
    def test_resolves_env_suffix_keys(self, monkeypatch):
        monkeypatch.setenv("MY_API_KEY", "sk-secret-123")
        cfg = {"provider": "openai", "model": "gpt-4o", "api_key_env": "MY_API_KEY"}
        resolved = _resolve_config(cfg)
        assert resolved["api_key"] == "sk-secret-123"
        assert resolved["provider"] == "openai"
        assert resolved["model"] == "gpt-4o"
        assert "api_key_env" not in resolved

    def test_missing_env_var_resolves_to_none(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_KEY", raising=False)
        cfg = {"api_key_env": "NONEXISTENT_KEY"}
        resolved = _resolve_config(cfg)
        assert resolved["api_key"] is None

    def test_empty_env_var_resolves_to_none(self, monkeypatch):
        monkeypatch.setenv("EMPTY_KEY", "   ")
        cfg = {"api_key_env": "EMPTY_KEY"}
        resolved = _resolve_config(cfg)
        assert resolved["api_key"] is None

    def test_non_env_keys_pass_through(self):
        cfg = {"provider": "mock", "model": "test-model"}
        resolved = _resolve_config(cfg)
        assert resolved == cfg

    def test_multiple_env_keys(self, monkeypatch):
        monkeypatch.setenv("MY_PROJECT", "proj-123")
        monkeypatch.setenv("MY_LOCATION", "us-central1")
        cfg = {"provider": "vertexai", "project_env": "MY_PROJECT", "location_env": "MY_LOCATION"}
        resolved = _resolve_config(cfg)
        assert resolved["project"] == "proj-123"
        assert resolved["location"] == "us-central1"
        assert resolved["provider"] == "vertexai"


class TestLoadLlmConfigs:
    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")
        result = load_llm_configs()
        assert result is None

    def test_loads_and_resolves_configs(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "sk-test")
        config_file = tmp_path / "llm.json"
        config_file.write_text(
            json.dumps(
                {
                    "configs": {
                        "gpt4o": {"provider": "openai", "model": "gpt-4o", "api_key_env": "TEST_API_KEY"},
                        "mock_llm": {"provider": "mock", "model": "test"},
                    },
                    "default": "gpt4o",
                }
            )
        )
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", config_file)
        result = load_llm_configs()
        assert result is not None
        assert "gpt4o" in result
        assert result["gpt4o"]["api_key"] == "sk-test"
        assert result["gpt4o"]["provider"] == "openai"
        assert "mock_llm" in result
        assert result["mock_llm"]["provider"] == "mock"

    def test_returns_none_on_invalid_json(self, tmp_path, monkeypatch):
        config_file = tmp_path / "llm.json"
        config_file.write_text("not valid json {{{")
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", config_file)
        result = load_llm_configs()
        assert result is None

    def test_empty_configs_section(self, tmp_path, monkeypatch):
        config_file = tmp_path / "llm.json"
        config_file.write_text(json.dumps({"configs": {}}))
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", config_file)
        result = load_llm_configs()
        assert result == {}


class TestGetDefaultLlmName:
    def test_returns_default_from_file(self, tmp_path, monkeypatch):
        config_file = tmp_path / "llm.json"
        config_file.write_text(json.dumps({"configs": {}, "default": "gpt4o"}))
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", config_file)
        assert get_default_llm_name() == "gpt4o"

    def test_returns_none_when_no_default(self, tmp_path, monkeypatch):
        config_file = tmp_path / "llm.json"
        config_file.write_text(json.dumps({"configs": {}}))
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", config_file)
        assert get_default_llm_name() is None

    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")
        assert get_default_llm_name() is None


class TestGetAvailableLlmConfigs:
    def test_returns_configs_from_llm_json(self, tmp_path, monkeypatch):
        config_file = tmp_path / "llm.json"
        config_file.write_text(
            json.dumps(
                {
                    "configs": {"mock_llm": {"provider": "mock", "model": "test"}},
                }
            )
        )
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", config_file)

        result = get_available_llm_configs()
        assert "mock_llm" in result

    def test_never_exposes_actual_keys(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "sk-very-secret")
        config_file = tmp_path / "llm.json"
        config_file.write_text(
            json.dumps(
                {
                    "configs": {"test": {"provider": "openai", "model": "gpt-4o", "api_key_env": "SECRET_KEY"}},
                }
            )
        )
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", config_file)

        result = get_available_llm_configs()
        assert "test" in result
        assert "api_key" not in result["test"]
        assert "sk-very-secret" not in str(result["test"])
        assert result["test"]["has_credentials"] is True

    def test_returns_empty_when_no_llm_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")

        result = get_available_llm_configs()
        assert result == {}


class TestGetAdapterForConfig:
    def test_named_config_creates_adapter(self, tmp_path, monkeypatch):
        config_file = tmp_path / "llm.json"
        config_file.write_text(
            json.dumps(
                {
                    "configs": {"mock_test": {"provider": "mock", "model": "test"}},
                }
            )
        )
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", config_file)

        adapter = get_adapter_for_config("mock_test")
        assert isinstance(adapter, MockAdapter)

    def test_unknown_config_raises(self, tmp_path, monkeypatch):
        config_file = tmp_path / "llm.json"
        config_file.write_text(json.dumps({"configs": {}}))
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", config_file)

        with pytest.raises(ValueError, match="Unknown LLM config"):
            get_adapter_for_config("nonexistent")

    def test_raises_when_no_llm_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")
        with pytest.raises(ValueError, match="Unknown LLM config"):
            get_adapter_for_config("some_config")
