import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend_app.database import Base
from backend_app.models.ai_result import AIResult
from backend_app.routers.ai import router, verify_article
from backend_app.schemas.ai import AIVerifyRequest
from backend_app.services.ai_provider import AIProviderError, RealAIProvider
from backend_app.services.ai_service import AIService


def complete_verify_result(event_id=25, news_id=1001):
    return {
        "event_id": event_id,
        "target_news_id": news_id,
        "overall_verdict": "insufficient_evidence",
        "evidence_score": 0,
        "score_type": "heuristic_evidence_score",
        "claim_results": [],
        "risk_flags": [],
        "limitations": [],
        "verifiable_claim_count": 0,
        "determinate_claim_count": 0,
        "verification_coverage": 0,
        "score_explanation": "当前证据强度为启发式评分。",
        "evidence_source_assessments": [],
        "credibility_assessment": None,
        "ai_explanation": None,
        "display_result": None,
    }


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


class AIVerifyContractTests(unittest.TestCase):
    def test_build_context_forwards_available_article_provenance(self):
        event = SimpleNamespace(
            event_id=25,
            title="测试事件",
            summary="测试摘要",
            update_time=datetime(2026, 7, 15, 10, 0),
            heat=80,
            stage="成长期",
            risk_level="中",
        )
        article = SimpleNamespace(
            news_id=1001,
            title="测试新闻",
            content="测试正文",
            source="测试媒体",
            url="https://media.example.test/news/1001",
            publish_time=datetime(2026, 7, 15, 9, 0),
            platform="新闻网站",
            author="记者甲",
            account_type="新闻媒体",
            is_official=True,
            reference_urls=["https://source.example.test/notice"],
            quoted_news_ids=[9001],
            duplicate_group_id="duplicate-1001",
        )

        event_query = Mock()
        event_query.filter.return_value.first.return_value = event
        article_query = Mock()
        article_query.filter.return_value.all.return_value = [article]
        analysis_query = Mock()
        analysis_query.filter.return_value.all.return_value = []
        db = Mock()
        db.query.side_effect = [
            event_query,
            article_query,
            analysis_query,
        ]

        context = AIService(db).build_context(25)
        forwarded = context["event"]["articles"][0]

        self.assertEqual(forwarded["author"], "记者甲")
        self.assertEqual(forwarded["account_type"], "新闻媒体")
        self.assertIs(forwarded["is_official"], True)
        self.assertEqual(
            forwarded["reference_urls"],
            ["https://source.example.test/notice"],
        )
        self.assertEqual(forwarded["quoted_news_ids"], [9001])
        self.assertEqual(
            forwarded["duplicate_group_id"],
            "duplicate-1001",
        )
        self.assertNotIn("source_type", forwarded)

    def test_openapi_exposes_strict_request_model(self):
        app = FastAPI()
        app.include_router(router)

        openapi = app.openapi()
        request_schema = (
            openapi["paths"]["/api/ai/verify"]["post"]
            ["requestBody"]["content"]["application/json"]["schema"]
        )
        model_schema = openapi["components"]["schemas"]["AIVerifyRequest"]
        response_schema = (
            openapi["paths"]["/api/ai/verify"]["post"]
            ["responses"]["200"]["content"]["application/json"]["schema"]
        )
        result_schema = openapi["components"]["schemas"]["AIVerifyResult"]

        self.assertEqual(
            request_schema["$ref"],
            "#/components/schemas/AIVerifyRequest",
        )
        self.assertEqual(
            set(model_schema["required"]),
            {"event_id", "news_id"},
        )
        self.assertFalse(model_schema["additionalProperties"])
        self.assertEqual(
            response_schema["$ref"],
            "#/components/schemas/AIVerifyAPIResponse",
        )
        self.assertTrue(
            {"event_id", "news_id", "target_news_id", "display_result"}
            <= set(result_schema["required"])
        )

    def test_model_rejects_invalid_values_and_unknown_fields(self):
        invalid_requests = [
            {"event_id": 0, "news_id": 1},
            {"event_id": 1, "news_id": 0},
            {"event_id": 1, "news_id": 1, "max_claims": 0},
            {"event_id": 1, "news_id": 1, "max_claims": 11},
            {"event_id": 1, "news_id": 1, "unknown": True},
        ]

        for payload in invalid_requests:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    AIVerifyRequest(**payload)

    def test_backend_normalizes_ids_and_validates_complete_ai_response(self):
        upstream = complete_verify_result()
        upstream.pop("event_id")

        result = AIService._normalize_verify_result(
            upstream,
            event_id=25,
            news_id=1001,
        )

        self.assertEqual(result["event_id"], 25)
        self.assertEqual(result["news_id"], 1001)
        self.assertEqual(result["target_news_id"], 1001)
        self.assertIn("display_result", result)

    def test_backend_rejects_mismatched_ai_response_ids(self):
        with self.assertRaises(AIProviderError) as caught:
            AIService._normalize_verify_result(
                complete_verify_result(event_id=99),
                event_id=25,
                news_id=1001,
            )

        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("mismatched event_id", caught.exception.message)

    def test_backend_rejects_incomplete_ai_response_before_persistence(self):
        incomplete = complete_verify_result()
        incomplete.pop("overall_verdict")

        with self.assertRaises(AIProviderError) as caught:
            AIService._normalize_verify_result(
                incomplete,
                event_id=25,
                news_id=1001,
            )

        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("incompatible", caught.exception.message)

    @patch("backend_app.routers.ai.AIService")
    def test_route_persists_and_returns_current_contract(self, service_class):
        result = {
            "overall_verdict": "conflicting",
            "evidence_score": 65,
            "score_type": "heuristic_evidence_score",
            "claim_results": [],
            "verification_coverage": 100,
        }
        service_class.return_value.save_verify_result.return_value = result
        db = object()

        response = verify_article(
            AIVerifyRequest(event_id=25, news_id=1001, max_claims=3),
            db,
        )

        service_class.assert_called_once_with(db)
        service_class.return_value.save_verify_result.assert_called_once_with(
            25,
            1001,
            3,
        )
        self.assertEqual(response["data"], result)

    @patch("backend_app.routers.ai.AIService")
    def test_route_preserves_provider_status(self, service_class):
        service_class.return_value.save_verify_result.side_effect = (
            AIProviderError(422, "max_claims超出范围")
        )

        with self.assertRaises(HTTPException) as caught:
            verify_article(
                AIVerifyRequest(event_id=25, news_id=1001),
                object(),
            )

        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.detail, "max_claims超出范围")

    @patch("backend_app.routers.ai.AIService")
    def test_http_route_validates_input_before_calling_service(self, service_class):
        app = FastAPI()
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post(
                "/api/ai/verify",
                json={"event_id": 25, "news_id": 1001, "max_claims": 11},
            )

        self.assertEqual(response.status_code, 422)
        service_class.assert_not_called()

    @patch("backend_app.routers.ai.AIService")
    def test_http_route_returns_503_for_provider_failure(self, service_class):
        service_class.return_value.save_verify_result.side_effect = (
            AIProviderError(503, "AI service is unavailable")
        )
        app = FastAPI()
        app.include_router(router)

        with TestClient(app) as client:
            response = client.post(
                "/api/ai/verify",
                json={"event_id": 25, "news_id": 1001},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "AI service is unavailable")


