from fastapi import APIRouter,Depends,HTTPException

from sqlalchemy.exc import IntegrityError

from sqlalchemy.orm import Session


from backend_app.database import get_db

from backend_app.models.user import User

from backend_app.schemas.user import LoginRequest,RegisterRequest

from backend_app.core.security import hash_password,verify_password

from backend_app.utils.response import success



router=APIRouter(

    prefix="/api",

    tags=["登录"]

)



def user_data(user:User):


    return {

        "user_id":user.id,

        "username":user.username,

        "nickname":user.nickname

    }



@router.post("/register")
def register(

    data:RegisterRequest,

    db:Session=Depends(get_db)

):


    username=data.username.strip()

    nickname=data.nickname.strip()


    if not username:

        raise HTTPException(
            status_code=422,
            detail="用户名不能为空"
        )


    if not nickname:

        raise HTTPException(
            status_code=422,
            detail="昵称不能为空"
        )


    existing=db.query(
        User
    ).filter(
        User.username==username
    ).first()


    if existing:

        raise HTTPException(
            status_code=409,
            detail="用户名已存在"
        )


    user=User(
        username=username,
        nickname=nickname,
        password=hash_password(data.password),
        preferences={}
    )


    db.add(user)


    try:

        db.commit()

        db.refresh(user)

    except IntegrityError:

        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="用户名已存在"
        )


    return success(
        user_data(user),
        "register success"
    )



@router.post("/login")
def login(

    data:LoginRequest,

    db:Session=Depends(get_db)

):


    username=data.username.strip()


    user=db.query(
        User
    ).filter(
        User.username==username
    ).first()


    if not user or not verify_password(
        data.password,
        user.password
    ):

        raise HTTPException(
            status_code=401,
            detail="用户名或密码错误"
        )



    return success({

        "user_id":user.id,

        "username":user.username,

        "nickname":user.nickname

    },"login success")
