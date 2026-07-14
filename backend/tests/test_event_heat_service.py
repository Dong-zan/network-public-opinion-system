import unittest
from datetime import datetime

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend_app.database import Base
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.services.event_heat_service import EventHeatService


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


class EventHeatServiceTests(unittest.TestCase):
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

    def _create_event(self, db) -> Event:
        event = Event(title="测试事件", heat=0)
        db.add(event)
        db.commit()
        db.refresh(event)
        return event

    def _add_news(
        self,
        db,
        event_id: int,
        heat_score: float | None,
        negative: float | None = 0,
        *,
        with_analysis: bool = True,
    ) -> Article:
        article = Article(
            event_id=event_id,
            title="事件新闻",
            content="事件新闻正文",
            created_at=datetime.now(),
        )
        db.add(article)
        db.flush()

        if with_analysis:
            db.add(
                Analysis(
                    news_id=article.news_id,
                    event_id=event_id,
                    heat_score=heat_score,
                    negative=negative,
                )
            )

        db.commit()
        return article

    def test_one_article_generates_event_heat(self):
        db = self.Session()
        event = self._create_event(db)
        self._add_news(db, event.event_id, heat_score=40, negative=0.2)

        heat = EventHeatService(db).update_event_heat(event.event_id)

        self.assertAlmostEqual(heat, 20.0)
        db.refresh(event)
        self.assertAlmostEqual(event.heat, 20.0)
        db.close()

    def test_low_heat_article_does_not_reduce_event_heat(self):
        db = self.Session()
        event = self._create_event(db)
        self._add_news(db, event.event_id, heat_score=21, negative=0)
        self._add_news(db, event.event_id, heat_score=21, negative=0)
        self._add_news(db, event.event_id, heat_score=20, negative=0)
        service = EventHeatService(db)
        initial_heat = service.update_event_heat(event.event_id)

        self._add_news(db, event.event_id, heat_score=1, negative=0)
        updated_heat = service.update_event_heat(event.event_id)

        self.assertGreaterEqual(updated_heat, initial_heat)
        db.close()

    def test_high_heat_article_increases_event_heat(self):
        db = self.Session()
        event = self._create_event(db)
        self._add_news(db, event.event_id, heat_score=10, negative=0)
        service = EventHeatService(db)
        initial_heat = service.update_event_heat(event.event_id)

        self._add_news(db, event.event_id, heat_score=100, negative=0)
        updated_heat = service.update_event_heat(event.event_id)

        self.assertGreater(updated_heat, initial_heat)
        db.close()

    def test_more_articles_increase_volume_component(self):
        db = self.Session()
        event = self._create_event(db)
        self._add_news(
            db,
            event.event_id,
            heat_score=None,
            with_analysis=False,
        )
        service = EventHeatService(db)
        one_article_heat = service.update_event_heat(event.event_id)

        self._add_news(
            db,
            event.event_id,
            heat_score=None,
            with_analysis=False,
        )
        two_article_heat = service.update_event_heat(event.event_id)

        self.assertAlmostEqual(one_article_heat, 6.0)
        self.assertAlmostEqual(two_article_heat, 12.0)
        self.assertGreater(two_article_heat, one_article_heat)
        db.close()

    def test_event_heat_is_limited_to_zero_and_one_hundred(self):
        db = self.Session()
        event = self._create_event(db)
        self._add_news(db, event.event_id, heat_score=1000, negative=10)
        heat = EventHeatService(db).update_event_heat(event.event_id)

        self.assertGreaterEqual(heat, 0)
        self.assertLessEqual(heat, 100)
        self.assertEqual(heat, 100)
        db.close()

    def test_event_without_analysis_does_not_fail(self):
        db = self.Session()
        event = self._create_event(db)
        self._add_news(
            db,
            event.event_id,
            heat_score=None,
            with_analysis=False,
        )

        heat = EventHeatService(db).update_event_heat(event.event_id)

        self.assertAlmostEqual(heat, 6.0)
        db.close()


if __name__ == "__main__":
    unittest.main()
