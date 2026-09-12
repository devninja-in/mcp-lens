import os

import pytest

from src.app.eval.llm_config import load_llm_config, get_eval_adapter
from src.app.eval.model_adapter import MockAdapter


class TestLoadLlmConfig:
    def test_returns_none_when_not_set(self, monkeypatch):
        monkeypatch.delenv("EVAL_LLM_PROVIDER", raising=False)
        assert load_llm_config() is None

    def test_returns_none_for_empty_string(self, monkeypatch):
        monkeypatch.setenv("EVAL_LLM_PROVIDER", "  ")
        assert load_llm_config() is None

    def test_returns_config_for_openai(self, monkeypatch):
        monkeypatch.setenv("EVAL_LLM_PROVIDER", "openai")
        monkeypatch.setenv("EVAL_LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("EVAL_LLM_API_KEY", "sk-test123")
        monkeypatch.delenv("EVAL_LLM_PROJECT", raising=False)
        monkeypatch.delenv("EVAL_LLM_LOCATION", raising=False)
        monkeypatch.delenv("EVAL_LLM_BASE_URL", raising=False)

        config = load_llm_config()
        assert config is not None
        assert config["provider"] == "openai"
        assert config["model"] == "gpt-4o"
        assert config["api_key"] == "sk-test123"
        assert config["project"] is None
        assert config["location"] is None
        assert config["base_url"] is None

    def test_returns_config_for_vertexai(self, monkeypatch):
        monkeypatch.setenv("EVAL_LLM_PROVIDER", "vertexai")
        monkeypatch.setenv("EVAL_LLM_MODEL", "gemini-2.0-flash")
        monkeypatch.setenv("EVAL_LLM_PROJECT", "my-project")
        monkeypatch.setenv("EVAL_LLM_LOCATION", "europe-west1")
        monkeypatch.delenv("EVAL_LLM_API_KEY", raising=False)
        monkeypatch.delenv("EVAL_LLM_BASE_URL", raising=False)

        config = load_llm_config()
        assert config is not None
        assert config["provider"] == "vertexai"
        assert config["project"] == "my-project"
        assert config["location"] == "europe-west1"

    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("EVAL_LLM_PROVIDER", "  anthropic  ")
        monkeypatch.setenv("EVAL_LLM_MODEL", " claude-sonnet-4-20250514 ")
        monkeypatch.delenv("EVAL_LLM_API_KEY", raising=False)
        monkeypatch.delenv("EVAL_LLM_PROJECT", raising=False)
        monkeypatch.delenv("EVAL_LLM_LOCATION", raising=False)
        monkeypatch.delenv("EVAL_LLM_BASE_URL", raising=False)

        config = load_llm_config()
        assert config["provider"] == "anthropic"
        assert config["model"] == "claude-sonnet-4-20250514"

    def test_base_url_included(self, monkeypatch):
        monkeypatch.setenv("EVAL_LLM_PROVIDER", "openai")
        monkeypatch.setenv("EVAL_LLM_BASE_URL", "https://my-proxy.example.com/v1")
        monkeypatch.delenv("EVAL_LLM_MODEL", raising=False)
        monkeypatch.delenv("EVAL_LLM_API_KEY", raising=False)
        monkeypatch.delenv("EVAL_LLM_PROJECT", raising=False)
        monkeypatch.delenv("EVAL_LLM_LOCATION", raising=False)

        config = load_llm_config()
        assert config["base_url"] == "https://my-proxy.example.com/v1"


class TestGetEvalAdapter:
    def test_returns_none_when_not_configured(self, monkeypatch):
        monkeypatch.delenv("EVAL_LLM_PROVIDER", raising=False)
        assert get_eval_adapter() is None

    def test_returns_mock_adapter(self, monkeypatch):
        monkeypatch.setenv("EVAL_LLM_PROVIDER", "mock")
        monkeypatch.delenv("EVAL_LLM_MODEL", raising=False)
        monkeypatch.delenv("EVAL_LLM_API_KEY", raising=False)
        monkeypatch.delenv("EVAL_LLM_PROJECT", raising=False)
        monkeypatch.delenv("EVAL_LLM_LOCATION", raising=False)
        monkeypatch.delenv("EVAL_LLM_BASE_URL", raising=False)

        adapter = get_eval_adapter()
        assert isinstance(adapter, MockAdapter)

    def test_raises_for_unknown_provider(self, monkeypatch):
        monkeypatch.setenv("EVAL_LLM_PROVIDER", "nonexistent")
        monkeypatch.delenv("EVAL_LLM_MODEL", raising=False)
        monkeypatch.delenv("EVAL_LLM_API_KEY", raising=False)
        monkeypatch.delenv("EVAL_LLM_PROJECT", raising=False)
        monkeypatch.delenv("EVAL_LLM_LOCATION", raising=False)
        monkeypatch.delenv("EVAL_LLM_BASE_URL", raising=False)

        with pytest.raises(ValueError, match="Unknown adapter"):
            get_eval_adapter()

    def test_import_error_with_hint(self, monkeypatch):
        """Test get_eval_adapter ImportError handling with install hint."""
        monkeypatch.setenv("EVAL_LLM_PROVIDER", "openai")
        monkeypatch.delenv("EVAL_LLM_MODEL", raising=False)
        monkeypatch.delenv("EVAL_LLM_API_KEY", raising=False)
        monkeypatch.delenv("EVAL_LLM_PROJECT", raising=False)
        monkeypatch.delenv("EVAL_LLM_LOCATION", raising=False)
        monkeypatch.delenv("EVAL_LLM_BASE_URL", raising=False)

        def mock_get_adapter(*args, **kwargs):
            raise ImportError("No module named 'openai'")

        monkeypatch.setattr("src.app.eval.llm_config.get_adapter", mock_get_adapter)

        with pytest.raises(ImportError, match="uv sync --extra eval-openai"):
            get_eval_adapter()


class TestGetDefaultLlmName:
    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        """Test get_default_llm_name returns None when llm.json doesn't exist."""
        from src.app.eval.llm_config import get_default_llm_name
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")
        assert get_default_llm_name() is None

    def test_returns_none_on_corrupt_json(self, tmp_path, monkeypatch):
        """Test get_default_llm_name exception path with corrupt JSON."""
        from src.app.eval.llm_config import get_default_llm_name
        corrupt_file = tmp_path / "llm.json"
        corrupt_file.write_text("{invalid json")
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", corrupt_file)
        assert get_default_llm_name() is None

    def test_returns_default_name_successfully(self, tmp_path, monkeypatch):
        """Test get_default_llm_name returns default name from file."""
        from src.app.eval.llm_config import get_default_llm_name
        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"default": "my-default-llm"}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)
        assert get_default_llm_name() == "my-default-llm"


