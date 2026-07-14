from pydantic import BaseModel, Field

from typing import List, Optional



class Sentiment(BaseModel):

    positive: float = 0

    neutral: float = 0

    negative: float = 0



class AnalysisCreate(BaseModel):

    # 新闻编号
    news_id: int


    # 4号新增输出

    summary: str = ""


    processed_text: str = ""


    source: str = ""


    publish_time: Optional[str] = None


    url: str = ""


    missing_fields: List[str] = []



    # 原有分析字段

    keywords: List[str] = []


    sentiment: Optional[Sentiment] = None


    heat_score: float = 0


    stage: Optional[str] = None


    risk_level: Optional[str] = None


    similar_news: List[int] = []


    # 单新闻语义向量，由4号生成，供1号事件聚合使用

    embedding: List[float] = Field(min_length=768, max_length=768)
