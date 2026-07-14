import logging

from fastapi import APIRouter, BackgroundTasks, Depends

from sqlalchemy.orm import Session

from datetime import datetime

from backend_app.database import SessionLocal, get_db

from backend_app.models.article import Article

from backend_app.models.analysis import Analysis

from backend_app.schemas.article import ArticleCreate

from backend_app.services.nlp_client import NLPClient


logger = logging.getLogger(__name__)


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

    news_ids = []


    for item in data:

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

            publish_time=item.publish_time
        )


        db.add(article)

        db.flush()


        news_ids.append(article.news_id)



    db.commit()


    for news_id in news_ids:

        background_tasks.add_task(
            analyze_article_in_background,
            news_id,
        )


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
