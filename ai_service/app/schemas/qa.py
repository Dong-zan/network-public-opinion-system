from pydantic import BaseModel

from app.schemas.event import EventContext


class AskRequest(BaseModel):
    event: EventContext
    question: str = ""


class AskResponse(BaseModel):
    answer: str
