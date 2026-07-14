from sqlalchemy.orm import Session

from backend_app.models.event import Event
from backend_app.models.article import Article
from backend_app.models.analysis import Analysis



class EventService:


    def __init__(self, db: Session):

        self.db = db



    def get_events(
            self,
            sort="time"
    ):


        query = self.db.query(Event)


        if sort == "heat":

            query = query.order_by(
                Event.heat.desc()
            )

        else:

            query = query.order_by(
                Event.create_time.desc()
            )


        return query.all()





    def get_event_detail(
            self,
            event_id:int
    ):


        # 查询事件

        event = (
            self.db.query(Event)
            .filter(
                Event.event_id == event_id
            )
            .first()
        )


        if not event:

            return None



        # 查询该事件下新闻

        articles = (
            self.db.query(Article)
            .filter(
                Article.event_id == event_id
            )
            .all()
        )



        # ==========================
        # 查询分析结果
        #
        # 不依赖 Analysis.event_id
        # 通过 Article.news_id 关联
        # ==========================


        analysis = (
            self.db.query(Analysis)
            .join(
                Article,
                Analysis.news_id == Article.news_id
            )
            .filter(
                Article.event_id == event_id
            )
            .all()
        )



        # ==========================
        # 汇总关键词
        # ==========================

        keywords = []


        for item in analysis:

            if item.keywords:

                keywords.extend(
                    item.keywords
                )



        # ==========================
        # 汇总情感
        # ==========================

        sentiment = {

            "positive":0,

            "neutral":0,

            "negative":0

        }


        if analysis:

            count = len(analysis)


            sentiment["positive"] = round(
                sum(
                    item.positive or 0
                    for item in analysis
                )
                /
                count,
                2
            )


            sentiment["neutral"] = round(
                sum(
                    item.neutral or 0
                    for item in analysis
                )
                /
                count,
                2
            )


            sentiment["negative"] = round(
                sum(
                    item.negative or 0
                    for item in analysis
                )
                /
                count,
                2
            )



        # ==========================
        # 时间线
        # ==========================


        timeline=[]


        for article in articles:


            timeline.append({

                "time":
                    article.publish_time,


                "content":
                    article.title,


                "news_id":
                    article.news_id,


                "source":
                    article.source

            })



        # ==========================
        # 返回给前端
        # ==========================


        return {


            "event_id":
                event.event_id,


            "title":
                event.title,


            "summary":
                event.summary,


            "heat":
                event.heat,


            "risk_level":
                event.risk_level,


            "stage":
                event.stage,



            # 5号以后补充真实数据

            "overview":{


                "time":None,


                "location":None,


                "cause":None,


                "persons":None


            },



            "timeline":
                timeline,



            # 4号暂时没有趋势分析

            "trend":[],

            "trend_labels":[],

            "trend_highlights":[],


            "keywords":
                list(set(keywords)),


            "sentiment":
                sentiment,



            # 暂时统计平台

            "platform_distribution":[

            ],



            # 5号负责

            "authenticity":None,


            "propagation_analysis":None,


            "propagation_path":None,


            "ai_report":None


        }