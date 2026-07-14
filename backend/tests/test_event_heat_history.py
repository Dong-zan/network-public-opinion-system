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
from backend_app.models.event_heat_history import EventHeatHistory
from backend_app.services.event_heat_service import EventHeatService


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


class EventHeatHistoryTests(unittest.TestCase):
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

    def _create_event_with_news(
        self,
        db,
        *,
        heat_score: float = 40,
    ) -> Event:
        event = Event(title="历史测试事件", heat=0)
        db.add(event)
        db.flush()

        article = Article(
            event_id=event.event_id,
            title="历史测试新闻",
            content="历史测试正文",
            created_at=datetime.now(),
        )
        db.add(article)
        db.flush()
        db.add(
            Analysis(
                news_id=article.news_id,
                event_id=event.event_id,
                heat_score=heat_score,
                negative=0.2,
            )
        )
        db.commit()
        db.refresh(event)
        return event

    def test_update_adds_one_history_record(self):
        db = self.Session()
        event = self._create_event_with_news(db)

        EventHeatService(db).update_event_heat(event.event_id)

        records = db.query(EventHeatHistory).filter(
            EventHeatHistory.event_id == event.event_id
        ).all()
        self.assertEqual(len(records), 1)
        self.assertIsNotNone(records[0].created_at)
        db.close()

    def test_two_updates_add_two_history_records(self):
        db = self.Session()
        event = self._create_event_with_news(db)
        service = EventHeatService(db)

        service.update_event_heat(event.event_id)
        service.update_event_heat(event.event_id)

        count = db.query(EventHeatHistory).filter(
            EventHeatHistory.event_id == event.event_id
        ).count()
        self.assertEqual(count, 2)
        db.close()

    def test_history_heat_matches_event_heat(self):
        db = self.Session()
        event = self._create_event_with_news(db)

        calculated_heat = EventHeatService(db).update_event_heat(
            event.event_id
        )

        db.refresh(event)
        history = db.query(EventHeatHistory).filter(
            EventHeatHistory.event_id == event.event_id
        ).one()
        self.assertAlmostEqual(history.heat, calculated_heat)
        self.assertAlmostEqual(history.heat, event.heat)
        db.close()

    def test_histories_are_isolated_by_event(self):
        db = self.Session()
        first_event = self._create_event_with_news(db, heat_score=20)
        second_event = self._create_event_with_news(db, heat_score=80)
        service = EventHeatService(db)

        service.update_event_heat(first_event.event_id)
        service.update_event_heat(second_event.event_id)

        first_records = db.query(EventHeatHistory).filter(
            EventHeatHistory.event_id == first_event.event_id
        ).all()
        second_records = db.query(EventHeatHistory).filter(
            EventHeatHistory.event_id == second_event.event_id
        ).all()
        self.assertEqual(len(first_records), 1)
        self.assertEqual(len(second_records), 1)
        self.assertNotEqual(first_records[0].event_id, second_records[0].event_id)
        db.close()


if __name__ == "__main__":
    unittest.main()
