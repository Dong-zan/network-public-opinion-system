import unittest
from datetime import datetime
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import MagicMock
import sys



class FakeColumn:


    def __eq__(self,value):

        return ("eq",value)


    def isnot(self,value):

        return ("isnot",value)



class FakeArticle:


    event_id=FakeColumn()

    publish_time=FakeColumn()



sqlalchemy_module=ModuleType("sqlalchemy")

sqlalchemy_orm_module=ModuleType("sqlalchemy.orm")

sqlalchemy_orm_module.Session=object

article_module=ModuleType("backend_app.models.article")

article_module.Article=FakeArticle

sys.modules.setdefault("sqlalchemy",sqlalchemy_module)

sys.modules.setdefault("sqlalchemy.orm",sqlalchemy_orm_module)

sys.modules.setdefault("backend_app.models.article",article_module)

from backend_app.services.statistic_service import StatisticService



def build_service(publish_times):

    articles=[
        SimpleNamespace(publish_time=publish_time)
        for publish_time in publish_times
    ]

    query=MagicMock()

    query.filter.return_value.all.return_value=articles

    db=MagicMock()

    db.query.return_value=query

    return StatisticService(db)



class StatisticServiceTrendTests(unittest.TestCase):


    def test_empty_articles_return_empty_arrays(self):

        result=build_service([]).trend(1)

        self.assertEqual(
            result,
            {
                "trend":[],
                "trend_labels":[],
                "trend_highlights":[]
            }
        )


    def test_span_within_48_hours_uses_hour_buckets(self):

        result=build_service([
            datetime(2026,7,8,10,5),
            datetime(2026,7,8,10,45),
            datetime(2026,7,8,12,10)
        ]).trend(1)

        self.assertEqual(
            result["trend_labels"],
            ["07-08 10:00","07-08 11:00","07-08 12:00"]
        )

        self.assertEqual(
            result["trend"],
            [2,0,1]
        )


    def test_span_over_48_hours_uses_day_buckets(self):

        result=build_service([
            datetime(2026,7,8,10,5),
            datetime(2026,7,8,20,30),
            datetime(2026,7,11,9,10)
        ]).trend(1)

        self.assertEqual(
            result["trend_labels"],
            ["07-08","07-09","07-10","07-11"]
        )

        self.assertEqual(
            result["trend"],
            [2,0,0,1]
        )


    def test_highlights_include_start_peak_latest_and_large_changes(self):

        self.assertEqual(
            StatisticService._trend_highlights([2,4,10,8,3]),
            [0,1,2,4]
        )



if __name__=="__main__":

    unittest.main()
