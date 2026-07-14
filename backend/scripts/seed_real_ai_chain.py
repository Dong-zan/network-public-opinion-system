"""Create a fresh event fixture without AIResult for real AI-chain testing."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from backend_app.database import Base, SessionLocal, engine
from backend_app.models.ai_result import AIResult
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event


def main() -> None:
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    now = datetime.now().replace(microsecond=0)

    try:
        event = Event(
            title=f"[E2E-REAL-AI] 真实调用链测试 {now:%Y%m%d%H%M%S}",
            summary="用于验证后端到真实 AI 服务报告接口的完整调用链。",
            heat=72.0,
            risk_level="中",
            stage="成长期",
            create_time=now - timedelta(hours=2),
            update_time=now,
            status="active",
            extra={"purpose": "real-ai-chain-e2e"},
        )
        db.add(event)
        db.flush()

        for index in range(2):
            publish_time = now - timedelta(hours=1 - index)
            article = Article(
                event_id=event.event_id,
                title=f"真实 AI 调用链测试报道 {index + 1}",
                content=(
                    "这是用于测试 AI 报告生成链路的结构化测试内容，"
                    "不代表真实新闻事件。"
                ),
                source="端到端测试媒体",
                url=f"https://example.test/real-ai-chain/{event.event_id}/{index + 1}",
                publish_time=publish_time,
                platform="新闻网站",
                author="端到端测试",
                account_id=f"real-ai-test-{event.event_id}-{index + 1}",
                account_name="端到端测试账号",
                account_type="媒体",
                is_official=False,
                crawl_time=publish_time,
                repost_count=10 + index,
                comment_count=5 + index,
                like_count=20 + index,
                reference_urls=[],
                quoted_news_ids=[],
                parent_news_id=None,
                duplicate_group_id=f"real-ai-chain-{event.event_id}",
                created_at=publish_time,
            )
            db.add(article)
            db.flush()

            analysis = Analysis(
                news_id=article.news_id,
                event_id=event.event_id,
                summary=f"真实 AI 调用链测试分析摘要 {index + 1}",
                processed_text=article.content,
                source=article.source,
                publish_time=publish_time.strftime("%Y-%m-%d %H:%M:%S"),
                url=article.url,
                missing_fields=[],
                keywords=["真实AI调用链", "端到端测试"],
                positive=0.2,
                neutral=0.5,
                negative=0.3,
                heat_score=70.0 + index,
                stage="成长期",
                risk_level="中",
                similar_news=[],
                created_at=publish_time,
            )
            db.add(analysis)

        db.commit()

        ai_result_count = db.query(AIResult).filter(
            AIResult.event_id == event.event_id
        ).count()

        print(
            json.dumps(
                {
                    "event_id": int(event.event_id),
                    "article_count": 2,
                    "analysis_count": 2,
                    "ai_result_count_before_request": ai_result_count,
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
