from fastapi import APIRouter



from backend_app.utils.response import success



router=APIRouter(

    prefix="/api",

    tags=["登录"]

)



@router.post("/login")
def login():



    return success({

        "token":
        "jwt-test-token"

    })