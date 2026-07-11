from fastapi import APIRouter, Depends

from sqlalchemy.orm import Session

from datetime import datetime


from backend_app.database import get_db

from backend_app.models.article import Article

from backend_app.schemas.article import ArticleCreate



router=APIRouter(
    prefix="/internal",
    tags=["内部-新闻采集"]
)




@router.post("/articles")
def receive_article(

    data:ArticleCreate,

    db:Session=Depends(get_db)

):


    article=Article(

        title=data.title,

        content=data.content,

        source=data.source,

        url=data.url,


        platform=data.platform,


        author=data.author,


        account_id=data.account_id,


        account_name=data.account_name,


        account_type=data.account_type,


        is_official=data.is_official,


        repost_count=data.repost_count,


        comment_count=data.comment_count,


        like_count=data.like_count,


        crawl_time=datetime.now()

    )



    db.add(article)

    db.commit()

    db.refresh(article)



    return {

        "code":200,

        "message":"success",

        "data":{

            "news_id":article.news_id

        }

    }