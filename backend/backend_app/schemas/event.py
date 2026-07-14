from pydantic import BaseModel



class EventBase(BaseModel):

    event_id:int

    title:str|None

    summary:str|None

    heat:float

    risk_level:str|None

    stage:str|None
