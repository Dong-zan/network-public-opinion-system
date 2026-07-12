import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

from app.core.config import Settings
from app.llm.deepseek_provider import DeepSeekProvider
from app.llm.factory import create_llm_provider
from app.llm.fake_provider import FakeLLMProvider


AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]


def test_settings_import_and_creation() -> None:
    settings = Settings(llm_provider="fake")

    assert settings.llm_provider == "fake"
    assert settings.report_top_k == 5
    assert settings.report_article_max_chars == 1000


def test_report_settings_are_independent_from_qa(monkeypatch) -> None:
    monkeypatch.setenv("AI_QA_TOP_K", "2")
    monkeypatch.setenv("AI_REPORT_TOP_K", "7")
    monkeypatch.setenv("AI_ARTICLE_MAX_CHARS", "300")
    monkeypatch.setenv("AI_REPORT_ARTICLE_MAX_CHARS", "900")

    settings = Settings(llm_provider="fake")

    assert settings.qa_top_k == 2
    assert settings.report_top_k == 7
    assert settings.article_max_chars == 300
    assert settings.report_article_max_chars == 900


def test_fake_provider_creation_after_settings_import() -> None:
    provider = create_llm_provider("fake", config=Settings(llm_provider="fake"))

    assert isinstance(provider, FakeLLMProvider)


def test_deepseek_provider_creation_with_mock_client() -> None:
    settings = Settings(
        llm_provider="deepseek",
        deepseek_api_key="unit-test-placeholder",
    )

    provider = create_llm_provider("deepseek", config=settings, client=MagicMock())

    assert isinstance(provider, DeepSeekProvider)


def test_cold_import_settings_and_main_has_no_cycle() -> None:
    environment = os.environ.copy()
    environment["AI_LLM_PROVIDER"] = "fake"
    environment.pop("DEEPSEEK_API_KEY", None)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.core.config import Settings; "
                "assert Settings().llm_provider == 'fake'; "
                "import app.main"
            ),
        ],
        cwd=AI_SERVICE_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
