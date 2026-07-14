from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from backend_app.database import get_db

from backend_app.models.analysis import Analysis
from backend_app.models.article import Article


router = APIRouter(
    prefix="/internal",
    tags=["内部-AI输入"]
)


@router.get("/analysis/pending")
def get_pending_analysis(
    db: Session = Depends(get_db)
):


    result = (
        db.query(
            Article,
            Analysis
        )
        .join(
            Analysis,
            Article.news_id == Analysis.news_id
        )
        .filter(
            Analysis.ai_generated == False
        )
        .all()
    )


    data = []


    for article, analysis in result:

        data.append({

            "news_id": article.news_id,

            "title": article.title,

            "content": article.content,

            "source": article.source,

            "url": article.url,


            "analysis": {

                "summary": analysis.summary,

                "keywords": analysis.keywords,

                "sentiment": {

                    "positive": analysis.positive,

                    "neutral": analysis.neutral,

                    "negative": analysis.negative

                },

                "heat_score": analysis.heat_score,

                "stage": analysis.stage,

                "risk_level": analysis.risk_level,

                "similar_news": analysis.similar_news

            }

        })


    return {

        "code":200,

        "message":"success",

        "data":data

    }