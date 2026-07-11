from fastapi import APIRouter,Depends

from sqlalchemy.orm import Session


from backend_app.database import get_db

from backend_app.models.user import User

from backend_app.schemas.user import PreferenceRequest



from backend_app.utils.response import success



router=APIRouter(

    prefix="/api/user",

    tags=["用户"]

)




@router.post("/preferences")
def save_preferences(

    data:PreferenceRequest,

    db:Session=Depends(get_db)

):


    user=db.query(
        User
    ).first()



    if not user:


        user=User(

            username="test",

            password="123456"

        )

        db.add(user)



    user.preferences={

        "keywords":
        data.keywords,


        "platforms":
        data.platforms

    }



    db.commit()



    return success({

        "preferences":
        user.preferences

    })