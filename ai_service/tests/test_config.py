from pathlib import Path

from app.core.config import Settings, _load_environment


def _write_env(path: Path, *, provider: str) -> None:
    path.write_text(
        "\n".join(
            (
                f"AI_LLM_PROVIDER={provider}",
                "DEEPSEEK_API_KEY=test-only-placeholder",
            )
        ),
        encoding="utf-8",
    )


def test_settings_loads_deepseek_provider_from_dotenv(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    _write_env(env_path, provider="deepseek")
    monkeypatch.delenv("AI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    _load_environment(env_path)

    configured = Settings()
    assert configured.llm_provider == "deepseek"
    assert configured.deepseek_api_key == "test-only-placeholder"


def test_settings_defaults_to_fake_without_environment(monkeypatch) -> None:
    monkeypatch.delenv("AI_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    configured = Settings()

    assert configured.llm_provider == "fake"


def test_process_environment_overrides_dotenv(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    _write_env(env_path, provider="deepseek")
    monkeypatch.setenv("AI_LLM_PROVIDER", "fake")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    _load_environment(env_path)

    configured = Settings()
    assert configured.llm_provider == "fake"
