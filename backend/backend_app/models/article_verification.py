from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    JSON,
    String,
)

from backend_app.database import Base


class ArticleVerification(Base):
    __tablename__ = "article_verifications"

    id = Column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    event_id = Column(BigInteger, nullable=False)
    news_id = Column(BigInteger, nullable=False)
    status = Column(String(20), nullable=False)
    overall_verdict = Column(String(50), nullable=False)
    evidence_score = Column(Float, nullable=False)
    result_json = Column(JSON, nullable=False)
    provider = Column(String(50), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    __table_args__ = (
        Index(
            "idx_article_verifications_event_news_created",
            "event_id",
            "news_id",
            "created_at",
        ),
    )
