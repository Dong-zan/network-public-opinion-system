import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


AI_SERVICE_ROOT = Path(__file__).resolve().parents[2] / "ai_service"
if str(AI_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.llm.fake_provider import FakeLLMProvider  # noqa: E402
from app.main import app as ai_app  # noqa: E402
from app.services.verification_explanation import (  # noqa: E402
    VerificationExplanationService,
)
from app.services.verification_service import (  # noqa: E402
    VerificationService,
    get_verification_service,
)
from backend_app.database import Base, get_db  # noqa: E402
from backend_app.models.ai_result import AIResult  # noqa: E402
from backend_app.models.analysis import Analysis  # noqa: E402
from backend_app.models.article import Article  # noqa: E402
from backend_app.models.event import Event  # noqa: E402
from backend_app.routers.ai import router as backend_ai_router  # noqa: E402


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


class VerifyEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            cls.engine,
            tables=[
                Event.__table__,
                Article.__table__,
                Analysis.__table__,
                AIResult.__table__,
            ],
        )
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        db = self.Session()
        db.query(AIResult).delete()
        db.query(Analysis).delete()
        db.query(Article).delete()
        db.query(Event).delete()
        db.commit()
        db.close()

    def test_stored_news_to_backend_ai_to_frontend_contract(self):
        db = self.Session()
        event = Event(
            event_id=1,
            title="测试事件",
            summary="用于验证 Verify 接口链路。",
            update_time=datetime(2026, 7, 15, 10, 0),
        )
        article = Article(
            event_id=1,
            title="事故情况通报",
            content="事故造成2人受伤，相关人员正在接受治疗。",
            source="人民网",
            url="http://society.people.com.cn/n1/test.html",
            publish_time=datetime(2026, 7, 15, 9, 30),
            platform="新闻网站",
            author="记者甲",
            account_id="",
            account_name="人民网",
            account_type="媒体",
            is_official=True,
            crawl_time=datetime(2026, 7, 15, 9, 35),
            repost_count=1,
            comment_count=2,
            like_count=3,
            reference_urls=["https://source.example/notice"],
        )
        db.add_all([event, article])
        db.flush()
        news_id = article.news_id
        db.commit()
        db.close()

        backend_app = FastAPI()
        backend_app.include_router(backend_ai_router)

        def override_db():
            request_db = self.Session()
            try:
                yield request_db
            finally:
                request_db.close()

        backend_app.dependency_overrides[get_db] = override_db
        verification_service = VerificationService(
            explanation_service=VerificationExplanationService(
                FakeLLMProvider()
            )
        )
        ai_app.dependency_overrides[get_verification_service] = (
            lambda: verification_service
        )

        with TestClient(ai_app) as ai_client:
            def forward_to_ai(url, json, timeout):
                self.assertTrue(url.endswith("/ai/verify"))
                self.assertEqual(timeout, 60)
                self.assertEqual(json["event"]["event_id"], 1)
                self.assertEqual(json["target_news_id"], news_id)
                self.assertEqual(
                    json["event"]["articles"][0]["reference_urls"],
                    ["https://source.example/notice"],
                )
                return ai_client.post("/ai/verify", json=json)

            with patch(
                "backend_app.services.ai_provider.requests.post",
                side_effect=forward_to_ai,
            ):
                with TestClient(backend_app) as backend_client:
                    response = backend_client.post(
                        "/api/ai/verify",
                        json={
                            "event_id": 1,
                            "news_id": news_id,
                            "max_claims": 5,
                        },
                    )

        ai_app.dependency_overrides.clear()
        backend_app.dependency_overrides.clear()

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["code"], 200)
        self.assertEqual(payload["data"]["event_id"], 1)
        self.assertEqual(payload["data"]["news_id"], news_id)
        self.assertEqual(payload["data"]["target_news_id"], news_id)
        self.assertIn("overall_verdict", payload["data"])
        self.assertIsNotNone(payload["data"]["display_result"])

        db = self.Session()
        persisted = db.query(AIResult).filter(AIResult.event_id == 1).one()
        self.assertEqual(persisted.authenticity, payload["data"])
        db.close()


if __name__ == "__main__":
    unittest.main()
