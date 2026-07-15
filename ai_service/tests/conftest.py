import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def event_payload() -> dict:
    return {
        "event_id": 1,
        "title": "某地发生事故并开展救援",
        "summary": "事故发生后，相关部门组织现场救援并发布情况通报。",
        "update_time": "2026-07-08 12:00:00",
        "articles": [
            {
                "news_id": 1001,
                "title": "人民网：救援工作正在进行",
                "content": "相关部门已组织救援，现场处置工作仍在进行。",
                "source": "人民网",
                "url": "https://example.com/news/1001",
                "publish_time": "2026-07-08 10:00:00",
                "platform": "新闻网站",
            }
        ],
        "analysis": {
            "keywords": ["事故", "救援"],
            "sentiment": {"positive": 0.2, "neutral": 0.3, "negative": 0.5},
            "heat": 85,
            "stage": "高潮期",
            "risk_level": "高",
        },
    }
