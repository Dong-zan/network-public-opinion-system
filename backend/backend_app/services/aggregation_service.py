from sqlalchemy.orm import Session

from backend_app.models.article import Article
from backend_app.models.analysis import Analysis
from backend_app.models.event import Event

from datetime import datetime



class AggregationService:



    def __init__(self, db:Session):

        self.db=db



    def aggregate_article(
            self,
            news_id:int
    ):


        article=self.db.query(
            Article
        ).filter(
            Article.news_id==news_id
        ).first()



        if not article:

            return None



        analysis=self.db.query(
            Analysis
        ).filter(
            Analysis.news_id==news_id
        ).first()



        if not analysis:

            return None



        # 查找已有相似事件

        event=None



        if analysis.similar_news:


            for old_news_id in analysis.similar_news:


                old_article=self.db.query(
                    Article
                ).filter(
                    Article.news_id==old_news_id
                ).first()



                if old_article and old_article.event_id:


                    event=self.db.query(
                        Event
                    ).filter(
                        Event.event_id==old_article.event_id
                    ).first()


                    break



        # 没找到则创建新事件

        if not event:


            event=Event(

                title=article.title,

                summary=article.content[:200]
                if article.content
                else "",


                heat=analysis.heat_score,


                risk_level=analysis.risk_level,


                stage=analysis.stage,


                create_time=datetime.now(),

                update_time=datetime.now()

            )


            self.db.add(event)

            self.db.commit()

            self.db.refresh(event)



        # 新闻绑定事件


        article.event_id=event.event_id


        self.db.commit()



        return event