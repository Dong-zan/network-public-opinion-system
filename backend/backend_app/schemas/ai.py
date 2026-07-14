from pydantic import BaseModel, Field



class AIAsk(BaseModel):

    event_id:int=Field(
        gt=0
    )

    question:str=Field(
        min_length=1,
        max_length=2000
    )
