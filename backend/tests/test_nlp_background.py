import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import BackgroundTasks
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend_app.database import Base
from backend_app.internal.articles import (
    analyze_article_in_background,
    normalize_publish_time,
    receive_article,
)
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.models.event_heat_history import EventHeatHistory
from backend_app.schemas.article import ArticleCreate
from backend_app.services.nlp_client import NLPClient, NLPClientError


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


class NLPClientTests(unittest.TestCase):
    def setUp(self):
        self.article = SimpleNamespace(
            news_id=101,
            title="测试新闻",
            content="测试正文",
            source="测试来源",
            url="https://example.test/101",
            publish_time=datetime(2026, 7, 14, 10, 0),
            platform="测试平台",
            author="测试作者",
            account_id="account-101",
            account_name="测试账号",
            account_type="媒体",
            is_official=True,
            repost_count=10,
            comment_count=20,
            like_count=30,
        )

    @patch("backend_app.services.nlp_client.requests.post")
    def test_client_posts_article_and_validates_analysis(self, mock_post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "news_id": 101,
            "summary": "摘要",
            "processed_text": "处理后正文",
            "keywords": ["测试"],
            "sentiment": {
                "positive": 0.2,
                "neutral": 0.7,
                "negative": 0.1,
            },
            "heat_score": 65,
            "stage": "成长期",
            "risk_level": "中",
            "similar_news": [],
            "embedding": [1.0] + [0.0] * 767,
        }
        mock_post.return_value = response

        result = NLPClient(
            server_url="https://nlp.example.test/analyze"
        ).analyze(self.article)

        self.assertEqual(result.news_id, 101)
        self.assertEqual(result.summary, "摘要")
        self.assertEqual(len(result.embedding), 768)
        request_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(request_payload["news_id"], 101)
        self.assertEqual(request_payload["title"], "测试新闻")
        self.assertEqual(
            request_payload["publish_time"],
            "2026-07-14T10:00:00",
        )

    @patch("backend_app.services.nlp_client.requests.post")
    def test_client_rejects_mismatched_news_id(self, mock_post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"news_id": 999}
        mock_post.return_value = response

        with self.assertRaises(NLPClientError):
            NLPClient(
                server_url="https://nlp.example.test/analyze"
            ).analyze(self.article)


class NLPBackgroundTaskTests(unittest.TestCase):
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
                EventHeatHistory.__table__,
            ],
        )
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        db = self.Session()
        db.query(EventHeatHistory).delete()
        db.query(Analysis).delete()
        db.query(Article).delete()
        db.query(Event).delete()
        db.commit()
        db.close()

    def test_article_ingestion_schedules_background_task(self):
        db = self.Session()
        tasks = BackgroundTasks()

        response = receive_article(
            data=[ArticleCreate(title="待分析新闻", content="正文")],
            background_tasks=tasks,
            db=db,
        )

        db.close()

        self.assertEqual(response["code"], 200)
        self.assertEqual(len(response["data"]["news_ids"]), 1)
        self.assertEqual(len(tasks.tasks), 1)
        self.assertIs(
            tasks.tasks[0].func,
            analyze_article_in_background,
        )

    def test_backend_normalizes_valid_and_mojibake_publish_times(self):
        self.assertEqual(
            normalize_publish_time("2026-07-13 22:01:00"),
            datetime(2026, 7, 13, 22, 1),
        )
        self.assertIsNone(
            normalize_publish_time("2026е№ҙ07жңҲ13ж—Ҙ 22:01гҖҖ"),
        )

    def test_invalid_publish_time_does_not_fail_ingestion(self):
        db = self.Session()
        tasks = BackgroundTasks()

        response = receive_article(
            data=[
                ArticleCreate(
                    title="乱码时间新闻",
                    content="正文",
                    publish_time="2026е№ҙ07жңҲ13ж—Ҙ 22:01гҖҖ",
                ),
                ArticleCreate(
                    title="正常时间新闻",
                    content="正文",
                    publish_time="2026-07-13 22:01:00",
                ),
            ],
            background_tasks=tasks,
            db=db,
        )

        saved_articles = db.query(Article).order_by(Article.news_id).all()
        self.assertEqual(response["code"], 200)
        self.assertEqual(len(response["data"]["news_ids"]), 2)
        self.assertIsNone(saved_articles[0].publish_time)
        self.assertEqual(
            saved_articles[1].publish_time,
            datetime(2026, 7, 13, 22, 1),
        )
        self.assertEqual(len(tasks.tasks), 2)
        db.close()

    def test_one_article_failure_does_not_rollback_later_article(self):
        db = self.Session()
        tasks = BackgroundTasks()
        valid_article = Article(title="正常文章", content="正常正文")

        with patch(
            "backend_app.internal.articles.Article",
            side_effect=[ValueError("bad article"), valid_article],
        ):
            response = receive_article(
                data=[
                    ArticleCreate(title="坏文章", content="坏正文"),
                    ArticleCreate(title="正常文章", content="正常正文"),
                ],
                background_tasks=tasks,
                db=db,
            )

        self.assertEqual(response["code"], 200)
        self.assertEqual(len(response["data"]["news_ids"]), 1)
        self.assertEqual(db.query(Article).count(), 1)
        self.assertEqual(len(tasks.tasks), 1)
        db.close()

    @patch("backend_app.services.ai_service.AIService.try_generate_report")
    @patch("backend_app.internal.articles.NLPClient.analyze")
    @patch("backend_app.internal.articles.SessionLocal")
    def test_background_task_saves_analysis_and_assigns_event(
        self,
        mock_session_local,
        mock_analyze,
        mock_try_generate_report,
    ):
        db = self.Session()
        article = Article(title="自动分析新闻", content="自动分析正文")
        db.add(article)
        db.commit()
        news_id = article.news_id
        db.close()

        mock_session_local.side_effect = self.Session
        mock_analyze.return_value = {
            "news_id": news_id,
            "summary": "自动摘要",
            "processed_text": "处理后正文",
            "keywords": ["自动分析"],
            "sentiment": {
                "positive": 0.1,
                "neutral": 0.7,
                "negative": 0.2,
            },
            "heat_score": 70,
            "stage": "成长期",
            "risk_level": "中",
            "similar_news": [],
            "embedding": [1.0] + [0.0] * 767,
        }

        from backend_app.schemas.analysis import AnalysisCreate

        mock_analyze.return_value = AnalysisCreate.model_validate(
            mock_analyze.return_value
        )

        analyze_article_in_background(news_id)

        verify_db = self.Session()
        saved_article = verify_db.query(Article).filter(
            Article.news_id == news_id
        ).one()
        saved_analysis = verify_db.query(Analysis).filter(
            Analysis.news_id == news_id
        ).one()

        self.assertIsNotNone(saved_article.event_id)
        self.assertEqual(saved_analysis.event_id, saved_article.event_id)
        self.assertEqual(saved_analysis.summary, "自动摘要")
        self.assertEqual(len(saved_analysis.embedding), 768)
        mock_try_generate_report.assert_called_once_with(
            saved_article.event_id
        )
        verify_db.close()


if __name__ == "__main__":
    unittest.main()
