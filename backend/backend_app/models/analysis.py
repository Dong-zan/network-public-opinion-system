from sqlalchemy import (
    Column,
    BigInteger,
    Float,
    String,
    JSON,
    DateTime
)

from datetime import datetime

from backend_app.database import Base



class Analysis(Base):

    __tablename__="analysis"


    id=Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )


    news_id=Column(
        BigInteger
    )


    event_id=Column(
        BigInteger
    )


    keywords=Column(
        JSON
    )


    positive=Column(
        Float
    )


    neutral=Column(
        Float
    )


    negative=Column(
        Float
    )


    heat_score=Column(
        Float
    )


    stage=Column(
        String(20)
    )


    risk_level=Column(
        String(20)
    )


    similar_news=Column(
        JSON
    )


    created_at=Column(
        DateTime,
        default=datetime.utcnow
    )