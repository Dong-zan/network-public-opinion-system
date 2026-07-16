import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from math import sqrt
import time
from unittest.mock import patch

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend_app.database import Base
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event
from backend_app.models.event_heat_history import EventHeatHistory
from backend_app.services.aggregation_service import AggregationService


@compiles(BigInteger, "sqlite")
def compile_big_integer_as_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


class EmbeddingAggregationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            cls.engine,
            tables=[
                Event.__table__,
                Article.__table__,
                Analysis.__table__,
                EventHeatHistory.__table__,
            ],
        )
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        db = self.Session()
        db.query(EventHeatHistory).delete()
        db.query(Analysis).delete()
        db.query(Article).delete()
        db.query(Event).delete()
        db.commit()
        db.close()

    def test_first_news_creates_event_with_embedding_count_one(self):
        db = self.Session()
        embedding = [1.0] + [0.0] * 767
        article = Article(title="事件首篇", content="事件内容")
        db.add(article)
        db.flush()
        db.add(
            Analysis(
                news_id=article.news_id,
                embedding=embedding,
                keywords=["测试事件"],
                similar_news=[],
            )
        )
        db.commit()

        event = AggregationService(db).aggregate_article(article.news_id)

        self.assertEqual(event.embedding_count, 1)
        self.assertEqual(event.embedding, embedding)
        self.assertEqual(len(event.embedding), 768)
        db.close()

    def test_deepseek_financing_reports_from_different_media_merge(self):
        db = self.Session()
        first_embedding = [1.0] + [0.0] * 767
        second_embedding = [0.73, sqrt(1 - 0.73 ** 2)] + [0.0] * 766

        first_article = Article(
            title="DeepSeek完成新一轮融资",
            content="企业公布融资消息",
            source="财经日报",
        )
        second_article = Article(
            title="DeepSeek新一轮融资获多家机构参与",
            content="多家媒体跟进融资消息",
            source="科技新闻",
        )
        db.add_all([first_article, second_article])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_article.news_id,
                    embedding=first_embedding,
                    keywords=["DeepSeek", "融资"],
                    similar_news=[],
                ),
                Analysis(
                    news_id=second_article.news_id,
                    embedding=second_embedding,
                    keywords=["DeepSeek", "融资"],
                    similar_news=[],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_article.news_id)
        second_event = service.aggregate_article(second_article.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.refresh(second_event)
        self.assertEqual(second_event.embedding_count, 2)
        self.assertEqual(len(second_event.embedding), 768)
        self.assertAlmostEqual(
            sqrt(sum(value * value for value in second_event.embedding)),
            1.0,
        )

        expected_x = (1.0 + 0.73) / 2
        expected_y = sqrt(1 - 0.73 ** 2) / 2
        expected_norm = sqrt(expected_x ** 2 + expected_y ** 2)
        self.assertAlmostEqual(
            second_event.embedding[0],
            expected_x / expected_norm,
        )
        self.assertAlmostEqual(
            second_event.embedding[1],
            expected_y / expected_norm,
        )
        self.assertNotEqual(second_event.embedding, second_embedding)
        db.close()

    def test_dissimilar_news_embeddings_create_different_events(self):
        db = self.Session()
        first_article = Article(title="事件甲", content="事件甲内容")
        second_article = Article(title="事件乙", content="事件乙内容")
        db.add_all([first_article, second_article])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_article.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["事件"],
                ),
                Analysis(
                    news_id=second_article.news_id,
                    embedding=[0.0, 1.0] + [0.0] * 766,
                    keywords=["事件"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_article.news_id)
        second_event = service.aggregate_article(second_article.news_id)

        self.assertNotEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 2)
        db.close()

    def test_high_embedding_without_keyword_overlap_creates_new_event(self):
        db = self.Session()
        embedding = [1.0] + [0.0] * 767
        first_article = Article(title="影视事件", content="影视内容")
        second_article = Article(title="体育事件", content="体育内容")
        db.add_all([first_article, second_article])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_article.news_id,
                    embedding=embedding,
                    keywords=["暑期档"],
                ),
                Analysis(
                    news_id=second_article.news_id,
                    embedding=embedding,
                    keywords=["世界杯"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_article.news_id)
        second_event = service.aggregate_article(second_article.news_id)

        self.assertNotEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 2)
        db.close()

    def test_event_older_than_seven_days_still_matches_within_fourteen_days(self):
        db = self.Session()
        embedding = [1.0] + [0.0] * 767
        first_article = Article(title="#世界杯半决赛# 旧报道", content="旧事件内容")
        second_article = Article(title="#世界杯半决赛# 新进展", content="新报道内容")
        db.add_all([first_article, second_article])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_article.news_id,
                    embedding=embedding,
                    keywords=["世界杯", "半决赛"],
                ),
                Analysis(
                    news_id=second_article.news_id,
                    embedding=embedding,
                    keywords=["世界杯", "半决赛"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_article.news_id)
        old_time = datetime.now() - timedelta(days=7, minutes=1)
        first_event.create_time = old_time
        first_event.update_time = old_time
        db.commit()

        second_event = service.aggregate_article(second_article.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_event_older_than_fourteen_days_is_not_matched(self):
        db = self.Session()
        embedding = [1.0] + [0.0] * 767
        first_article = Article(title="#世界杯半决赛# 首篇", content="首篇")
        second_article = Article(title="#世界杯半决赛# 后续", content="后续")
        db.add_all([first_article, second_article])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_article.news_id,
                    embedding=embedding,
                    keywords=["世界杯", "半决赛"],
                ),
                Analysis(
                    news_id=second_article.news_id,
                    embedding=embedding,
                    keywords=["世界杯", "半决赛"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_article.news_id)
        old_time = datetime.now() - timedelta(days=14, minutes=1)
        first_event.create_time = old_time
        first_event.update_time = old_time
        db.commit()

        second_event = service.aggregate_article(second_article.news_id)

        self.assertNotEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 2)
        db.close()

    def test_later_create_time_keeps_event_active_when_update_time_is_older(self):
        db = self.Session()
        embedding = [1.0] + [0.0] * 767
        first_article = Article(title="世界杯英格兰对阵阿根廷首篇", content="比赛内容")
        second_article = Article(title="世界杯英格兰对阵阿根廷最新进展", content="比赛进展")
        db.add_all([first_article, second_article])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_article.news_id,
                    embedding=embedding,
                    keywords=["世界杯", "英格兰", "阿根廷"],
                ),
                Analysis(
                    news_id=second_article.news_id,
                    embedding=embedding,
                    keywords=["世界杯", "英格兰", "阿根廷"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_article.news_id)
        first_event.create_time = datetime.now() - timedelta(days=1)
        first_event.update_time = datetime.now() - timedelta(days=8)
        db.commit()

        second_event = service.aggregate_article(second_article.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_future_event_timestamps_do_not_keep_event_active(self):
        db = self.Session()
        embedding = [1.0] + [0.0] * 767
        first_article = Article(title="异常时间事件", content="异常时间内容")
        second_article = Article(title="当前报道", content="当前报道内容")
        db.add_all([first_article, second_article])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_article.news_id,
                    embedding=embedding,
                    keywords=["共同主题"],
                ),
                Analysis(
                    news_id=second_article.news_id,
                    embedding=embedding,
                    keywords=["共同主题"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_article.news_id)
        future_time = datetime.now() + timedelta(days=365)
        first_event.create_time = future_time
        first_event.update_time = future_time
        db.commit()

        second_event = service.aggregate_article(second_article.news_id)

        self.assertNotEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 2)
        db.close()

    def test_summer_tv_news_does_not_absorb_world_cup_news(self):
        db = self.Session()
        embedding = [1.0] + [0.0] * 767
        summer_news = Article(
            title="暑期档多部长剧开播，市场关注剧集招商表现",
            content="多部暑期档电视剧陆续上线，平台公布最新排播计划。",
        )
        world_cup_news = Article(
            title="世界杯决赛球队公布首发阵容",
            content="世界杯决赛即将开赛，两队公布首发球员名单。",
        )
        db.add_all([summer_news, world_cup_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=summer_news.news_id,
                    embedding=embedding,
                    keywords=["暑期档", "电视剧", "剧集招商"],
                ),
                Analysis(
                    news_id=world_cup_news.news_id,
                    embedding=embedding,
                    keywords=["世界杯", "决赛", "首发阵容"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        summer_event = service.aggregate_article(summer_news.news_id)
        world_cup_event = service.aggregate_article(world_cup_news.news_id)

        self.assertNotEqual(summer_event.event_id, world_cup_event.event_id)
        db.close()

    def test_celebrity_news_with_same_topic_is_merged(self):
        db = self.Session()
        first_embedding = [1.0] + [0.0] * 767
        second_embedding = [0.99, 0.01] + [0.0] * 766
        first_news = Article(
            title="演员张某出席电影首映礼回应新角色",
            content="演员张某在电影首映礼现场分享角色创作经历。",
            publish_time=datetime.now() - timedelta(hours=2),
        )
        follow_up_news = Article(
            title="张某谈新电影角色：拍摄过程很有挑战",
            content="张某接受采访，再次回应电影中的新角色。",
            publish_time=datetime.now(),
        )
        db.add_all([first_news, follow_up_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=first_embedding,
                    keywords=["张某", "电影首映礼", "新角色"],
                ),
                Analysis(
                    news_id=follow_up_news.news_id,
                    embedding=second_embedding,
                    keywords=["张某", "新电影", "新角色"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        follow_up_event = service.aggregate_article(follow_up_news.news_id)

        self.assertEqual(first_event.event_id, follow_up_event.event_id)
        db.close()

    def test_ai_news_does_not_absorb_celebrity_news(self):
        db = self.Session()
        embedding = [1.0] + [0.0] * 767
        ai_news = Article(
            title="国产AI大模型发布新版本提升推理能力",
            content="科技企业发布人工智能大模型新版本并公布评测结果。",
        )
        celebrity_news = Article(
            title="演员李某亮相电影节红毯",
            content="演员李某出席电影节活动并接受媒体采访。",
        )
        db.add_all([ai_news, celebrity_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=ai_news.news_id,
                    embedding=embedding,
                    keywords=["AI大模型", "人工智能", "推理能力"],
                ),
                Analysis(
                    news_id=celebrity_news.news_id,
                    embedding=embedding,
                    keywords=["李某", "电影节", "红毯"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        ai_event = service.aggregate_article(ai_news.news_id)
        celebrity_event = service.aggregate_article(celebrity_news.news_id)

        self.assertNotEqual(ai_event.event_id, celebrity_event.event_id)
        db.close()

    def test_similarity_below_point_eighty_five_creates_new_event(self):
        db = self.Session()
        first_embedding = [1.0] + [0.0] * 767
        second_embedding = [0.84, sqrt(1 - 0.84 ** 2)] + [0.0] * 766
        first_article = Article(title="事件首篇", content="事件内容")
        second_article = Article(title="相近报道", content="相近内容")
        db.add_all([first_article, second_article])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_article.news_id,
                    embedding=first_embedding,
                    keywords=["共同主题"],
                ),
                Analysis(
                    news_id=second_article.news_id,
                    embedding=second_embedding,
                    keywords=["共同主题"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_article.news_id)
        second_event = service.aggregate_article(second_article.news_id)

        self.assertNotEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 2)
        db.close()

    def test_world_cup_reports_merge_with_multi_signal_score(self):
        db = self.Session()
        first_embedding = [1.0] + [0.0] * 767
        second_embedding = [0.82, sqrt(1 - 0.82 ** 2)] + [0.0] * 766
        first_news = Article(
            title="世界杯 英格兰 阿根廷 半决赛",
            content="英格兰将在世界杯半决赛对阵阿根廷。",
            source="体育新闻",
        )
        second_news = Article(
            title="英格兰对阵阿根廷 晋级世界杯决赛",
            content="英格兰与阿根廷争夺世界杯决赛席位。",
            source="微博",
        )
        db.add_all([first_news, second_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=first_embedding,
                    keywords=["世界杯", "英格兰", "阿根廷", "半决赛"],
                ),
                Analysis(
                    news_id=second_news.news_id,
                    embedding=second_embedding,
                    keywords=["世界杯", "英格兰", "阿根廷", "决赛"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        second_event = service.aggregate_article(second_news.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_celebrity_new_drama_reports_from_different_sources_merge(self):
        db = self.Session()
        first_embedding = [1.0] + [0.0] * 767
        second_embedding = [0.82, sqrt(1 - 0.82 ** 2)] + [0.0] * 766
        first_news = Article(
            title="白鹿新剧开到荼蘼即将开机",
            content="剧方公布新剧开机计划。",
            source="娱乐日报",
            publish_time=datetime.now() - timedelta(hours=3),
        )
        second_news = Article(
            title="白鹿主演开到荼蘼公布开机日期",
            content="后援会发布该剧开机日期。",
            source="微博",
            publish_time=datetime.now(),
        )
        db.add_all([first_news, second_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=first_embedding,
                    keywords=["白鹿", "开到荼蘼", "新剧"],
                ),
                Analysis(
                    news_id=second_news.news_id,
                    embedding=second_embedding,
                    keywords=["白鹿", "开到荼蘼", "开机"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        second_event = service.aggregate_article(second_news.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        db.close()

    def test_match_score_two_creates_new_event(self):
        db = self.Session()
        first_news = Article(title="世界杯球队公布阵容", content="体育新闻")
        second_news = Article(title="AI产品进入消费市场", content="科技新闻")
        db.add_all([first_news, second_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["世界杯"],
                ),
                Analysis(
                    news_id=second_news.news_id,
                    embedding=[0.90, sqrt(1 - 0.90 ** 2)] + [0.0] * 766,
                    keywords=["AI产品"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        second_event = service.aggregate_article(second_news.news_id)

        self.assertNotEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 2)
        db.close()

    def test_score_three_without_event_boundary_does_not_merge(self):
        db = self.Session()
        first_news = Article(title="甲方公布阶段进展", content="首篇报道")
        second_news = Article(title="后续消息确认相关安排", content="跟进报道")
        db.add_all([first_news, second_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["共同主体"],
                ),
                Analysis(
                    news_id=second_news.news_id,
                    embedding=[0.90, sqrt(1 - 0.90 ** 2)] + [0.0] * 766,
                    keywords=["共同主体"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        second_event = service.aggregate_article(second_news.news_id)

        self.assertNotEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 2)
        db.close()

    def test_high_title_overlap_contributes_one_point(self):
        db = self.Session()
        first_news = Article(
            title="世界杯英格兰阿根廷半决赛",
            content="首篇体育报道",
        )
        second_news = Article(
            title="世界杯英格兰对阵阿根廷半决赛",
            content="另一来源体育报道",
        )
        db.add_all([first_news, second_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["首发阵容"],
                ),
                Analysis(
                    news_id=second_news.news_id,
                    embedding=[0.90, sqrt(1 - 0.90 ** 2)] + [0.0] * 766,
                    keywords=["晋级形势"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        second_event = service.aggregate_article(second_news.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_representative_embedding_does_not_block_strong_event_signals(self):
        db = self.Session()
        first_news = Article(title="世界杯英格兰阿根廷半决赛首篇", content="首篇")
        bridge_news = Article(title="世界杯英格兰阿根廷半决赛跟进", content="桥接")
        drifting_news = Article(title="世界杯英格兰阿根廷半决赛远端报道", content="远端")
        db.add_all([first_news, bridge_news, drifting_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=[1.0, 0.0] + [0.0] * 766,
                    keywords=["世界杯", "英格兰", "阿根廷", "半决赛"],
                ),
                Analysis(
                    news_id=bridge_news.news_id,
                    embedding=[0.8, 0.6] + [0.0] * 766,
                    keywords=["世界杯", "英格兰", "阿根廷", "半决赛"],
                ),
                Analysis(
                    news_id=drifting_news.news_id,
                    embedding=[0.573576, 0.819152] + [0.0] * 766,
                    keywords=["世界杯", "英格兰", "阿根廷", "半决赛"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        bridge_event = service.aggregate_article(bridge_news.news_id)
        drifting_event = service.aggregate_article(drifting_news.news_id)

        self.assertEqual(first_event.event_id, bridge_event.event_id)
        self.assertEqual(first_event.event_id, drifting_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_england_argentina_weibo_variants_merge(self):
        db = self.Session()
        base_embedding = [1.0] + [0.0] * 767
        recalled_embedding = [0.73, sqrt(1 - 0.73 ** 2)] + [0.0] * 766
        articles = [
            Article(
                title="英格兰vs阿根廷世界杯半决赛",
                content="世界杯半决赛英格兰将迎战阿根廷。",
                source="微博",
            ),
            Article(
                title="英阿大战火药味拉满",
                content="英阿大战进入关键阶段。",
                source="微博",
            ),
            Article(
                title="英格兰队1-0领先后梅西开始发挥",
                content="比赛中英格兰率先领先，梅西随后组织反击。",
                source="微博",
            ),
            Article(
                title="世界杯半决赛英阿对决",
                content="世界杯英阿对决受到球迷关注。",
                source="微博",
            ),
        ]
        db.add_all(articles)
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=articles[0].news_id,
                    embedding=base_embedding,
                    keywords=["世界杯半决赛", "英格兰队", "阿根廷队"],
                ),
                Analysis(
                    news_id=articles[1].news_id,
                    embedding=recalled_embedding,
                    keywords=["英阿大战", "世界杯"],
                ),
                Analysis(
                    news_id=articles[2].news_id,
                    embedding=recalled_embedding,
                    keywords=["英格兰队", "梅西", "比分"],
                ),
                Analysis(
                    news_id=articles[3].news_id,
                    embedding=recalled_embedding,
                    keywords=["世界杯半决赛", "英阿对决"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        events = [
            service.aggregate_article(article.news_id)
            for article in articles
        ]

        self.assertEqual(len({event.event_id for event in events}), 1)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_ronaldo_2030_world_cup_weibo_variants_merge(self):
        db = self.Session()
        first_news = Article(
            title="C罗确认将冲击2030年世界杯",
            content="C罗谈到继续参加世界杯的计划。",
            source="微博",
        )
        second_news = Article(
            title="2030世界杯还能看到他？C罗剑指再战一届",
            content="不同账号讨论C罗出战2030世界杯。",
            source="微博",
        )
        db.add_all([first_news, second_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["C罗", "2030世界杯", "参赛计划"],
                ),
                Analysis(
                    news_id=second_news.news_id,
                    embedding=[0.73, sqrt(1 - 0.73 ** 2)] + [0.0] * 766,
                    keywords=["C罗", "2030年", "出战世界杯"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        second_event = service.aggregate_article(second_news.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_world_cup_and_unrelated_football_news_do_not_merge(self):
        db = self.Session()
        world_cup = Article(
            title="世界杯半决赛英格兰对阵阿根廷",
            content="两队争夺世界杯决赛席位。",
        )
        club_football = Article(
            title="英超联赛曼城完成夏季转会签约",
            content="俱乐部公布新赛季球员签约消息。",
        )
        db.add_all([world_cup, club_football])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=world_cup.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["世界杯", "英格兰", "阿根廷", "足球"],
                ),
                Analysis(
                    news_id=club_football.news_id,
                    embedding=[0.90, sqrt(1 - 0.90 ** 2)] + [0.0] * 766,
                    keywords=["英超", "曼城", "转会", "足球"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        world_cup_event = service.aggregate_article(world_cup.news_id)
        club_event = service.aggregate_article(club_football.news_id)

        self.assertNotEqual(world_cup_event.event_id, club_event.event_id)
        db.close()

    def test_ai_salary_and_ai_regulation_do_not_merge(self):
        db = self.Session()
        salary_news = Article(
            title="AI岗位平均工资继续上涨",
            content="招聘平台发布人工智能岗位薪酬报告。",
        )
        regulation_news = Article(
            title="人工智能监管新规正式征求意见",
            content="监管部门公布AI产品治理规则。",
        )
        db.add_all([salary_news, regulation_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=salary_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["AI", "招聘", "工资"],
                ),
                Analysis(
                    news_id=regulation_news.news_id,
                    embedding=[0.90, sqrt(1 - 0.90 ** 2)] + [0.0] * 766,
                    keywords=["人工智能", "监管", "法规"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        salary_event = service.aggregate_article(salary_news.news_id)
        regulation_event = service.aggregate_article(regulation_news.news_id)

        self.assertNotEqual(salary_event.event_id, regulation_event.event_id)
        db.close()

    def test_celebrity_reports_from_different_sources_merge_at_recall_threshold(self):
        db = self.Session()
        official_news = Article(
            title="白鹿新剧开到荼蘼宣布开机",
            content="剧方发布开机信息。",
            source="新闻网站",
            publish_time=datetime.now() - timedelta(hours=6),
        )
        weibo_news = Article(
            title="白鹿主演开到荼蘼开机路透曝光",
            content="微博网友分享新剧开机现场。",
            source="微博",
            publish_time=datetime.now(),
        )
        db.add_all([official_news, weibo_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=official_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["白鹿", "开到荼蘼", "新剧"],
                ),
                Analysis(
                    news_id=weibo_news.news_id,
                    embedding=[0.75, sqrt(1 - 0.75 ** 2)] + [0.0] * 766,
                    keywords=["白鹿", "开到荼蘼", "开机"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        official_event = service.aggregate_article(official_news.news_id)
        weibo_event = service.aggregate_article(weibo_news.news_id)

        self.assertEqual(official_event.event_id, weibo_event.event_id)
        db.close()

    def test_embedding_point_nine_without_event_entity_does_not_merge(self):
        db = self.Session()
        first_news = Article(title="平台发布季度业务报告", content="季度经营数据")
        second_news = Article(title="行业公布年度观察数据", content="年度行业数据")
        db.add_all([first_news, second_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["业务报告"],
                ),
                Analysis(
                    news_id=second_news.news_id,
                    embedding=[0.90, sqrt(1 - 0.90 ** 2)] + [0.0] * 766,
                    keywords=["行业观察"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        second_event = service.aggregate_article(second_news.news_id)

        self.assertNotEqual(first_event.event_id, second_event.event_id)
        db.close()

    def test_japanese_nurse_weibo_titles_merge(self):
        db = self.Session()
        first_news = Article(
            title="#日本护士输液管致患者死亡# 一护士污染输液管被捕",
            content="日本千叶县一名护士涉嫌污染患者输液管。",
            publish_time=datetime.now() - timedelta(hours=1),
        )
        second_news = Article(
            title="#日本护士粪便掺入输液管致患者死亡# 警方公布调查进展",
            content="警方调查护士向输液管混入粪便导致患者死亡。",
            publish_time=datetime.now(),
        )
        db.add_all([first_news, second_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["日本护士", "输液管", "死亡"],
                ),
                Analysis(
                    news_id=second_news.news_id,
                    embedding=[0.93, sqrt(1 - 0.93 ** 2)] + [0.0] * 766,
                    keywords=["日本护士", "输液管", "死亡"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        second_event = service.aggregate_article(second_news.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_zheng_qinwen_reports_from_different_media_merge(self):
        db = self.Session()
        first_news = Article(
            title="#郑钦文赛季首进八强# 郑钦文轻取米契奇",
            content="郑钦文晋级WTA250雅典站八强。",
            source="体育新闻",
        )
        second_news = Article(
            title="郑钦文横扫米契奇，本赛季首次闯入巡回赛八强",
            content="另一媒体报道郑钦文晋级雅典站八强。",
            source="微博",
        )
        db.add_all([first_news, second_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["郑钦文", "米契奇", "八强"],
                ),
                Analysis(
                    news_id=second_news.news_id,
                    embedding=[0.89, sqrt(1 - 0.89 ** 2)] + [0.0] * 766,
                    keywords=["郑钦文", "米契奇", "八强"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        second_event = service.aggregate_article(second_news.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_exact_hashtag_is_a_strong_event_boundary(self):
        db = self.Session()
        first_news = Article(
            title="#某地地铁临时停运# 官方发布情况说明",
            content="当地地铁发布临时停运通知。",
        )
        second_news = Article(
            title="#某地地铁临时停运# 多家媒体跟进报道",
            content="媒体跟进当地地铁临时停运消息。",
        )
        db.add_all([first_news, second_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["地铁", "临时停运"],
                ),
                Analysis(
                    news_id=second_news.news_id,
                    embedding=[0.86, sqrt(1 - 0.86 ** 2)] + [0.0] * 766,
                    keywords=["地铁", "临时停运"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        second_event = service.aggregate_article(second_news.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        db.close()

    def test_zheng_qinwen_same_hotspot_different_expression_merges(self):
        db = self.Session()
        topic_news = Article(
            title="#郑钦文赛季首进八强# 球迷热议状态回升",
            content="郑钦文迎来本赛季重要突破。",
            publish_time=datetime.now() - timedelta(days=8),
        )
        result_news = Article(
            title="郑钦文雅典站晋级",
            content="WTA雅典站赛果确认郑钦文进入八强。",
            publish_time=datetime.now(),
        )
        db.add_all([topic_news, result_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=topic_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["郑钦文", "赛季", "八强"],
                ),
                Analysis(
                    news_id=result_news.news_id,
                    embedding=[0.71, sqrt(1 - 0.71 ** 2)] + [0.0] * 766,
                    keywords=["郑钦文", "WTA", "雅典站", "晋级"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(topic_news.news_id)
        second_event = service.aggregate_article(result_news.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_world_cup_different_public_opinion_angles_merge(self):
        db = self.Session()
        match_news = Article(
            title="#世界杯半决赛# 两队争夺决赛席位",
            content="世界杯比赛进入关键阶段。",
            publish_time=datetime.now() - timedelta(days=2),
        )
        fan_news = Article(
            title="世界杯球迷赛后发生冲突",
            content="警方处理球迷冲突。",
            publish_time=datetime.now() - timedelta(days=1),
        )
        interview_news = Article(
            title="FIFA世界杯赛前采访引发热议",
            content="球队主帅回应晋级形势。",
            publish_time=datetime.now(),
        )
        articles = [match_news, fan_news, interview_news]
        db.add_all(articles)
        db.flush()
        embeddings = [
            [1.0] + [0.0] * 767,
            [0.72, sqrt(1 - 0.72 ** 2)] + [0.0] * 766,
            [0.70, sqrt(1 - 0.70 ** 2)] + [0.0] * 766,
        ]
        keywords = [
            ["世界杯", "半决赛", "球队"],
            ["世界杯", "球迷", "冲突"],
            ["FIFA", "世界杯", "赛前采访", "晋级"],
        ]
        db.add_all(
            [
                Analysis(
                    news_id=article.news_id,
                    embedding=embedding,
                    keywords=article_keywords,
                )
                for article, embedding, article_keywords in zip(
                    articles,
                    embeddings,
                    keywords,
                )
            ]
        )
        db.commit()

        service = AggregationService(db)
        events = [service.aggregate_article(article.news_id) for article in articles]

        self.assertEqual(len({event.event_id for event in events}), 1)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_apple_ai_function_and_apple_sales_remain_separate(self):
        db = self.Session()
        feature_news = Article(
            title="苹果AI功能将在国行iPhone落地",
            content="Apple Intelligence功能进入测试。",
        )
        sales_news = Article(
            title="苹果iPhone季度销量公布",
            content="市场机构发布苹果手机出货量。",
        )
        db.add_all([feature_news, sales_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=feature_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["苹果", "AI功能", "iPhone"],
                ),
                Analysis(
                    news_id=sales_news.news_id,
                    embedding=[0.92, sqrt(1 - 0.92 ** 2)] + [0.0] * 766,
                    keywords=["苹果", "iPhone", "销量"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        feature_event = service.aggregate_article(feature_news.news_id)
        sales_event = service.aggregate_article(sales_news.news_id)

        self.assertNotEqual(feature_event.event_id, sales_event.event_id)
        self.assertEqual(db.query(Event).count(), 2)
        db.close()

    def test_simulated_one_hundred_weibo_posts_reduce_event_fragmentation(self):
        db = self.Session()
        hotspot_templates = [
            ("世界杯赛事", "世界杯球迷关注半决赛", ["世界杯", "球迷", "晋级"]),
            ("郑钦文赛事", "郑钦文WTA雅典站晋级八强", ["郑钦文", "WTA", "八强"]),
            ("日本护士事件", "日本护士输液管事件调查", ["日本护士", "输液管", "调查"]),
            ("白鹿新剧", "白鹿新剧开到荼蘼开机", ["白鹿", "开到荼蘼", "开机"]),
            ("苹果AI功能", "苹果AI功能国行落地", ["苹果", "AI功能", "国行AI"]),
            ("AI薪资", "AI岗位工资薪酬报告", ["AI工资", "招聘", "薪酬"]),
            ("地铁停运", "某地地铁临时停运", ["地铁停运", "运营调整"]),
            ("台风事件", "台风路径与登陆预警", ["台风", "登陆", "预警"]),
            ("DeepSeek融资", "DeepSeek融资新进展", ["DeepSeek融资", "投资机构"]),
            ("NFC果汁", "NFC果汁配料表讨论", ["NFC果汁", "饮料", "配料表"]),
        ]
        articles = []
        analyses = []
        for family_index, (_family, title, keywords) in enumerate(hotspot_templates):
            for post_index in range(10):
                article = Article(
                    title=f"{title}：多角度讨论{post_index}",
                    content=f"热点事件的讨论、回应或后续进展{post_index}",
                    source="微博",
                    publish_time=datetime.now() - timedelta(days=post_index),
                )
                db.add(article)
                db.flush()
                if post_index == 0:
                    embedding = [0.0] * 768
                    embedding[family_index] = 1.0
                else:
                    embedding = [0.0] * 768
                    embedding[family_index] = 0.72
                    embedding[100 + family_index * 10 + post_index] = sqrt(
                        1 - 0.72 ** 2
                    )
                articles.append(article)
                analyses.append(
                    Analysis(
                        news_id=article.news_id,
                        embedding=embedding,
                        keywords=keywords + [f"角度{post_index}"],
                    )
                )
        db.add_all(analyses)
        db.commit()

        original_event_count = len(articles)
        service = AggregationService(db)
        with patch("builtins.print"):
            for article in articles:
                service.aggregate_article(article.news_id)

        events = db.query(Event).all()
        optimized_event_count = len(events)
        embedding_counts = [int(event.embedding_count or 0) for event in events]
        distribution = {
            count: embedding_counts.count(count)
            for count in sorted(set(embedding_counts))
        }
        max_event_size = max(embedding_counts)
        print(
            "[100微博模拟]",
            f"原事件数量={original_event_count}",
            f"优化后事件数量={optimized_event_count}",
            f"最大event包含文章数={max_event_size}",
            f"embedding_count分布={distribution}",
        )

        self.assertLessEqual(optimized_event_count, 20)
        self.assertLess(optimized_event_count, original_event_count * 0.5)
        self.assertGreaterEqual(max_event_size, 8)
        self.assertEqual(sum(embedding_counts), 100)
        db.close()

    def test_concurrent_aggregation_does_not_create_duplicate_event(self):
        db = self.Session()
        articles = [
            Article(
                title="#日本护士输液管致死# 第一家媒体报道",
                content="第一篇",
            ),
            Article(
                title="#日本护士输液管致死# 第二家媒体跟进",
                content="第二篇",
            ),
        ]
        db.add_all(articles)
        db.flush()
        news_ids = [article.news_id for article in articles]
        db.add_all(
            [
                Analysis(
                    news_id=news_ids[0],
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["日本护士", "输液管", "死亡"],
                ),
                Analysis(
                    news_id=news_ids[1],
                    embedding=[0.95, sqrt(1 - 0.95 ** 2)] + [0.0] * 766,
                    keywords=["日本护士", "输液管", "死亡"],
                ),
            ]
        )
        db.commit()
        db.close()

        original_find = AggregationService._find_most_similar_event

        def slow_find(service, *args, **kwargs):
            result = original_find(service, *args, **kwargs)
            time.sleep(0.05)
            return result

        def aggregate(news_id):
            thread_db = self.Session()
            try:
                return AggregationService(thread_db).aggregate_article(news_id).event_id
            finally:
                thread_db.close()

        with patch.object(
            AggregationService,
            "_find_most_similar_event",
            slow_find,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                event_ids = list(executor.map(aggregate, news_ids))

        db = self.Session()
        self.assertEqual(len(set(event_ids)), 1)
        self.assertEqual(db.query(Event).count(), 1)
        self.assertEqual(db.query(Article).filter(Article.event_id.isnot(None)).count(), 2)
        db.close()

    def test_explicit_post_processing_merges_only_high_confidence_events(self):
        db = self.Session()
        first_event = Event(
            title="#郑钦文赛季首进八强# 郑钦文横扫米契奇",
            embedding=[1.0] + [0.0] * 767,
            embedding_count=1,
        )
        second_event = Event(
            title="#郑钦文赛季首进八强# 郑钦文晋级雅典站八强",
            embedding=[0.95, sqrt(1 - 0.95 ** 2)] + [0.0] * 766,
            embedding_count=1,
        )
        db.add_all([first_event, second_event])
        db.flush()
        articles = [
            Article(title=first_event.title, event_id=first_event.event_id),
            Article(title=second_event.title, event_id=second_event.event_id),
        ]
        db.add_all(articles)
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=articles[0].news_id,
                    event_id=first_event.event_id,
                    embedding=first_event.embedding,
                    keywords=["郑钦文", "八强"],
                ),
                Analysis(
                    news_id=articles[1].news_id,
                    event_id=second_event.event_id,
                    embedding=second_event.embedding,
                    keywords=["郑钦文", "八强"],
                ),
            ]
        )
        db.commit()

        merged = AggregationService(db).merge_similar_events()

        self.assertEqual(len(merged), 1)
        self.assertEqual(db.query(Event).count(), 1)
        target_event_id = merged[0][1]
        article_event_ids = [
            article.event_id
            for article in db.query(Article).order_by(Article.news_id).all()
        ]
        self.assertEqual(
            article_event_ids,
            [target_event_id, target_event_id],
            article_event_ids,
        )
        db.close()

    def test_strong_core_entity_can_merge_below_embedding_recall_threshold(self):
        db = self.Session()
        first_news = Article(
            title="世界杯半决赛英格兰迎战阿根廷",
            content="两队争夺决赛资格。",
        )
        second_news = Article(
            title="英格兰对阵阿根廷世界杯半决赛前瞻",
            content="不同媒体发布赛前分析。",
        )
        db.add_all([first_news, second_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=first_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["世界杯", "半决赛", "英格兰", "阿根廷"],
                ),
                Analysis(
                    news_id=second_news.news_id,
                    embedding=[0.69, sqrt(1 - 0.69 ** 2)] + [0.0] * 766,
                    keywords=["世界杯", "半决赛", "英格兰", "阿根廷"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        first_event = service.aggregate_article(first_news.news_id)
        second_event = service.aggregate_article(second_news.news_id)

        self.assertEqual(first_event.event_id, second_event.event_id)
        self.assertEqual(db.query(Event).count(), 1)
        db.close()

    def test_unrelated_finance_news_do_not_merge(self):
        db = self.Session()
        central_bank_news = Article(
            title="央行继续实施适度宽松货币政策",
            content="中国人民银行公布下一阶段货币政策安排。",
        )
        stock_news = Article(
            title="港股科技板块午后集体上涨",
            content="股票市场多个科技公司股价上涨。",
        )
        db.add_all([central_bank_news, stock_news])
        db.flush()
        db.add_all(
            [
                Analysis(
                    news_id=central_bank_news.news_id,
                    embedding=[1.0] + [0.0] * 767,
                    keywords=["央行", "货币政策", "财经"],
                ),
                Analysis(
                    news_id=stock_news.news_id,
                    embedding=[0.91, sqrt(1 - 0.91 ** 2)] + [0.0] * 766,
                    keywords=["港股", "股票", "财经"],
                ),
            ]
        )
        db.commit()

        service = AggregationService(db)
        central_bank_event = service.aggregate_article(central_bank_news.news_id)
        stock_event = service.aggregate_article(stock_news.news_id)

        self.assertNotEqual(central_bank_event.event_id, stock_event.event_id)
        db.close()


if __name__ == "__main__":
    unittest.main()