class TestGetAdapterForConfig:
    def test_import_error_for_config(self, tmp_path, monkeypatch):
        """Test get_adapter_for_config ImportError handling."""
        from src.app.eval.llm_config import get_adapter_for_config
        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"configs": {"test": {"provider": "anthropic", "model": "claude-3"}}}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)

        def mock_get_adapter(*args, **kwargs):
            raise ImportError("No module named 'anthropic'")

        monkeypatch.setattr("src.app.eval.llm_config.get_adapter", mock_get_adapter)

        with pytest.raises(ImportError, match="uv sync --extra eval-anthropic"):
            get_adapter_for_config("test")

    def test_env_adapter_success(self, monkeypatch):
        """Test get_adapter_for_config with env config."""
        from src.app.eval.llm_config import get_adapter_for_config
        monkeypatch.setenv("EVAL_LLM_PROVIDER", "mock")
        adapter = get_adapter_for_config("env")
        assert isinstance(adapter, MockAdapter)

    def test_env_adapter_not_configured(self, monkeypatch):
        """Test get_adapter_for_config raises when env not configured."""
        from src.app.eval.llm_config import get_adapter_for_config
        monkeypatch.delenv("EVAL_LLM_PROVIDER", raising=False)
        with pytest.raises(ValueError, match="No LLM configured via environment"):
            get_adapter_for_config("env")

    def test_unknown_config_name(self, tmp_path, monkeypatch):
        """Test get_adapter_for_config with unknown config name."""
        from src.app.eval.llm_config import get_adapter_for_config
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")
        with pytest.raises(ValueError, match="Unknown LLM config"):
            get_adapter_for_config("unknown")

    def test_successful_adapter_creation(self, tmp_path, monkeypatch):
        """Test get_adapter_for_config creates adapter successfully."""
        from src.app.eval.llm_config import get_adapter_for_config
        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"configs": {"test": {"provider": "mock", "model": "test-model"}}}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)

        adapter = get_adapter_for_config("test")
        assert isinstance(adapter, MockAdapter)


class TestLoadMultiLlmConfigs:
    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        """Test load_multi_llm_configs returns None when file doesn't exist."""
        from src.app.eval.llm_config import load_multi_llm_configs
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")
        assert load_multi_llm_configs() is None

    def test_loads_configs_successfully(self, tmp_path, monkeypatch):
        """Test load_multi_llm_configs loads configs from file."""
        from src.app.eval.llm_config import load_multi_llm_configs
        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"configs": {"test": {"provider": "openai", "model": "gpt-4"}}}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)

        configs = load_multi_llm_configs()
        assert configs is not None
        assert "test" in configs
        assert configs["test"]["provider"] == "openai"

    def test_resolves_env_vars(self, tmp_path, monkeypatch):
        """Test load_multi_llm_configs resolves environment variables."""
        from src.app.eval.llm_config import load_multi_llm_configs
        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"configs": {"test": {"provider": "openai", "api_key_env": "MY_API_KEY"}}}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)
        monkeypatch.setenv("MY_API_KEY", "sk-test123")

        configs = load_multi_llm_configs()
        assert configs is not None
        assert configs["test"]["api_key"] == "sk-test123"

    def test_returns_none_on_error(self, tmp_path, monkeypatch):
        """Test load_multi_llm_configs returns None on error."""
        from src.app.eval.llm_config import load_multi_llm_configs
        llm_file = tmp_path / "llm.json"
        llm_file.write_text("{invalid json")
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)

        assert load_multi_llm_configs() is None


class TestGetAvailableLlmConfigs:
    def test_returns_configs_from_file(self, tmp_path, monkeypatch):
        """Test get_available_llm_configs returns configs from file."""
        from src.app.eval.llm_config import get_available_llm_configs
        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"configs": {"test": {"provider": "openai", "model": "gpt-4", "api_key": "sk-test"}}}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)

        configs = get_available_llm_configs()
        assert "test" in configs
        assert configs["test"]["provider"] == "openai"
        assert configs["test"]["model"] == "gpt-4"
        assert configs["test"]["has_credentials"] is True

    def test_includes_env_config(self, tmp_path, monkeypatch):
        """Test get_available_llm_configs includes environment config."""
        from src.app.eval.llm_config import get_available_llm_configs
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")
        monkeypatch.setenv("EVAL_LLM_PROVIDER", "openai")
        monkeypatch.setenv("EVAL_LLM_MODEL", "gpt-4")

        configs = get_available_llm_configs()
        assert "env" in configs
        assert configs["env"]["provider"] == "openai"
        assert configs["env"]["source"] == "environment"
