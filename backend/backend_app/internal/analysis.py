from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session


from backend_app.database import get_db

from backend_app.models.analysis import Analysis

from backend_app.models.article import Article

from backend_app.schemas.analysis import AnalysisCreate

from backend_app.services.aggregation_service import AggregationService



router = APIRouter(

    prefix="/internal",

    tags=["内部-NLP分析"]

)




@router.post("/analysis")
def receive_analysis(

    data: AnalysisCreate,

    db: Session = Depends(get_db)

):


    print(
        "========== 收到分析结果 =========="
    )

    print(
        "news_id:",
        data.news_id
    )




    # =========================
    # 检查新闻是否存在
    # =========================


    article = db.query(
        Article
    ).filter(
        Article.news_id == data.news_id
    ).first()



    if not article:


        raise HTTPException(

            status_code=404,

            detail="news_id不存在"

        )



    print(
        "找到文章:",
        article.title
    )





    # =========================
    # 防止重复分析
    # =========================


    existing_analysis = db.query(
        Analysis
    ).filter(
        Analysis.news_id == data.news_id
    ).first()



    if existing_analysis:


        print(
            "========== 已存在分析结果 =========="
        )

        print(
            "analysis_id:",
            existing_analysis.id
        )

        print(
            "event_id:",
            existing_analysis.event_id
        )

        print(
            "================================="
        )


        return {


            "code": 200,


            "message": "already analyzed",


            "data": {


                "analysis_id":
                    existing_analysis.id,


                "event_id":
                    existing_analysis.event_id

            }

        }





    # =========================
    # 保存分析结果
    # =========================


    sentiment = data.sentiment



    result = Analysis(


        news_id=data.news_id,


        summary=data.summary,


        processed_text=data.processed_text,


        source=data.source,


        publish_time=data.publish_time,


        url=data.url,


        missing_fields=data.missing_fields,



        keywords=data.keywords,



        positive=(

            sentiment.positive

            if sentiment

            else 0

        ),



        neutral=(

            sentiment.neutral

            if sentiment

            else 0

        ),



        negative=(

            sentiment.negative

            if sentiment

            else 0

        ),



        heat_score=data.heat_score,


        stage=data.stage,


        risk_level=data.risk_level,


        similar_news=data.similar_news,


        embedding=data.embedding

    )




    db.add(result)


    db.commit()


    db.refresh(result)



    print(
        "分析结果保存成功"
    )


    print(
        "analysis_id:",
        result.id
    )





    # =========================
    # 自动事件聚合
    # =========================


    print(
        "========== 开始事件聚合 =========="
    )



    aggregation = AggregationService(db)



    print(
        "AggregationService 创建成功"
    )



    event = aggregation.aggregate_article(

        data.news_id

    )




    print(
        "========== 聚合返回 =========="
    )


    print(
        "event:",
        event
    )


    if event:

        print(
            "event_id:",
            event.event_id
        )


    else:

        print(
            "没有生成event"
        )


    print(
        "=============================="
    )





    # =========================
    # 自动判断是否生成AI报告
    # =========================


    if event:


        print(
            "========== 准备调用5号AI =========="
        )


        from backend_app.services.ai_service import AIService



        ai_service = AIService(db)



        ai_service.try_generate_report(

            event.event_id

        )


    else:


        print(
            "没有event，不调用AI"
        )





    # =========================
    # 返回结果
    # =========================


    return {


        "code": 200,


        "message": "success",


        "data": {


            "analysis_id":

                result.id,



            "event_id": (

                event.event_id

                if event

                else None

            )

        }

    }
