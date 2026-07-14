from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Text,
    Float,
    Integer,
    DateTime,
    JSON
)

from datetime import datetime

from backend_app.database import Base



class Event(Base):

    __tablename__="events"


    event_id=Column(
        BigInteger,
        primary_key=True
    )


    title=Column(
        String(255)
    )


    summary=Column(
        Text
    )


    heat=Column(
        Float,
        default=0
    )


    risk_level=Column(
        String(20)
    )


    stage=Column(
        String(20)
    )


    create_time=Column(
        DateTime,
        default=datetime.utcnow
    )


    update_time=Column(
        DateTime,
        default=datetime.utcnow
    )


    status=Column(
        String(20),
        default="active"
    )


    extra=Column(
        JSON
    )


    embedding=Column(
        JSON
    )


    embedding_count=Column(
        Integer,
        nullable=False,
        default=1,
        server_default="1"
    )
