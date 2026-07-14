import unittest
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend_app.database import Base, get_db
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.routers.news import event_news_router, router


class NewsRouteTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            cls.engine,
            tables=[Event.__table__, Article.__table__, Analysis.__table__],
        )
        cls.Session = sessionmaker(bind=cls.engine)

        app = FastAPI()
        app.include_router(router)
        app.include_router(event_news_router)

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
        db.query(Analysis).delete()
        db.query(Article).delete()
        db.query(Event).delete()

        first_content = "第一篇新闻正文" * 40
        second_content = "第二篇新闻正文" * 40

        db.add_all(
            [
                Event(
                    event_id=10,
                    title="测试事件",
                    summary="测试事件摘要",
                    heat=76.0,
                ),
                Article(
                    news_id=1001,
                    event_id=10,
                    title="已有分析的新闻",
                    content=first_content,
                    source="测试媒体甲",
                    url="https://example.com/news/1001",
                    publish_time=datetime(2026, 7, 13, 10, 0),
                    platform="新闻网站",
                ),
                Article(
                    news_id=1002,
                    event_id=10,
                    title="尚未分析的新闻",
                    content=second_content,
                    source="测试媒体乙",
                    url="https://example.com/news/1002",
                    publish_time=datetime(2026, 7, 13, 11, 0),
                    platform="新闻客户端",
                ),
                Analysis(
                    id=2001,
                    news_id=1001,
                    event_id=10,
                    summary="NLP生成的新闻摘要",
                    heat_score=76.0,
                    risk_level="中",
                    stage="发酵期",
                ),
            ]
        )
        db.commit()
        db.close()

        self.first_content = first_content
        self.second_content = second_content

    def test_get_news_returns_articles_with_analysis(self):
        response = self.client.get("/api/news")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["code"], 200)
        self.assertEqual(len(body["data"]), 2)

        news_by_id = {
            item["news_id"]: item
            for item in body["data"]
        }
        analyzed = news_by_id[1001]

        self.assertEqual(analyzed["event_id"], 10)
        self.assertEqual(analyzed["summary"], "NLP生成的新闻摘要")
        self.assertEqual(analyzed["content"], self.first_content)
        self.assertEqual(analyzed["heat"], 76.0)
        self.assertEqual(analyzed["risk_level"], "中")
        self.assertEqual(analyzed["stage"], "发酵期")

    def test_get_news_falls_back_to_content_summary(self):
        response = self.client.get("/api/news")
        news_by_id = {
            item["news_id"]: item
            for item in response.json()["data"]
        }
        pending = news_by_id[1002]

        self.assertEqual(
            pending["summary"],
            self.second_content[:200],
        )
        self.assertIsNone(pending["heat"])
        self.assertIsNone(pending["risk_level"])
        self.assertIsNone(pending["stage"])

    def test_openapi_contains_news_route_and_response_fields(self):
        openapi = self.app.openapi()

        self.assertIn("/api/news", openapi["paths"])
        self.assertIn("/api/events/{event_id}/news", openapi["paths"])
        properties = openapi["components"]["schemas"]["NewsItem"]["properties"]
        self.assertEqual(
            set(properties),
            {
                "news_id",
                "event_id",
                "title",
                "source",
                "publish_time",
                "summary",
                "content",
                "url",
                "heat",
                "risk_level",
                "stage",
                "platform",
            },
        )

    def test_get_event_news_returns_only_event_articles(self):
        response = self.client.get("/api/events/10/news")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["code"], 200)
        self.assertEqual(len(body["data"]), 2)
        self.assertTrue(
            all(item["event_id"] == 10 for item in body["data"])
        )
        self.assertEqual(
            set(body["data"][0]),
            {
                "news_id",
                "event_id",
                "title",
                "source",
                "publish_time",
                "summary",
                "content",
                "url",
            },
        )

    def test_get_event_news_returns_404_for_unknown_event(self):
        response = self.client.get("/api/events/999/news")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "事件不存在")


if __name__ == "__main__":
    unittest.main()
