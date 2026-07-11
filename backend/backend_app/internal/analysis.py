from fastapi import APIRouter,Depends,HTTPException

from sqlalchemy.orm import Session


from backend_app.database import get_db

from backend_app.models.analysis import Analysis

from backend_app.models.article import Article

from backend_app.schemas.analysis import AnalysisCreate



router=APIRouter(

    prefix="/internal",

    tags=["内部-NLP分析"]

)




@router.post("/analysis")
def receive_analysis(

    data:AnalysisCreate,

    db:Session=Depends(get_db)

):


    article=db.query(Article)\
        .filter(
            Article.news_id==data.news_id
        )\
        .first()



    if not article:

        raise HTTPException(

            status_code=404,

            detail="news_id不存在"

        )



    sentiment=data.sentiment



    result=Analysis(

        news_id=data.news_id,


        keywords=data.keywords,


        positive=(
            sentiment.positive
            if sentiment else 0
        ),


        neutral=(
            sentiment.neutral
            if sentiment else 0
        ),


        negative=(
            sentiment.negative
            if sentiment else 0
        ),


        heat_score=data.heat_score,


        stage=data.stage,


        risk_level=data.risk_level,


        similar_news=data.similar_news

    )



    db.add(result)

    db.commit()

    db.refresh(result)



    return {


        "code":200,


        "message":"success",


        "data":{

            "analysis_id":result.id

        }

    }