import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from fastapi import HTTPException

from backend_app.models.ai_result import AIResult
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.models.event_heat_history import EventHeatHistory
from backend_app.routers.ai import ask_ai
from backend_app.schemas.ai import AIAsk
from backend_app.services.ai_provider import AIProviderError, RealAIProvider
from backend_app.services.ai_service import AIService


class AIProviderIntegrationTests(unittest.TestCase):
    @patch("backend_app.services.ai_provider.requests.post")
    def test_provider_reads_actual_ai_mode_from_response_header(self, post):
        response = Mock(
            ok=True,
            status_code=200,
            headers={"X-AI-Provider": "fake"},
        )
        response.json.return_value = {"answer": "测试回答"}
        post.return_value = response

        provider = RealAIProvider()

        self.assertEqual(provider.ask({"event": {}, "question": "测试"}), {"answer": "测试回答"})
        self.assertEqual(provider.provider_name, "fake")

    @patch("backend_app.services.ai_provider.requests.post")
    def test_provider_raises_safe_error_for_upstream_failure(self, post):
        response = Mock(
            ok=False,
            status_code=503,
            headers={"X-AI-Provider": "deepseek"},
        )
        response.json.return_value = {"detail": "AI 报告服务暂时不可用"}
        post.return_value = response

        with self.assertRaises(AIProviderError) as raised:
            RealAIProvider().report({"event": {}})

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(str(raised.exception), "AI 报告服务暂时不可用")

    @patch("backend_app.services.ai_provider.requests.post")
    def test_provider_maps_timeout_to_504(self, post):
        post.side_effect = requests.exceptions.Timeout("secret timeout detail")

        with self.assertRaises(AIProviderError) as raised:
            RealAIProvider().verify({"event": {}})

        self.assertEqual(raised.exception.status_code, 504)
        self.assertEqual(str(raised.exception), "AI service request timed out")

    @patch("backend_app.routers.ai.AIService")
    def test_backend_route_does_not_wrap_ai_failure_in_http_200(self, service_class):
        service_class.return_value.ask.side_effect = AIProviderError(
            "AI service is unavailable",
            503,
        )

        with self.assertRaises(HTTPException) as raised:
            ask_ai(
                AIAsk(event_id=1, question="事件风险是什么？"),
                object(),
            )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(raised.exception.detail, "AI service is unavailable")


class AIContextIntegrationTests(unittest.TestCase):
    def test_context_contains_ordered_event_heat_history(self):
        event = SimpleNamespace(
            event_id=7,
            title="测试事件",
            summary="测试摘要",
            update_time=datetime(2026, 7, 15, 12, 0),
            heat=72.5,
            stage="成长期",
            risk_level="中",
        )
        histories = [
            SimpleNamespace(
                id=1,
                event_id=7,
                heat=60.0,
                created_at=datetime(2026, 7, 15, 10, 0),
            ),
            SimpleNamespace(
                id=2,
                event_id=7,
                heat=72.5,
                created_at=datetime(2026, 7, 15, 11, 0),
            ),
        ]

        db = Mock()

        def query(model):
            query_mock = Mock()
            filtered = query_mock.filter.return_value
            if model is Event:
                filtered.first.return_value = event
            elif model is Article:
                filtered.all.return_value = []
            elif model is Analysis:
                filtered.all.return_value = []
            elif model is EventHeatHistory:
                filtered.order_by.return_value.all.return_value = histories
            else:
                self.fail(f"Unexpected model query: {model}")
            return query_mock

        db.query.side_effect = query

        context = AIService(db).build_context(7)

        self.assertEqual(
            context["event"]["analysis"]["history"],
            [
                {"time": "2026-07-15 10:00:00", "heat": 60.0},
                {"time": "2026-07-15 11:00:00", "heat": 72.5},
            ],
        )

    def test_report_persists_actual_provider_name(self):
        db = Mock()
        db.query.return_value.filter.return_value.first.return_value = None
        service = AIService(db)
        service.build_context = Mock(return_value={"event": {"articles": []}})
        service.provider = Mock(provider_name="fake")
        service.provider.report.return_value = {
            "overview": {},
            "summary": "摘要",
            "trend_analysis": "趋势",
            "risk_analysis": "风险",
            "suggestions": [],
            "limitations": [],
        }

        result = service.generate_report(7)

        self.assertIsInstance(result, AIResult)
        self.assertEqual(result.provider, "fake")


if __name__ == "__main__":
    unittest.main()
