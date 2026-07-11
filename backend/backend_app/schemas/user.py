from pydantic import BaseModel



class LoginRequest(BaseModel):

    username:str

    password:str




class PreferenceRequest(BaseModel):

    keywords:list=[]

    platforms:list=[]