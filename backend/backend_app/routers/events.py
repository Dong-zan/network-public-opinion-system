from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session


from backend_app.database import get_db


from backend_app.models.event import Event
from backend_app.models.article import Article
from backend_app.models.analysis import Analysis
from backend_app.models.ai_result import AIResult

from backend_app.services.statistic_service import StatisticService



router = APIRouter(

    prefix="/api/events",

    tags=["事件"]

)





@router.get("")
def get_events(

    sort:str="time",

    db:Session=Depends(get_db)

):


    query=db.query(Event)



    if sort=="heat":

        query=query.order_by(
            Event.heat.desc()
        )

    else:

        query=query.order_by(
            Event.create_time.desc()
        )



    events=query.all()



    data=[]



    for event in events:


        data.append({

            "event_id":
            event.event_id,


            "title":
            event.title,


            "summary":
            event.summary,


            "heat":
            event.heat,


            "risk_level":
            event.risk_level,


            "stage":
            event.stage,


            "create_time":
            event.create_time

        })



    return {


        "code":200,


        "message":"success",


        "data":data

    }






@router.get("/{event_id}")
def get_event_detail(

    event_id:int,

    db:Session=Depends(get_db)

):


    event=db.query(Event).filter(

        Event.event_id==event_id

    ).first()



    if not event:


        raise HTTPException(

            status_code=404,

            detail="事件不存在"

        )



    articles=db.query(
        Article
    ).filter(

        Article.event_id==event_id

    ).order_by(

        Article.publish_time.asc()

    ).all()



    analyses=db.query(
        Analysis
    ).filter(

        Analysis.event_id==event_id

    ).all()



    ai=db.query(
        AIResult
    ).filter(

        AIResult.event_id==event_id

    ).order_by(

        AIResult.generated_at.desc()

    ).first()



    statistic=StatisticService(db)



    # timeline

    timeline=statistic.timeline(
        event_id
    )



    # 平台分布

    platform_distribution=(

        statistic.platform_distribution(
            event_id
        )

    )



    # 发展趋势（按文章发布时间统计报道量）

    trend_data=statistic.trend(
        event_id
    )



    #关键词

    keywords=[]


    positive=0

    neutral=0

    negative=0



    for item in analyses:


        if item.keywords:

            keywords.extend(
                item.keywords
            )


        positive+=item.positive or 0

        neutral+=item.neutral or 0

        negative+=item.negative or 0




    count=len(analyses) or 1



    sentiment={

        "positive":
        round(
            positive/count,
            3
        ),


        "neutral":
        round(
            neutral/count,
            3
        ),


        "negative":
        round(
            negative/count,
            3
        )

    }





    return {


        "code":200,


        "message":"success",


        "data":{


            "event_id":
            event.event_id,


            "title":
            event.title,


            "summary":
            event.summary,


            "heat":
            event.heat,


            "risk_level":
            event.risk_level,


            "stage":
            event.stage,



            "overview":{


                "article_count":
                len(articles)

            },



            "timeline":
            timeline,



            "trend":
            trend_data["trend"],



            "trend_labels":
            trend_data["trend_labels"],



            "trend_highlights":
            trend_data["trend_highlights"],



            "keywords":
            list(set(keywords)),



            "sentiment":
            sentiment,



            "platform_distribution":
            platform_distribution,



            "ai_report":
            ai.ai_report
            if ai
            else {},



            "authenticity":
            ai.authenticity
            if ai
            else {},



            "propagation_analysis":
            ai.propagation_analysis
            if ai
            else {},



            "propagation_path":
            ai.propagation_path
            if ai
            else {}

        }

    }
