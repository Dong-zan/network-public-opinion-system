from pydantic import BaseModel, ConfigDict, Field



class AIAsk(BaseModel):

    event_id:int=Field(
        gt=0
    )

    question:str=Field(
        min_length=1,
        max_length=2000
    )


class AIVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: int = Field(gt=0, strict=True)
    news_id: int = Field(gt=0, strict=True)
    max_claims: int = Field(default=5, ge=1, le=10, strict=True)
