import pytest

from src.app.eval.llm_config import get_adapter_for_config, load_llm_configs
from src.app.eval.model_adapter import MockAdapter


class TestLoadLlmConfigs:
    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")
        assert load_llm_configs() is None

    def test_loads_configs_successfully(self, tmp_path, monkeypatch):
        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"configs": {"test": {"provider": "openai", "model": "gpt-4"}}}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)

        configs = load_llm_configs()
        assert configs is not None
        assert "test" in configs
        assert configs["test"]["provider"] == "openai"

    def test_resolves_env_vars(self, tmp_path, monkeypatch):
        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"configs": {"test": {"provider": "openai", "api_key_env": "MY_API_KEY"}}}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)
        monkeypatch.setenv("MY_API_KEY", "sk-test123")

        configs = load_llm_configs()
        assert configs is not None
        assert configs["test"]["api_key"] == "sk-test123"

    def test_returns_none_on_error(self, tmp_path, monkeypatch):
        llm_file = tmp_path / "llm.json"
        llm_file.write_text("{invalid json")
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)

        assert load_llm_configs() is None


class TestGetDefaultLlmName:
    def test_returns_none_when_file_missing(self, tmp_path, monkeypatch):
        from src.app.eval.llm_config import get_default_llm_name

        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")
        assert get_default_llm_name() is None

    def test_returns_none_on_corrupt_json(self, tmp_path, monkeypatch):
        from src.app.eval.llm_config import get_default_llm_name

        corrupt_file = tmp_path / "llm.json"
        corrupt_file.write_text("{invalid json")
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", corrupt_file)
        assert get_default_llm_name() is None

    def test_returns_default_name_successfully(self, tmp_path, monkeypatch):
        from src.app.eval.llm_config import get_default_llm_name

        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"default": "my-default-llm"}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)
        assert get_default_llm_name() == "my-default-llm"


class TestGetAdapterForConfig:
    def test_import_error_for_config(self, tmp_path, monkeypatch):
        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"configs": {"test": {"provider": "anthropic", "model": "claude-3"}}}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)

        def mock_get_adapter(*args, **kwargs):
            raise ImportError("No module named 'anthropic'")

        monkeypatch.setattr("src.app.eval.llm_config.get_adapter", mock_get_adapter)

        with pytest.raises(ImportError, match="uv sync --extra eval-anthropic"):
            get_adapter_for_config("test")

    def test_unknown_config_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")
        with pytest.raises(ValueError, match="Unknown LLM config"):
            get_adapter_for_config("unknown")

    def test_successful_adapter_creation(self, tmp_path, monkeypatch):
        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"configs": {"test": {"provider": "mock", "model": "test-model"}}}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)

        adapter = get_adapter_for_config("test")
        assert isinstance(adapter, MockAdapter)


class TestGetAvailableLlmConfigs:
    def test_returns_configs_from_file(self, tmp_path, monkeypatch):
        from src.app.eval.llm_config import get_available_llm_configs

        llm_file = tmp_path / "llm.json"
        llm_file.write_text('{"configs": {"test": {"provider": "openai", "model": "gpt-4", "api_key": "sk-test"}}}')
        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", llm_file)

        configs = get_available_llm_configs()
        assert "test" in configs
        assert configs["test"]["provider"] == "openai"
        assert configs["test"]["model"] == "gpt-4"
        assert configs["test"]["has_credentials"] is True

    def test_returns_empty_when_no_file(self, tmp_path, monkeypatch):
        from src.app.eval.llm_config import get_available_llm_configs

        monkeypatch.setattr("src.app.eval.llm_config.LLM_CONFIG_PATH", tmp_path / "nonexistent.json")

        configs = get_available_llm_configs()
        assert configs == {}
