import unittest
from datetime import datetime, timedelta

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend_app.database import Base
from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.models.event_heat_history import EventHeatHistory
from backend_app.services.event_lifecycle_service import EventLifecycleService


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


class EventLifecycleServiceTests(unittest.TestCase):
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
        db.query(Article).delete()
        db.query(Event).delete()
        db.commit()
        db.close()

    def _create_event_with_history(self, db, heats: list[float]) -> Event:
        event = Event(title="生命周期测试事件", heat=heats[-1] if heats else 0)
        db.add(event)
        db.flush()

        start_time = datetime.now() - timedelta(minutes=len(heats))
        for index, heat in enumerate(heats):
            db.add(
                EventHeatHistory(
                    event_id=event.event_id,
                    heat=heat,
                    created_at=start_time + timedelta(minutes=index),
                )
            )

        db.commit()
        db.refresh(event)
        return event

    def test_rising_history_is_growth_stage(self):
        db = self.Session()
        event = self._create_event_with_history(db, [20, 40, 60])

        stage = EventLifecycleService(db).update_stage(event.event_id)

        self.assertEqual(stage, "成长期")
        db.refresh(event)
        self.assertEqual(event.stage, "成长期")
        db.close()

    def test_high_heat_is_climax_stage(self):
        db = self.Session()
        event = self._create_event_with_history(db, [60, 85, 90])

        stage = EventLifecycleService(db).calculate_stage(event.event_id)

        self.assertEqual(stage, "高潮期")
        db.close()

    def test_declining_history_is_decline_stage(self):
        db = self.Session()
        event = self._create_event_with_history(db, [90, 70, 40])

        stage = EventLifecycleService(db).calculate_stage(event.event_id)

        self.assertEqual(stage, "衰退期")
        db.close()

    def test_low_heat_without_trend_is_seed_stage(self):
        db = self.Session()
        event = self._create_event_with_history(db, [10, 10, 12])

        stage = EventLifecycleService(db).calculate_stage(event.event_id)

        self.assertEqual(stage, "萌芽期")
        db.close()

    def test_no_history_does_not_fail(self):
        db = self.Session()
        event = self._create_event_with_history(db, [])

        stage = EventLifecycleService(db).calculate_stage(event.event_id)

        self.assertEqual(stage, "萌芽期")
        db.close()


if __name__ == "__main__":
    unittest.main()
