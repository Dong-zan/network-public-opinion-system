from sqlalchemy.orm import Session


from backend_app.models.event import Event

from backend_app.models.article import Article

from backend_app.models.analysis import Analysis




class EventService:



    def __init__(self,db:Session):

        self.db=db



    def get_events(
        self,
        sort="time"
    ):


        query=self.db.query(Event)



        if sort=="heat":

            query=query.order_by(
                Event.heat.desc()
            )

        else:

            query=query.order_by(
                Event.create_time.desc()
            )



        return query.all()



    def get_event_detail(
            self,
            event_id:int
    ):


        event=self.db.query(
            Event
        ).filter(
            Event.event_id==event_id
        ).first()



        if not event:

            return None



        articles=self.db.query(
            Article
        ).filter(
            Article.event_id==event_id
        ).all()



        analysis=self.db.query(
            Analysis
        ).filter(
            Analysis.event_id==event_id
        ).all()



        keywords=[]

        for item in analysis:

            if item.keywords:

                keywords.extend(
                    item.keywords
                )



        return {


            "event_id":event.event_id,


            "title":event.title,


            "summary":event.summary,


            "heat":event.heat,


            "risk_level":event.risk_level,


            "stage":event.stage,


            "articles":articles,


            "keywords":list(set(keywords))

        }