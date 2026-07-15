from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session


from backend_app.database import get_db


from backend_app.services.ai_provider import AIProviderError
from backend_app.services.ai_service import AIResourceNotFoundError, AIService

from backend_app.models.ai_result import AIResult

from backend_app.schemas.ai import AIAsk, AIVerifyAPIResponse, AIVerifyRequest


router=APIRouter(

    prefix="/api/ai",

    tags=["AI分析"]

)




@router.post("/ask")
def ask_ai(

    data:AIAsk,

    db:Session=Depends(get_db)

):


    service=AIService(db)


    answer=service.ask(

        data.event_id,

        data.question

    )



    return {


        "code":200,

        "message":"success",

        "data":answer

    }





@router.post("/report/{event_id}")
def generate_report(

    event_id:int,

    db:Session=Depends(get_db)

):


    service=AIService(db)


    result=service.generate_report(

        event_id

    )


    return {


        "code":200,

        "message":"success",

        "data":{


            "event_id":
            result.event_id,


            "status":
            result.status

        }

    }

@router.get("/report/{event_id}")
def get_report(
    event_id:int,
    db:Session = Depends(get_db)
):

    result = (
        db.query(AIResult)
        .filter(
            AIResult.event_id == event_id
        )
        .first()
    )


    if not result:
        raise HTTPException(
            status_code=404,
            detail="AI report not found"
        )


    return {
        "code":200,
        "message":"success",
        "data":{
            "event_id":event_id,
            "report":result.ai_report
        }
    }

@router.post("/verify", response_model=AIVerifyAPIResponse)
def verify_article(

    data:AIVerifyRequest,

    db:Session=Depends(get_db)

):


    service = AIService(db)


    try:
        result = service.save_verify_result(

            data.event_id,

            data.news_id,

            data.max_claims

        )
    except (AIProviderError, AIResourceNotFoundError) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message
        ) from exc


    return {

        "code":200,

        "message":"success",

        "data":result

    }

@router.get(
    "/verify/{event_id}/{news_id}",
    response_model=AIVerifyAPIResponse,
)
def verify_news(
    event_id:int,
    news_id:int,
    db:Session = Depends(get_db)
):


    service = AIService(db)


    try:
        result = service.save_verify_result(
            event_id,
            news_id
        )
    except (AIProviderError, AIResourceNotFoundError) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message
        ) from exc


    return {

        "code":200,

        "message":"success",

        "data":result

    }
