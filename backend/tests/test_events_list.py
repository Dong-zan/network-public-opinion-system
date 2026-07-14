import unittest
from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend_app.database import Base, get_db
from backend_app.models.event import Event
from backend_app.routers.events import router


class EventListRouteTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            cls.engine,
            tables=[Event.__table__],
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
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.engine.dispose()

    def setUp(self):
        db = self.Session()
        db.query(Event).delete()
        db.add(
            Event(
                event_id=25,
                title="测试舆情事件",
                summary="原有事件摘要",
                heat=91.0,
                risk_level="高",
                stage="持续期",
                create_time=datetime(2026, 7, 10, 10, 0),
            )
        )
        db.commit()
        db.close()

    def test_events_remain_a_lightweight_event_list(self):
        response = self.client.get("/api/events")
        body = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(body["code"], 200)
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(
            set(body["data"][0]),
            {
                "event_id",
                "title",
                "summary",
                "heat",
                "risk_level",
                "stage",
                "create_time",
            },
        )


if __name__ == "__main__":
    unittest.main()
