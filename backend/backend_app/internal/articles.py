import logging
import time

from fastapi import APIRouter, BackgroundTasks, Depends

from sqlalchemy.orm import Session

from datetime import datetime, timezone

from backend_app.database import SessionLocal, get_db

from backend_app.models.article import Article

from backend_app.models.analysis import Analysis

from backend_app.schemas.article import ArticleCreate

from backend_app.services.nlp_client import NLPClient


logger = logging.getLogger(__name__)


def normalize_publish_time(value) -> datetime | None:
    """将接口时间值转换为MySQL DATETIME；乱码或非法值降级为None。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
            for date_format in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y/%m/%d %H:%M:%S",
                "%Y/%m/%d %H:%M",
            ):
                try:
                    parsed = datetime.strptime(text, date_format)
                    break
                except ValueError:
                    continue
            if parsed is None:
                return None

    if not 1000 <= parsed.year <= 9999:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def analyze_article_in_background(news_id: int):
    db = SessionLocal()

    try:
        article = db.query(Article).filter(
            Article.news_id == news_id
        ).first()

        if not article:
            logger.warning(
                "Skip NLP analysis because article %s does not exist",
                news_id,
            )
            return

        existing_analysis = db.query(Analysis).filter(
            Analysis.news_id == news_id
        ).first()

        if existing_analysis:
            logger.info(
                "Skip NLP analysis because article %s is already analyzed",
                news_id,
            )
            return

        analysis_data = NLPClient().analyze(article)

        # Reuse the existing analysis persistence, aggregation and event binding.
        from backend_app.internal.analysis import receive_analysis

        receive_analysis(
            data=analysis_data,
            db=db,
        )
    except Exception:
        db.rollback()
        logger.exception(
            "Background NLP analysis failed for article %s",
            news_id,
        )
    finally:
        db.close()


router = APIRouter(
    prefix="/internal",
    tags=["内部-新闻采集"]
)


# ============================
# 3号爬虫 -> 1号后端
# 新闻采集接口
# ============================

@router.post("/articles")
def receive_article(

    data: list[ArticleCreate],

    background_tasks: BackgroundTasks,

    db: Session = Depends(get_db)

):

    request_started_at = time.perf_counter()

    def log_elapsed(step: str):
        elapsed_ms = (time.perf_counter() - request_started_at) * 1000
        logger.info(
            "[ARTICLE_DEBUG] step=%s elapsed=%.3f ms",
            step,
            elapsed_ms,
        )

    log_elapsed("request_enter")

    news_ids = []


    for index, item in enumerate(data):
        try:
            article = Article(
                title=item.title,
                content=item.content,
                source=item.source,
                url=item.url,
                platform=item.platform,
                author=item.author,
                account_id=item.account_id,
                account_name=item.account_name,
                account_type=item.account_type,
                is_official=item.is_official,
                repost_count=item.repost_count,
                comment_count=item.comment_count,
                like_count=item.like_count,
                crawl_time=datetime.now(),
                publish_time=normalize_publish_time(item.publish_time),
            )
            db.add(article)
            log_elapsed("db_add_after")
            log_elapsed("db_flush_start")
            db.flush()
            log_elapsed("db_flush_end")
            news_id = article.news_id
            log_elapsed("db_commit_start")
            db.commit()
            log_elapsed("db_commit_end")
            news_ids.append(news_id)
        except Exception as exc:
            db.rollback()
            logger.warning(
                "Skip invalid crawler article index=%s url=%r error=%s",
                index,
                item.url,
                exc,
            )


    for news_id in news_ids:

        background_tasks.add_task(
            analyze_article_in_background,
            news_id,
        )


    log_elapsed("before_return")

    return {

        "code": 200,

        "message": "success",

        "data": {

            "news_ids": news_ids

        }

    }



# ============================
# 4号分析 -> 1号后端
# 获取待分析新闻
# ============================

@router.get("/articles/pending")
def get_pending_articles(

    db: Session = Depends(get_db)

):

    articles = (

        db.query(Article)

        .outerjoin(

            Analysis,

            Article.news_id == Analysis.news_id

        )

        .filter(

            Analysis.news_id == None

        )

        .all()

    )


    return {

        "code": 200,

        "message": "success",

        "data": articles

    }
