from sqlalchemy.orm import Session

from datetime import datetime


from backend_app.models.event import Event

from backend_app.models.article import Article

from backend_app.models.analysis import Analysis

from backend_app.models.ai_result import AIResult



from backend_app.services.ai_provider import FakeAIProvider




class AIService:



    def __init__(self,db:Session):

        self.db=db

        self.provider=FakeAIProvider()




    def build_context(
        self,
        event_id:int
    ):


        event=self.db.query(
            Event
        ).filter(
            Event.event_id==event_id
        ).first()



        articles=self.db.query(
            Article
        ).filter(
            Article.event_id==event_id
        ).all()



        analyses=self.db.query(
            Analysis
        ).filter(
            Analysis.event_id==event_id
        ).all()



        return {


            "event":{


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


                "articles":[

                    {
                        "title":a.title,

                        "source":a.source

                    }

                    for a in articles

                ],


                "keywords":[

                k

                for item in analyses

                for k in (item.keywords or [])

                ]

            }

        }



    def ask(
        self,
        event_id:int,
        question:str
    ):


        context=self.build_context(
            event_id
        )


        context["question"]=question



        return self.provider.ask(
            context
        )




    def generate_report(
        self,
        event_id:int
    ):


        context=self.build_context(
            event_id
        )



        result=self.provider.ask(
            context
        )



        ai=self.db.query(
            AIResult
        ).filter(
            AIResult.event_id==event_id
        ).first()



        if not ai:


            ai=AIResult(

                event_id=event_id,

                generated_at=datetime.now(),

                provider="fake",

                status="success"

            )


            self.db.add(ai)



        ai.ai_report={

            "summary":
            result["summary"],


            "trend":
            result["trend"],


            "risk":
            result["risk"],


            "suggestion":
            result["suggestion"]

        }



        self.db.commit()


        return ai