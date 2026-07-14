from collections import Counter
from datetime import timedelta

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



    def trend(
        self,
        event_id:int
    ):


        articles=self.db.query(
            Article
        ).filter(
            Article.event_id==event_id,
            Article.publish_time.isnot(None)
        ).all()


        publish_times=sorted(
            article.publish_time
            for article in articles
            if article.publish_time is not None
        )


        if not publish_times:

            return {
                "trend":[],
                "trend_labels":[],
                "trend_highlights":[]
            }


        span=publish_times[-1]-publish_times[0]

        use_hour=span<=timedelta(hours=48)


        if use_hour:

            bucket=lambda value: value.replace(
                minute=0,
                second=0,
                microsecond=0
            )

            step=timedelta(hours=1)

            label_format="%m-%d %H:00"

        else:

            bucket=lambda value: value.replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0
            )

            step=timedelta(days=1)

            label_format="%m-%d"


        counts=Counter(
            bucket(value)
            for value in publish_times
        )


        current=bucket(publish_times[0])

        end=bucket(publish_times[-1])

        labels=[]

        values=[]


        while current<=end:

            labels.append(
                current.strftime(label_format)
            )

            values.append(
                counts.get(current,0)
            )

            current+=step


        return {
            "trend":values,
            "trend_labels":labels,
            "trend_highlights":self._trend_highlights(values)
        }



    @staticmethod
    def _trend_highlights(values):


        if not values:

            return []


        highlights={
            values.index(max(values)),
            len(values)-1
        }


        first_non_zero=next(
            (
                index
                for index,value in enumerate(values)
                if value!=0
            ),
            None
        )


        if first_non_zero is not None:

            highlights.add(first_non_zero)


        for index in range(1,len(values)):

            previous=values[index-1]

            current=values[index]


            if previous==0:

                if current!=0:

                    highlights.add(index)

                continue


            change=abs(current-previous)/abs(previous)


            if change>0.5:

                highlights.add(index)


        return sorted(highlights)
