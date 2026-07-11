from pydantic import BaseModel

from typing import List,Optional



class Sentiment(BaseModel):

    positive:float=0

    neutral:float=0

    negative:float=0




class AnalysisCreate(BaseModel):


    news_id:int


    keywords:List[str]=[]


    sentiment:Optional[Sentiment]=None


    heat_score:float=0


    stage:Optional[str]=None


    risk_level:Optional[str]=None


    similar_news:List[int]=[]