class RealAIProviderVerifyTests(unittest.TestCase):
    @patch("backend_app.services.ai_provider.requests.post")
    def test_verify_forwards_context_to_ai_service(self, post):
        context = {
            "event": {"event_id": 25, "articles": []},
            "target_news_id": 1001,
            "max_claims": 5,
        }
        expected = {
            "overall_verdict": "insufficient_evidence",
            "evidence_score": 0,
        }
        response = Mock(status_code=200)
        response.json.return_value = expected
        post.return_value = response

        result = RealAIProvider().verify(context)

        post.assert_called_once_with(
            f"{RealAIProvider.BASE_URL}/ai/verify",
            json=context,
            timeout=60,
        )
        self.assertEqual(result, expected)

    @patch("backend_app.services.ai_provider.requests.post")
    def test_verify_preserves_404_detail(self, post):
        response = Mock(status_code=404)
        response.json.return_value = {
            "detail": "待核验文章不在当前事件数据中"
        }
        post.return_value = response

        with self.assertRaises(AIProviderError) as caught:
            RealAIProvider().verify({})

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(
            caught.exception.message,
            "待核验文章不在当前事件数据中",
        )

    @patch("backend_app.services.ai_provider.requests.post")
    def test_verify_preserves_422_status(self, post):
        response = Mock(status_code=422)
        response.json.return_value = {"detail": "max_claims超出范围"}
        post.return_value = response

        with self.assertRaises(AIProviderError) as caught:
            RealAIProvider().verify({})

        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(caught.exception.message, "max_claims超出范围")

    @patch("backend_app.services.ai_provider.requests.post")
    def test_verify_maps_connection_failure_to_503(self, post):
        post.side_effect = requests.ConnectionError("connection refused")

        with self.assertRaises(AIProviderError) as caught:
            RealAIProvider().verify({})

        self.assertEqual(caught.exception.status_code, 503)

    @patch("backend_app.services.ai_provider.requests.post")
    def test_verify_maps_other_upstream_errors_to_503(self, post):
        response = Mock(status_code=500)
        response.json.return_value = {"detail": "internal error"}
        post.return_value = response

        with self.assertRaises(AIProviderError) as caught:
            RealAIProvider().verify({})

        self.assertEqual(caught.exception.status_code, 503)
        self.assertEqual(caught.exception.message, "AI service is unavailable")


class AIVerifyPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            cls.engine,
            tables=[AIResult.__table__],
        )
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        db = self.Session()
        db.query(AIResult).delete()
        db.commit()
        db.close()

    def test_successful_verification_is_persisted(self):
        expected = {
            "overall_verdict": "supported",
            "evidence_score": 88,
            "score_type": "heuristic_evidence_score",
        }
        db = self.Session()
        service = AIService(db)
        service.verify = Mock(return_value=expected)

        result = service.save_verify_result(25, 1001, 4)

        service.verify.assert_called_once_with(25, 1001, 4)
        self.assertEqual(result, expected)

        persisted = db.query(AIResult).filter(
            AIResult.event_id == 25
        ).one()
        self.assertEqual(persisted.authenticity, expected)
        self.assertEqual(persisted.status, "success")
        self.assertIsNone(persisted.error_message)
        db.close()

    def test_failed_verification_is_not_persisted(self):
        db = self.Session()
        service = AIService(db)
        service.verify = Mock(
            side_effect=AIProviderError(503, "AI service is unavailable")
        )

        with self.assertRaises(AIProviderError):
            service.save_verify_result(25, 1001)

        self.assertEqual(db.query(AIResult).count(), 0)
        db.close()


if __name__ == "__main__":
    unittest.main()
