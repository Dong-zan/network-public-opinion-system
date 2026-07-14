from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Float, String

from backend_app.database import Base


class EventHeatHistory(Base):
    __tablename__ = "event_heat_history"

    id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    event_id = Column(
        BigInteger,
        nullable=False,
    )

    heat = Column(
        Float,
        nullable=False,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )

    stage_snapshot = Column(
        String(20),
        nullable=True,
    )
