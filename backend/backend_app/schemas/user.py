from pydantic import BaseModel, Field



class RegisterRequest(BaseModel):

    username:str=Field(
        min_length=3,
        max_length=50
    )

    password:str=Field(
        min_length=6,
        max_length=128
    )

    nickname:str=Field(
        min_length=1,
        max_length=50
    )



class LoginRequest(BaseModel):

    username:str=Field(
        min_length=3,
        max_length=50
    )

    password:str=Field(
        min_length=6,
        max_length=128
    )




class PreferenceRequest(BaseModel):

    keywords:list=[]

    platforms:list=[]
