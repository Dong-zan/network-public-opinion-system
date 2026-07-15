import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend_app.database import Base, get_db
from backend_app.models.article_verification import ArticleVerification
from backend_app.routers.ai import router
from backend_app.services.ai_service import AIService


class AIVerifyContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            cls.engine,
            tables=[ArticleVerification.__table__],
        )
        cls.Session = sessionmaker(bind=cls.engine)

        app = FastAPI()
        app.include_router(router)

        def override_get_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.app = app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.engine.dispose()

    def setUp(self):
        db = self.Session()
        db.query(ArticleVerification).delete()
        db.commit()
        db.close()

    @staticmethod
    def _result(news_id, verdict="supported", score=80.0):
        return {
            "target_news_id": news_id,
            "overall_verdict": verdict,
            "evidence_score": score,
            "claim_results": [],
        }

    def test_openapi_exposes_verify_request_fields(self):
        openapi = self.app.openapi()
        request_schema = (
            openapi["paths"]["/api/ai/verify"]["post"]
            ["requestBody"]["content"]["application/json"]["schema"]
        )
        model_schema = openapi["components"]["schemas"]["AIVerifyRequest"]

        self.assertEqual(
            request_schema["$ref"],
            "#/components/schemas/AIVerifyRequest",
        )
        self.assertEqual(
            set(model_schema["required"]),
            {"event_id", "news_id"},
        )
        self.assertEqual(
            set(model_schema["properties"]),
            {"event_id", "news_id", "max_claims"},
        )

    def test_post_rejects_missing_and_invalid_fields_with_422(self):
        missing = self.client.post(
            "/api/ai/verify",
            json={"event_id": 1},
        )
        invalid = self.client.post(
            "/api/ai/verify",
            json={"event_id": "1", "news_id": 2, "max_claims": 5},
        )

        self.assertEqual(missing.status_code, 422)
        self.assertEqual(invalid.status_code, 422)

    @patch.object(AIService, "verify")
    def test_post_verify_success_persists_result(self, verify):
        verify.return_value = self._result(101)

        response = self.client.post(
            "/api/ai/verify",
            json={"event_id": 10, "news_id": 101, "max_claims": 4},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], self._result(101))
        verify.assert_called_once_with(10, 101, 4)

        db = self.Session()
        saved = db.query(ArticleVerification).one()
        self.assertEqual(saved.event_id, 10)
        self.assertEqual(saved.news_id, 101)
        self.assertEqual(saved.status, "success")
        self.assertEqual(saved.overall_verdict, "supported")
        self.assertEqual(saved.evidence_score, 80.0)
        self.assertEqual(saved.result_json, self._result(101))
        db.close()

    @patch.object(AIService, "verify", side_effect=AssertionError("GET called AI"))
    def test_get_reads_saved_result_without_calling_ai(self, verify):
        result = self._result(201, verdict="contradicted", score=75.0)
        db = self.Session()
        db.add(
            ArticleVerification(
                event_id=20,
                news_id=201,
                status="success",
                overall_verdict="contradicted",
                evidence_score=75.0,
                result_json=result,
                provider="fake",
            )
        )
        db.commit()
        db.close()

        response = self.client.get("/api/ai/verify/20/201")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], result)
        verify.assert_not_called()

    def test_get_missing_result_returns_404(self):
        response = self.client.get("/api/ai/verify/30/301")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["detail"],
            "Article verification not found",
        )

    @patch.object(AIService, "verify")
    def test_multiple_news_results_do_not_overwrite_each_other(self, verify):
        verify.side_effect = [
            self._result(401, verdict="supported", score=85.0),
            self._result(402, verdict="contradicted", score=70.0),
        ]

        first = self.client.post(
            "/api/ai/verify",
            json={"event_id": 40, "news_id": 401},
        )
        second = self.client.post(
            "/api/ai/verify",
            json={"event_id": 40, "news_id": 402},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        db = self.Session()
        saved = (
            db.query(ArticleVerification)
            .filter(ArticleVerification.event_id == 40)
            .order_by(ArticleVerification.news_id.asc())
            .all()
        )
        self.assertEqual([item.news_id for item in saved], [401, 402])
        self.assertEqual(
            [item.overall_verdict for item in saved],
            ["supported", "contradicted"],
        )
        db.close()


if __name__ == "__main__":
    unittest.main()
