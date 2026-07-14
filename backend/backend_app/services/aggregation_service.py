from sqlalchemy.orm import Session

from backend_app.models.article import Article
from backend_app.models.analysis import Analysis
from backend_app.models.event import Event

from datetime import datetime



class AggregationService:


    def __init__(
        self,
        db: Session
    ):

        self.db = db



    def aggregate_article(
        self,
        news_id: int
    ):


        print(
            "========== 开始事件聚合 =========="
        )

        print(
            "news_id:",
            news_id
        )



        # =========================
        # 查询新闻
        # =========================

        article = self.db.query(
            Article
        ).filter(
            Article.news_id == news_id
        ).first()



        if not article:


            print(
                "没有找到文章:",
                news_id
            )


            return None



        print(
            "找到文章:",
            article.title
        )




        # =========================
        # 查询分析结果
        # =========================


        analysis = self.db.query(
            Analysis
        ).filter(
            Analysis.news_id == news_id
        ).first()



        if not analysis:


            print(
                "没有找到分析结果"
            )


            return None




        print(
            "分析结果:"
        )


        print(
            "risk_level:",
            analysis.risk_level
        )


        print(
            "heat_score:",
            analysis.heat_score
        )


        print(
            "similar_news:",
            analysis.similar_news
        )




        # =========================
        # 查找已有事件
        # =========================


        event = None



        if analysis.similar_news:


            print(
                "开始寻找相似事件"
            )


            for old_news_id in analysis.similar_news:



                old_article = self.db.query(
                    Article
                ).filter(
                    Article.news_id == old_news_id
                ).first()



                if old_article:


                    print(
                        "找到旧文章:",
                        old_news_id
                    )



                    if old_article.event_id:



                        print(
                            "旧文章已有event_id:",
                            old_article.event_id
                        )



                        event = self.db.query(
                            Event
                        ).filter(
                            Event.event_id == old_article.event_id
                        ).first()



                        if event:


                            print(
                                "复用已有事件:",
                                event.event_id
                            )


                            break




        else:


            print(
                "没有similar_news，准备创建新事件"
            )





        # =========================
        # 创建新事件
        # =========================


        if not event:



            print(
                "========== 创建新EVENT =========="
            )



            event = Event(


                title=article.title,



                summary=(

                    article.content[:200]

                    if article.content

                    else ""

                ),



                heat=(

                    analysis.heat_score

                    if analysis.heat_score

                    else 0

                ),



                risk_level=analysis.risk_level,



                stage=analysis.stage,



                create_time=datetime.now(),



                update_time=datetime.now()

            )



            self.db.add(event)



            self.db.commit()



            self.db.refresh(event)



            print(
                "EVENT CREATED:"
            )


            print(
                "event_id:",
                event.event_id
            )


            print(
                "title:",
                event.title
            )



        else:


            print(
                "使用已有event:",
                event.event_id
            )





        # =========================
        # 绑定事件
        # =========================


        article.event_id = event.event_id


        analysis.event_id = event.event_id



        self.db.commit()



        print(
            "文章绑定event完成"
        )


        print(
            "article.news_id:",
            article.news_id
        )


        print(
            "event_id:",
            event.event_id
        )



        print(
            "========== 事件聚合完成 =========="
        )



        return event