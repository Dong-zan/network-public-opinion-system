from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend_app.database import get_db
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.schemas.news import EventNewsListResponse, NewsListResponse


router = APIRouter(
    prefix="/api/news",
    tags=["新闻"],
)

event_news_router = APIRouter(
    prefix="/api/events",
    tags=["新闻"],
)


@router.get("", response_model=NewsListResponse)
def get_news(db: Session = Depends(get_db)):
    rows = (
        db.query(Article, Analysis)
        .outerjoin(
            Analysis,
            Analysis.news_id == Article.news_id,
        )
        .order_by(
            Article.publish_time.desc(),
            Article.news_id.desc(),
        )
        .all()
    )

    data = []

    for article, analysis in rows:
        content = article.content or ""
        summary = (
            analysis.summary
            if analysis and analysis.summary
            else content[:200]
        )

        data.append(
            {
                "news_id": article.news_id,
                "event_id": article.event_id,
                "title": article.title,
                "source": article.source,
                "publish_time": article.publish_time,
                "summary": summary,
                "content": article.content,
                "url": article.url,
                "heat": analysis.heat_score if analysis else None,
                "risk_level": analysis.risk_level if analysis else None,
                "stage": analysis.stage if analysis else None,
                "platform": article.platform,
            }
        )

    return {
        "code": 200,
        "message": "success",
        "data": data,
    }


@event_news_router.get(
    "/{event_id}/news",
    response_model=EventNewsListResponse,
)
def get_event_news(
    event_id: int,
    db: Session = Depends(get_db),
):
    event = (
        db.query(Event)
        .filter(Event.event_id == event_id)
        .first()
    )

    if not event:
        raise HTTPException(
            status_code=404,
            detail="事件不存在",
        )

    articles = (
        db.query(Article)
        .filter(Article.event_id == event_id)
        .order_by(
            Article.publish_time.desc(),
            Article.news_id.desc(),
        )
        .all()
    )

    data = []

    for article in articles:
        content = article.content or ""
        data.append(
            {
                "news_id": article.news_id,
                "event_id": article.event_id,
                "title": article.title,
                "source": article.source,
                "publish_time": article.publish_time,
                "summary": content[:200],
                "content": article.content,
                "url": article.url,
            }
        )

    return {
        "code": 200,
        "message": "success",
        "data": data,
    }
