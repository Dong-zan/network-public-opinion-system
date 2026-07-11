from pydantic import BaseModel



class AIAsk(BaseModel):

    event_id:int

    question:str