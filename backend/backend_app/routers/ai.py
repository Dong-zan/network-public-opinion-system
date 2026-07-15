from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session


from backend_app.database import get_db


from backend_app.services.ai_service import AIService
from backend_app.services.ai_provider import AIProviderError

from backend_app.models.ai_result import AIResult

from backend_app.schemas.ai import AIAsk, AIVerifyRequest


router=APIRouter(

    prefix="/api/ai",

    tags=["AI分析"]

)


def _raise_ai_http_error(exc: AIProviderError):
    raise HTTPException(
        status_code=exc.status_code,
        detail=str(exc),
    ) from exc




@router.post("/ask")
def ask_ai(

    data:AIAsk,

    db:Session=Depends(get_db)

):


    service=AIService(db)


    try:
        answer=service.ask(
            data.event_id,
            data.question
        )
    except AIProviderError as exc:
        _raise_ai_http_error(exc)



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


    try:
        result=service.generate_report(
            event_id
        )
    except AIProviderError as exc:
        _raise_ai_http_error(exc)


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

@router.post("/verify")
def verify_article(

    data:AIVerifyRequest,

    db:Session=Depends(get_db)

):


    service = AIService(db)


    try:
        verification = service.save_verify_result(
            data.event_id,
            data.news_id,
            data.max_claims,
        )
    except AIProviderError as exc:
        _raise_ai_http_error(exc)


    return {

        "code":200,

        "message":"success",

        "data":verification.result_json

    }

@router.get("/verify/{event_id}/{news_id}")
def verify_news(
    event_id:int,
    news_id:int,
    db:Session = Depends(get_db)
):


    service = AIService(db)


    verification = service.get_verify_result(
        event_id,
        news_id,
    )

    if not verification:
        raise HTTPException(
            status_code=404,
            detail="Article verification not found",
        )


    return {

        "code":200,

        "message":"success",

        "data":verification.result_json

    }
