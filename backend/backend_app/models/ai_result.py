from sqlalchemy import (
    Column,
    BigInteger,
    String,
    JSON,
    Text,
    DateTime
)

from datetime import datetime

from backend_app.database import Base



class AIResult(Base):

    __tablename__="ai_results"


    id=Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )


    event_id=Column(
        BigInteger
    )


    overview=Column(
        JSON
    )


    ai_report=Column(
        JSON
    )


    authenticity=Column(
        JSON
    )


    propagation_analysis=Column(
        JSON
    )


    propagation_path=Column(
        JSON
    )


    generated_at=Column(
        DateTime,
        default=datetime.utcnow
    )


    provider=Column(
        String(50)
    )


    status=Column(
        String(20)
    )


    error_message=Column(
        Text
    )