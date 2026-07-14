from sqlalchemy import (
    Column,
    BigInteger,
    Float,
    String,
    JSON,
    DateTime,
    Text
)

from datetime import datetime

from backend_app.database import Base


class Analysis(Base):

    __tablename__ = "analysis"


    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )


    news_id = Column(
        BigInteger
    )


    event_id = Column(
        BigInteger
    )


    # ===== 4号新增输出 =====

    summary = Column(
        Text
    )


    processed_text = Column(
        Text
    )


    source = Column(
        String(100)
    )


    publish_time = Column(
        String(50)
    )


    url = Column(
        String(500)
    )


    missing_fields = Column(
        JSON
    )


    # ===== 原有分析结果 =====

    keywords = Column(
        JSON
    )


    positive = Column(
        Float
    )


    neutral = Column(
        Float
    )


    negative = Column(
        Float
    )


    heat_score = Column(
        Float
    )


    stage = Column(
        String(20)
    )


    risk_level = Column(
        String(20)
    )


    similar_news = Column(
        JSON
    )


    embedding = Column(
        JSON
    )


    created_at = Column(
        DateTime,
        default=datetime.utcnow
    )
