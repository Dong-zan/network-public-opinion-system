from sqlalchemy.orm import Session

from backend_app.models.article import Article



class StatisticService:



    def __init__(self,db:Session):

        self.db=db



    def timeline(
        self,
        event_id:int
    ):


        articles=self.db.query(
            Article
        ).filter(
            Article.event_id==event_id
        ).order_by(
            Article.publish_time.asc()
        ).all()



        result=[]



        for article in articles:


            result.append({

                "time":
                str(article.publish_time),


                "content":
                article.title,


                "news_id":
                article.news_id,


                "source":
                article.source

            })


        return result



    def platform_distribution(
        self,
        event_id:int
    ):


        articles=self.db.query(
            Article
        ).filter(
            Article.event_id==event_id
        ).all()



        counter={}



        for article in articles:


            name=(
                article.platform
                or article.source
                or "未知"
            )


            counter[name]=(
                counter.get(name,0)+1
            )



        return [

            {
                "name":k,

                "value":v
            }

            for k,v in counter.items()

        ]