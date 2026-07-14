import unittest

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend_app.database import Base
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.services.aggregation_service import AggregationService


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


class EmbeddingAggregationTests(unittest.TestCase):
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

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        db = self.Session()
        db.query(Analysis).delete()
        db.query(Article).delete()
        db.query(Event).delete()
        db.commit()
        db.close()

    def test_similar_news_embeddings_reuse_the_same_event(self):
        db = self.Session()
        first_embedding = [1.0] + [0.0] * 767
        second_embedding = [0.99, 0.01] + [0.0] * 766

        first_article = Article(title="同一事件首篇", content="事件内容")
        second_article = Article(title="同一事件跟进", content="事件后续内容")
        db.add_all([first_article, second_article])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_article.news_id,
                    embedding=first_embedding,
                    similar_news=[],
                ),
                Analysis(
                    news_id=second_article.news_id,
                    embedding=second_embedding,
                    similar_news=[],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_article.news_id)
        second_event = service.aggregate_article(second_article.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_dissimilar_news_embeddings_create_different_events(self):
        db = self.Session()
        first_article = Article(title="事件甲", content="事件甲内容")
        second_article = Article(title="事件乙", content="事件乙内容")
        db.add_all([first_article, second_article])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_article.news_id,
                    embedding=[1.0] + [0.0] * 767,
                ),
                Analysis(
                    news_id=second_article.news_id,
                    embedding=[0.0, 1.0] + [0.0] * 766,
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_article.news_id)
        second_event = service.aggregate_article(second_article.news_id)

        self.assertNotEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 2)
        db.close()


if __name__ == "__main__":
    unittest.main()
