import json
import logging

import pytest

from app.llm.base import LLMProvider, LLMProviderUnavailableError
from app.llm.prompt_types import PromptBundle
from app.schemas.event import EventContext
from app.services.report_service import ReportGenerationError, ReportService


TEST_API_KEY = "test-api-key-must-not-appear"
FULL_ARTICLE_BODY = "FULL_ARTICLE_BODY_MUST_NOT_APPEAR_IN_LOGS"


def report_event() -> EventContext:
    return EventContext.model_validate(
        {
            "event_id": 90,
            "title": "测试事件",
            "summary": "测试摘要",
            "articles": [
                {
                    "news_id": 1,
                    "title": "测试报道一",
                    "content": FULL_ARTICLE_BODY,
                    "source": "来源甲",
                    "url": "https://example.com/1",
                    "publish_time": "2026-07-13 10:00:00",
                    "platform": "新闻网站",
                },
                {
                    "news_id": 2,
                    "title": "测试报道二",
                    "content": "第二篇完整测试报道。",
                    "source": "来源乙",
                    "url": "https://example.com/2",
                    "publish_time": "2026-07-13 10:10:00",
                    "platform": "新闻网站",
                },
                {
                    "news_id": 3,
                    "title": "测试报道三",
                    "content": "第三篇完整测试报道。",
                    "source": "来源丙",
                    "url": "https://example.com/3",
                    "publish_time": "2026-07-13 10:20:00",
                    "platform": "新闻网站",
                },
            ],
            "analysis": {"risk_level": "中"},
        }
    )


def valid_report() -> dict:
    return {
        "overview": {"time": None, "location": None, "cause": None, "persons": [], "summary": "测试概述。"},
        "summary": "测试总结。",
        "trend_analysis": "测试趋势分析。",
        "risk_analysis": "测试风险分析。",
        "suggestions": ["持续跟踪可信来源信息。", "核验关键信息。"],
        "limitations": ["测试限制。"],
    }


class FailingProvider(LLMProvider):
    name = "deepseek"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate(self, prompt: PromptBundle) -> str:
        del prompt
        raise self.error


class SequenceProvider(LLMProvider):
    name = "deepseek"

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls = 0

    def generate(self, prompt: PromptBundle) -> str:
        del prompt
        output = self.outputs[self.calls]
        self.calls += 1
        return output


@pytest.mark.parametrize(
    ("error", "category"),
    [(TimeoutError("timeout"), "provider_timeout"), (ConnectionError("connection"), "provider_connection")],
)
def test_provider_failures_are_safely_classified(caplog, error, category) -> None:
    caplog.set_level(logging.INFO, logger="app.services.report_service")
    service = ReportService(provider=FailingProvider(error))

    with pytest.raises(LLMProviderUnavailableError):
        service.generate(report_event())

    assert "report_provider_call_failed" in caplog.text
    assert f"diagnostic_category={category}" in caplog.text
    assert "selected_article_count=3" in caplog.text


def test_provider_http_status_is_logged_as_a_safe_category(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.services.report_service")
    error = LLMProviderUnavailableError("safe provider failure")
    error.diagnostic_category = "provider_http_status"
    error.provider_status_code = 503

    with pytest.raises(LLMProviderUnavailableError):
        ReportService(provider=FailingProvider(error)).generate(report_event())

    assert "diagnostic_category=provider_http_status" in caplog.text
    assert "provider_status_code=503" in caplog.text


def test_initial_json_failure_runs_repair_and_returns_report(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.services.report_service")
    provider = SequenceProvider(["not json", json.dumps(valid_report(), ensure_ascii=False)])

    report = ReportService(provider=provider).generate(report_event())

    assert report.summary == "测试总结。"
    assert provider.calls == 2
    assert "report_json_decode_failed" in caplog.text
    assert "phase=initial" in caplog.text
    assert "report_repair_started" in caplog.text
    assert "repair=True" in caplog.text


def test_repair_json_failure_is_logged_and_raises_safe_error(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.services.report_service")
    provider = SequenceProvider(["not json", "still not json"])

    with pytest.raises(ReportGenerationError):
        ReportService(provider=provider).generate(report_event())

    assert provider.calls == 2
    assert "phase=repair" in caplog.text
    assert "report_generation_failed" in caplog.text


def test_pydantic_validation_logs_field_paths_without_values(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.services.report_service")
    invalid = valid_report()
    invalid["suggestions"] = "不是数组"
    provider = SequenceProvider([json.dumps(invalid, ensure_ascii=False), json.dumps(valid_report(), ensure_ascii=False)])

    ReportService(provider=provider).generate(report_event())

    assert "report_schema_validation_failed" in caplog.text
    assert "suggestions" in caplog.text
    assert "list_type" in caplog.text
    assert "不是数组" not in caplog.text


def test_logs_exclude_api_key_and_full_article_body(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.services.report_service")
    service = ReportService(provider=FailingProvider(RuntimeError(TEST_API_KEY)))

    with pytest.raises(ReportGenerationError):
        service.generate(report_event())

    assert TEST_API_KEY not in caplog.text
    assert FULL_ARTICLE_BODY not in caplog.text
    assert "selected_article_content_lengths" in caplog.text


def test_successful_provider_call_logs_only_metadata_and_keeps_behavior(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.services.report_service")
    report = ReportService(provider=SequenceProvider([json.dumps(valid_report(), ensure_ascii=False)])).generate(report_event())

    assert report.summary == "测试总结。"
    assert "report_provider_call_succeeded" in caplog.text
    assert "raw_output_chars=" in caplog.text
    assert FULL_ARTICLE_BODY not in caplog.text
