from fastapi import APIRouter,Depends


from sqlalchemy.orm import Session


from backend_app.database import get_db


from backend_app.services.ai_service import AIService




router=APIRouter(

    prefix="/api/ai",

    tags=["AI分析"]

)




@router.post("/ask")
def ask_ai(

    data:dict,

    db:Session=Depends(get_db)

):


    service=AIService(db)


    answer=service.ask(

        data["event_id"],

        data["question"]

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