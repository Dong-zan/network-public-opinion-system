"""Create deterministic end-to-end data for event trend API checks."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import inspect


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from backend_app.database import Base, SessionLocal, engine
from backend_app.models.ai_result import AIResult
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event


HOURLY_EVENT_TITLE = "[E2E] 小时报道量趋势测试事件"
DAILY_EVENT_TITLE = "[E2E] 天报道量趋势测试事件"


def model_instance(model: type[Any], values: dict[str, Any]) -> Any:
    """Apply scalar ORM defaults and reject missing non-null model columns."""

    completed = dict(values)
    missing: list[str] = []

    for column in inspect(model).columns:
        if column.key in completed:
            continue

        if column.default is not None and column.default.is_scalar:
            completed[column.key] = column.default.arg
            continue

        auto_primary_key = column.primary_key and column.autoincrement in (
            True,
            "auto",
        )

        if auto_primary_key or column.nullable or column.server_default is not None:
            continue

        missing.append(column.key)

    if missing:
        raise ValueError(
            f"{model.__name__} 缺少 ORM 必填字段: {', '.join(missing)}"
        )

    return model(**completed)


def remove_previous_seed(db) -> None:
    event_ids = [
        event_id
        for (event_id,) in db.query(Event.event_id).filter(
            Event.title.in_([HOURLY_EVENT_TITLE, DAILY_EVENT_TITLE])
        )
    ]

    if not event_ids:
        return

    db.query(AIResult).filter(AIResult.event_id.in_(event_ids)).delete(
        synchronize_session=False
    )
    db.query(Analysis).filter(Analysis.event_id.in_(event_ids)).delete(
        synchronize_session=False
    )
    db.query(Article).filter(Article.event_id.in_(event_ids)).delete(
        synchronize_session=False
    )
    db.query(Event).filter(Event.event_id.in_(event_ids)).delete(
        synchronize_session=False
    )
    db.commit()


def create_event_dataset(
    db,
    *,
    title: str,
    publish_times: list[datetime],
    seed_code: str,
) -> int:
    created_at = min(publish_times)
    updated_at = max(publish_times)

    event = model_instance(
        Event,
        {
            "title": title,
            "summary": "用于验证事件详情接口趋势数组的端到端测试事件。",
            "heat": 78.0,
            "risk_level": "中",
            "stage": "成长期",
            "create_time": created_at,
            "update_time": updated_at,
            "status": "active",
            "extra": {"seed": seed_code, "purpose": "trend-e2e"},
        },
    )
    db.add(event)
    db.flush()

    previous_news_ids: list[int] = []

    for index, publish_time in enumerate(publish_times, start=1):
        article = model_instance(
            Article,
            {
                "event_id": event.event_id,
                "title": f"{title} 第{index}篇报道",
                "content": f"这是{title}的第{index}篇端到端测试报道。",
                "source": f"测试媒体{index}",
                "url": f"https://example.test/{seed_code}/article-{index}",
                "publish_time": publish_time,
                "platform": "新闻网站" if index % 2 else "微博",
                "author": f"测试作者{index}",
                "account_id": f"{seed_code}-account-{index}",
                "account_name": f"测试账号{index}",
                "account_type": "媒体",
                "is_official": index == 1,
                "crawl_time": publish_time,
                "repost_count": index * 10,
                "comment_count": index * 5,
                "like_count": index * 20,
                "reference_urls": [],
                "quoted_news_ids": [],
                "parent_news_id": None,
                "duplicate_group_id": f"{seed_code}-group-{index}",
                "created_at": publish_time,
            },
        )
        db.add(article)
        db.flush()

        analysis = model_instance(
            Analysis,
            {
                "news_id": article.news_id,
                "event_id": event.event_id,
                "summary": f"第{index}篇测试报道摘要",
                "processed_text": f"{title} 测试报道 {index}",
                "source": article.source,
                "publish_time": publish_time.strftime("%Y-%m-%d %H:%M:%S"),
                "url": article.url,
                "missing_fields": [],
                "keywords": ["趋势测试", "网络舆情", seed_code],
                "positive": 0.2,
                "neutral": 0.5,
                "negative": 0.3,
                "heat_score": 60.0 + index * 5,
                "stage": "成长期",
                "risk_level": "中",
                "similar_news": list(previous_news_ids),
                "created_at": publish_time,
            },
        )
        db.add(analysis)
        previous_news_ids.append(article.news_id)

    ai_result = model_instance(
        AIResult,
        {
            "event_id": event.event_id,
            "overview": {
                "time": f"{created_at:%Y-%m-%d} 至 {updated_at:%Y-%m-%d}",
                "location": "测试环境",
                "cause": "端到端接口验证",
                "persons": "测试人员",
            },
            "ai_report": {
                "summary": "测试事件报告摘要",
                "trend": "趋势解释应以接口返回的结构化趋势数据为准。",
                "risk": "当前为测试数据。",
                "suggestion": "仅用于端到端验证。",
                "generated_at": updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            },
            "authenticity": {
                "authenticity_label": "可信",
                "confidence": 1.0,
                "reason": "这是明确标记的测试数据。",
                "evidence": [],
                "warnings": [],
            },
            "propagation_analysis": {
                "origin": None,
                "key_nodes": [],
                "path": [],
                "confidence": 0.0,
                "limitations": ["测试数据不包含真实传播关系"],
            },
            "propagation_path": [],
            "generated_at": updated_at,
            "provider": "seed",
            "status": "success",
            "error_message": None,
        },
    )
    db.add(ai_result)
    db.commit()

    return int(event.event_id)


def main() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        remove_previous_seed(db)

        hourly_event_id = create_event_dataset(
            db,
            title=HOURLY_EVENT_TITLE,
            seed_code="hourly",
            publish_times=[
                datetime(2026, 7, 10, 8, 5),
                datetime(2026, 7, 10, 8, 35),
                datetime(2026, 7, 10, 9, 10),
                datetime(2026, 7, 10, 11, 0),
                datetime(2026, 7, 10, 12, 30),
            ],
        )

        daily_event_id = create_event_dataset(
            db,
            title=DAILY_EVENT_TITLE,
            seed_code="daily",
            publish_times=[
                datetime(2026, 7, 1, 8, 0),
                datetime(2026, 7, 1, 18, 0),
                datetime(2026, 7, 2, 9, 0),
                datetime(2026, 7, 4, 10, 0),
                datetime(2026, 7, 5, 8, 0),
            ],
        )

        print(
            json.dumps(
                {
                    "hourly_event_id": hourly_event_id,
                    "daily_event_id": daily_event_id,
                },
                ensure_ascii=False,
            )
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
