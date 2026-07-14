from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Text,
    Integer,
    Boolean,
    DateTime,
    JSON
)

from datetime import datetime

from backend_app.database import Base



class Article(Base):

    __tablename__="articles"


    news_id=Column(
        BigInteger,
        primary_key=True,
        index=True
    )


    event_id=Column(
        BigInteger,
        nullable=True
    )


    title=Column(Text)

    content=Column(Text)


    source=Column(
        String(255)
    )


    url=Column(Text)


    publish_time=Column(
        DateTime
    )



    platform=Column(
        String(100)
    )


    author=Column(
        String(100)
    )


    account_id=Column(
        String(100)
    )


    account_name=Column(
        String(100)
    )


    account_type=Column(
        String(50)
    )


    is_official=Column(
        Boolean
    )



    crawl_time=Column(
        DateTime,
        default=datetime.utcnow
    )


    repost_count=Column(
        Integer,
        default=0
    )


    comment_count=Column(
        Integer,
        default=0
    )


    like_count=Column(
        Integer,
        default=0
    )


    reference_urls=Column(
        JSON
    )


    quoted_news_ids=Column(
        JSON
    )


    parent_news_id=Column(
        BigInteger
    )


    duplicate_group_id=Column(
        String(100)
    )


    created_at=Column(
        DateTime,
        default=datetime.utcnow
    )