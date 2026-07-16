"""Assign analyzed news articles to events by embedding similarity."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from math import ceil, sqrt
import re
import threading
from typing import Iterable

from sqlalchemy import and_, case, inspect
from sqlalchemy.orm import Session

from backend_app.models.analysis import Analysis
from backend_app.models.ai_result import AIResult
from backend_app.models.article import Article
from backend_app.models.article_verification import ArticleVerification
from backend_app.models.event import Event
from backend_app.models.event_heat_history import EventHeatHistory
from backend_app.services.embedding_utils import merge_embedding_center
from backend_app.services.event_heat_service import EventHeatService


EVENT_CANDIDATE_SIMILARITY_THRESHOLD = 0.64
EVENT_MATCH_SCORE_THRESHOLD = 3
EVENT_ACTIVE_WINDOW_HOURS = 720
EVENT_STRONG_TIME_WINDOW_HOURS = 720
EVENT_KEYWORD_TIME_WINDOW_HOURS = 720
EVENT_HIGH_EMBEDDING_THRESHOLD = 0.70
EVENT_POST_MERGE_SIMILARITY_THRESHOLD = 0.90
TITLE_SIMILARITY_THRESHOLD = 0.25
TITLE_STRONG_SIMILARITY_THRESHOLD = 0.45
TITLE_MIN_SHARED_BIGRAMS = 3
TITLE_CORE_MIN_LENGTH = 4
TITLE_CORE_MAX_LENGTH = 12
TITLE_CORE_MIN_OVERLAP = 2

_AGGREGATION_LOCK = threading.RLock()

TEXT_ALIASES = (
    ("世界杯半决赛", "世界杯 半决赛"),
    ("英格兰队", "英格兰"),
    ("三狮军团", "英格兰"),
    ("阿根廷队", "阿根廷"),
    ("英阿大战", "英格兰 阿根廷"),
    ("英阿对决", "英格兰 阿根廷"),
    ("人工智能", "ai"),
)
DOMAIN_ENTITY_ALIASES = {
    "AI": ("ai", "人工智能"),
    "体育": ("体育",),
    "足球": ("足球",),
    "财经": ("财经", "股市", "股票", "a股", "港股", "央行", "中国人民银行"),
    "科技": ("科技",),
    "中国": ("中国",),
    "美国": ("美国",),
}
EVENT_ENTITY_ALIASES = {
    "世界杯": ("世界杯", "world cup"),
    "半决赛": ("半决赛",),
    "英格兰": ("英格兰", "三狮军团"),
    "阿根廷": ("阿根廷",),
    "梅西": ("梅西", "messi"),
    "C罗": ("c罗", "cristiano ronaldo", "ronaldo"),
    "郑钦文": ("郑钦文",),
    "王俊凯": ("王俊凯", "俊凯"),
    "赖斯": ("赖斯",),
    "苹果": ("苹果", "apple"),
    "iPhone": ("iphone",),
    "DeepSeek": ("deepseek",),
    "FIFA": ("fifa", "国际足联"),
    "日本护士输液管致死": (
        "日本护士输液管致死",
        "日本护士污染输液管致患者死亡",
        "日本一护士污染输液管致患者死亡",
        "日本护士粪便掺入输液管致患者死亡",
        "日本护士输液管混粪便致患者死亡",
        "输液管混粪便致死",
    ),
    "NFC果汁": ("nfc果汁",),
    "快递员摔裂手镯": (
        "快递员摔裂手镯",
        "快递员摔裂18 6万手镯",
        "快递员摔裂18.6万手镯",
        "快递员摔裂",
    ),
}
ENTITY_IMPLICATIONS = {"梅西": {"阿根廷"}}
GENERIC_KEYWORDS = {
    "ai", "人工智能", "足球", "体育", "财经", "科技", "中国", "美国",
    "新闻", "热点", "最新消息",
}
FINGERPRINT_STOPWORDS = GENERIC_KEYWORDS | {
    "事件", "相关", "回应", "表示", "发布", "公布", "消息", "情况",
    "进展", "后续", "网友", "媒体", "引发", "关注", "讨论", "最新",
    "现场", "问题", "工作", "进行", "已经", "目前", "今日", "今天",
    "一个", "这个", "什么", "怎么", "为何", "视频", "微博",
    "攻击", "回应", "伤亡", "反应", "调查", "通报", "宣布", "确认",
    "比赛", "晋级", "淘汰", "发生", "造成", "影响",
    "安全", "风险", "隐患", "冲突", "危机", "政策", "规划", "十五",
    "官方", "品牌", "平台", "行业", "市场", "相关部门",
    "死亡", "智能", "满血", "治理", "整改", "违法", "消费", "创新",
    "发展", "停产", "涉事", "负责人", "领导", "活动", "要求", "称",
    "躺平", "喜欢", "东西", "感觉", "到底", "真的", "直接", "发现",
}
COMMON_CHINESE_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛范彭鲁韦昌马苗凤方俞任袁柳鲍史唐费廉"
    "岑薛雷贺倪汤滕殷罗毕郝安常乐于傅皮卞齐康伍余元顾孟黄穆萧尹"
    "姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜"
    "阮蓝闵席季麻强贾路娄江童颜郭梅盛林钟徐邱骆高夏蔡田樊胡凌霍"
    "虞万支柯管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚"
    "程嵇邢裴陆荣翁荀羊甄曲封芮储靳汲邴糜松井段富巫乌焦巴弓牧隗"
    "山谷侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘钭厉戎祖武符刘景詹束龙"
    "叶幸司韶黎乔苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍郤璩桑桂濮"
    "牛寿通边扈燕冀郏浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古"
    "易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧利师巩聂晁勾"
    "敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权"
    "盖益桓公"
) | {"白"}
LOCATION_EVENT_ENTITIES = {
    "中国", "美国", "英国", "法国", "德国", "日本", "韩国", "俄罗斯",
    "乌克兰", "伊朗", "伊拉克", "以色列", "印度", "加拿大", "澳大利亚",
    "西班牙", "葡萄牙", "阿根廷", "英格兰", "上海", "北京", "河南",
    "沈阳", "佛山", "千叶", "亚特兰大", "霍尔木兹",
}
EVENT_ACTION_TERMS = {
    "开机", "妆容", "考察", "团结", "强调", "调查", "录制", "演唱会",
    "打击", "反制", "伤亡", "抗议", "致函", "判罚", "比赛", "晋级",
    "淘汰", "落地", "发布", "停产", "整改", "坍塌", "获奖", "路演",
}
GENERIC_HASHTAG_BRIDGES = {
    "出租", "生活", "大家", "这个", "那个", "怎么", "为何", "提醒",
    "第一次", "网友", "事情", "问题", "今日", "今天",
}
PERSON_EVENT_ENTITIES = {"梅西", "C罗", "郑钦文", "王俊凯", "赖斯"}
SPORT_EVENT_ENTITIES = {"世界杯", "半决赛"}
MATCH_PARTICIPANT_ENTITIES = {"英格兰", "阿根廷", "梅西", "C罗"}
COMPANY_ENTITIES = {"苹果", "iPhone", "DeepSeek", "FIFA"}
STRUCTURED_ACTION_ALIASES = {
    "参赛": ("参赛", "出战", "征战", "冲击", "剑指", "备战", "亮相", "登场"),
    "融资": ("融资", "募资", "增资", "引资"),
    "监管": ("监管", "治理", "新规", "法规", "管理办法", "征求意见"),
}
POLICY_SUBJECT_ALIASES = {
    "AI": ("ai", "人工智能", "大模型", "算法"),
    "央行": ("央行", "中国人民银行"),
}

# Event families are deliberately broader than named entities.  They model a
# public-opinion hotspot, so interviews, reactions and follow-up developments
# can be recalled even when they do not repeat the exact event wording.
EVENT_FAMILY_ALIASES = {
    "世界杯赛事": (
        "世界杯", "fifa", "半决赛", "决赛", "球队", "球迷", "晋级", "淘汰",
    ),
    "郑钦文赛事": (
        "郑钦文", "wta", "雅典站", "网球", "八强",
    ),
    "日本护士事件": (
        "日本护士", "护士", "输液管", "患者", "死亡", "调查",
    ),
    "白鹿新剧": ("白鹿", "开到荼蘼", "新剧", "开机"),
    "苹果AI功能": ("苹果ai", "apple intelligence", "国行ai", "ai功能"),
    "苹果销量": ("苹果销量", "iphone销量", "出货量", "销量"),
    "AI薪资": ("ai工资", "ai薪资", "岗位工资", "招聘薪酬", "薪酬报告"),
    "AI监管": ("ai监管", "人工智能监管", "监管新规", "治理规则", "法规"),
    "足球转会": ("足球转会", "俱乐部转会", "夏季转会", "签约", "加盟"),
    "地铁停运": ("地铁停运", "临时停运", "地铁故障", "运营调整"),
    "台风事件": ("台风", "登陆", "预警", "路径"),
    "DeepSeek融资": ("deepseek融资", "deepseek 融资", "融资", "投资机构"),
    "NFC果汁": ("nfc果汁", "果汁", "饮料", "配料表"),
}

EVENT_FAMILY_ANCHORS = {
    "世界杯赛事": ("世界杯", "fifa"),
    "郑钦文赛事": ("郑钦文",),
    "日本护士事件": ("日本护士", "输液管"),
    "白鹿新剧": ("白鹿", "开到荼蘼"),
    "苹果AI功能": ("苹果ai", "apple intelligence", "国行ai"),
    "苹果销量": ("苹果销量", "iphone销量"),
    "AI薪资": ("ai工资", "ai薪资", "岗位工资", "招聘薪酬"),
    "AI监管": ("ai监管", "人工智能监管", "监管新规"),
    "足球转会": ("足球转会", "俱乐部转会", "夏季转会"),
    "DeepSeek融资": ("deepseek融资", "deepseek 融资"),
    "NFC果汁": ("nfc果汁",),
}

ACTION_TOPIC_ALIASES = {
    "薪资": ("工资", "薪资", "薪酬", "招聘"),
    "监管": ("监管", "治理", "新规", "法规", "征求意见"),
    "AI功能": ("ai功能", "apple intelligence", "国行ai", "智能功能"),
    "AI政策": ("ai政策", "人工智能政策", "合规要求", "监管要求"),
    "销量": ("销量", "出货量", "销售额", "销售数据"),
    "转会": ("转会", "签约", "加盟", "租借"),
    "足球比赛": ("足球", "世界杯", "比赛", "半决赛", "决赛", "对阵", "晋级", "淘汰"),
    "融资": ("融资", "募资", "投资机构"),
    "IPO": ("ipo", "上市"),
}

HARD_CONFLICT_ACTION_PAIRS = {
    frozenset(("薪资", "监管")),
    frozenset(("AI功能", "AI政策")),
    frozenset(("转会", "足球比赛")),
}


def cosine_similarity(vector_a: Iterable[float], vector_b: Iterable[float]) -> float:
    """Calculate cosine similarity for two numeric vectors."""
    try:
        values_a = [float(value) for value in vector_a]
        values_b = [float(value) for value in vector_b]
    except (TypeError, ValueError):
        return 0.0

    if not values_a or len(values_a) != len(values_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(values_a, values_b))
    norm_a = sqrt(sum(value * value for value in values_a))
    norm_b = sqrt(sum(value * value for value in values_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


class AggregationService:
    def __init__(self, db: Session):
        self.db = db

    def aggregate_article(self, news_id: int):
        """Aggregate one article while serializing decisions in this process."""
        with _AGGREGATION_LOCK:
            return self._aggregate_article_locked(news_id)

    def _aggregate_article_locked(self, news_id: int):
        print("========== 开始事件聚合 ==========")
        print("news_id:", news_id)

        article = self.db.query(Article).filter(
            Article.news_id == news_id
        ).first()
        if not article:
            print("没有找到文章:", news_id)
            return None

        analysis = self.db.query(Analysis).filter(
            Analysis.news_id == news_id
        ).first()
        if not analysis:
            print("没有找到分析结果")
            return None

        (
            event,
            similarity,
            keyword_overlap,
            domain_entity_overlap,
            event_entity_overlap,
            match_score,
            create_reason,
        ) = (
            self._find_most_similar_event(
                analysis.embedding,
                analysis.keywords,
                article.title,
                article.publish_time,
            )
        )

        if event is not None:
            print(
                "匹配已有事件:",
                "article_id:", article.news_id,
                "candidate_event_id:", event.event_id,
                "similarity:", similarity,
                "domain_entity_overlap:", sorted(domain_entity_overlap),
                "event_entity_overlap:", sorted(event_entity_overlap),
                "keyword_overlap:", sorted(keyword_overlap),
                "match_score:", match_score,
                "reason:", create_reason,
            )
            self._update_event_embedding(event, analysis.embedding)
        else:
            event = self._create_event(article, analysis)
            print(
                "创建新事件:",
                event.event_id,
                "article_id:", article.news_id,
                "reason:", create_reason,
                "best_similarity:", similarity,
                "domain_entity_overlap:", sorted(domain_entity_overlap),
                "event_entity_overlap:", sorted(event_entity_overlap),
                "keyword_overlap:", sorted(keyword_overlap),
                "match_score:", match_score,
            )

        article.event_id = event.event_id
        analysis.event_id = event.event_id
        self.db.commit()

        EventHeatService(self.db).update_event_heat(event.event_id)

        print("文章绑定event完成")
        print("article.news_id:", article.news_id)
        print("event_id:", event.event_id)
        print("========== 事件聚合完成 ==========")
        return event

    def _find_most_similar_event(
        self,
        news_embedding: list[float] | None,
        article_keywords: list[str] | None,
        article_title: str | None,
        article_publish_time: datetime | None,
    ) -> tuple[Event | None, float, set[str], set[str], set[str], int, str]:
        if not news_embedding:
            return None, 0.0, set(), set(), set(), 0, "missing_embedding"

        reference_time = datetime.now()
        active_cutoff = reference_time - timedelta(
            hours=EVENT_ACTIVE_WINDOW_HOURS
        )
        valid_update_time = and_(
            Event.update_time.isnot(None),
            Event.update_time <= reference_time,
        )
        valid_create_time = and_(
            Event.create_time.isnot(None),
            Event.create_time <= reference_time,
        )
        activity_time = case(
            (
                and_(
                    valid_update_time,
                    valid_create_time,
                    Event.update_time >= Event.create_time,
                ),
                Event.update_time,
            ),
            (
                and_(valid_update_time, valid_create_time),
                Event.create_time,
            ),
            (valid_update_time, Event.update_time),
            (valid_create_time, Event.create_time),
            else_=None,
        )
        events = self.db.query(Event).filter(
            Event.embedding.isnot(None),
            activity_time >= active_cutoff,
        ).all()

        if not events:
            return None, 0.0, set(), set(), set(), 0, "no_active_event_with_embedding"

        event_context = self._event_match_context(events)
        normalized_article_keywords = self._normalize_keywords(article_keywords)
        article_domain_entities = self._extract_entities(
            article_title,
            article_keywords,
            DOMAIN_ENTITY_ALIASES,
        )
        article_event_entities = self._extract_event_entities(
            article_title,
            article_keywords,
        )
        article_title_event_entities = self._extract_event_entities(
            article_title,
            None,
        )
        article_hashtags = self._extract_hashtags(article_title)
        article_title_core_phrases = self._extract_title_core_phrases(article_title)
        article_event_families = self._extract_event_families(
            article_title,
            article_keywords,
        )
        article_action_topics = self._extract_action_topics(
            article_title,
            article_keywords,
        )
        article_fingerprint_entities = self._extract_fingerprint_entities(
            article_title,
            article_keywords,
        )
        normalized_article_body = self._normalize_text(
            self._strip_hashtags(article_title)
        ).replace(" ", "")
        article_weak_fingerprint_entities = self._extract_weak_fingerprint_entities(
            article_title,
            article_keywords,
        )
        article_person_entities = self._extract_person_entities(
            article_title,
            article_keywords,
        )
        article_event_actions = self._extract_event_actions(
            article_title,
            article_keywords,
        )
        best_event = None
        best_similarity = 0.0
        best_overlap: set[str] = set()
        best_domain_entity_overlap: set[str] = set()
        best_event_entity_overlap: set[str] = set()
        best_score = 0
        best_title_similarity = 0.0
        best_representative_similarity = 0.0
        fallback_event = None
        fallback_similarity = 0.0
        fallback_overlap: set[str] = set()
        fallback_domain_entity_overlap: set[str] = set()
        fallback_event_entity_overlap: set[str] = set()
        fallback_match_score = 0
        fallback_rank = (-1, -1.0, -1, -1, -1, -1.0)
        fallback_reason = "no_candidate_above_similarity_threshold"

        for event in events:
            similarity = cosine_similarity(news_embedding, event.embedding)
            context = event_context.get(event.event_id, {})
            overlap = (
                normalized_article_keywords
                & context.get("keywords", set())
            )
            domain_entity_overlap = (
                article_domain_entities
                & context.get("domain_entities", set())
            )
            event_entity_overlap = (
                article_event_entities
                & context.get("event_entities", set())
            )
            anchor_event_entity_overlap = (
                article_event_entities
                & context.get("anchor_event_entities", set())
            )
            exact_hashtag_overlap = (
                article_hashtags
                & context.get("hashtags", set())
            )
            event_family_overlap = (
                article_event_families
                & context.get("event_families", set())
            )
            fingerprint_entity_overlap = (
                article_fingerprint_entities
                & context.get("fingerprint_entities", set())
            )
            anchor_fingerprint_overlap = (
                article_fingerprint_entities
                & context.get("anchor_fingerprint_entities", set())
            )
            weak_fingerprint_overlap = (
                article_weak_fingerprint_entities
                & context.get("weak_fingerprint_entities", set())
            )
            eligible_weak_fingerprint_overlap = {
                entity
                for entity in weak_fingerprint_overlap
                if (
                    not re.search(r"[a-z]", entity)
                    or entity.replace(" ", "") in normalized_article_body
                )
            }
            person_overlap = (
                article_person_entities
                & context.get("person_entities", set())
            )
            event_action_overlap = (
                article_event_actions
                & context.get("event_actions", set())
            )
            action_overlap = (
                article_action_topics
                & context.get("action_topics", set())
            )
            title_core_phrase_overlap = (
                article_title_core_phrases
                & context.get("title_core_phrases", set())
            )

            title_similarity, shared_title_bigrams = self._title_similarity(
                article_title,
                context.get("titles", []),
            )
            title_score = self._title_match_score(
                title_similarity,
                shared_title_bigrams,
            )
            scored_keyword_overlap = overlap - FINGERPRINT_STOPWORDS
            title_core_match = self._title_core_topic_match(
                article_title,
                context.get("titles", []),
                scored_keyword_overlap,
                article_title_event_entities,
                context.get("title_event_entities", set()),
                title_score,
            )
            if title_core_match:
                title_score = max(title_score, 2)
            representative_embedding = context.get("representative_embedding")
            representative_similarity = (
                cosine_similarity(news_embedding, representative_embedding)
                if representative_embedding
                else None
            )
            within_event_window = self._is_time_close(
                article_publish_time,
                context.get("timeline_times", []),
                window_hours=EVENT_STRONG_TIME_WINDOW_HOURS,
            )
            if article_publish_time is None:
                # The SQL event activity filter already enforces the active
                # window; crawler records without publish_time should not lose
                # all strong semantic matching signals.
                within_event_window = True

            same_hashtag = bool(exact_hashtag_overlap and within_event_window)
            core_entity_overlap = set(anchor_fingerprint_overlap)
            core_entity_overlap = {
                entity
                for entity in core_entity_overlap
                if not str(entity).startswith("话题:")
                and self._normalize_text(entity) not in article_person_entities
            }
            same_core_entity = bool(core_entity_overlap and within_event_window)
            same_event_family = bool(event_family_overlap and within_event_window)
            core_phrase_match = bool(
                len(title_core_phrase_overlap) >= TITLE_CORE_MIN_OVERLAP
            )
            title_topic_match = bool(
                (
                    title_score >= 1
                    and context.get("article_count", 0) <= 2
                )
                or core_phrase_match
                or len(scored_keyword_overlap) >= 2
            )
            person_event_object_match = bool(
                person_overlap
                and event_action_overlap
                and (
                    core_phrase_match
                    or bool(
                        scored_keyword_overlap
                        - person_overlap
                        - event_action_overlap
                    )
                    or same_event_family
                )
            )
            strong_event_consistency = bool(
                same_core_entity
                or core_phrase_match
                or same_event_family
                or person_event_object_match
            )
            weak_embedding_consistency = bool(
                eligible_weak_fingerprint_overlap
                and similarity >= EVENT_CANDIDATE_SIMILARITY_THRESHOLD
            )
            hashtag_body_consistency = bool(
                eligible_weak_fingerprint_overlap
                or not (
                    article_fingerprint_entities
                    and context.get("fingerprint_entities", set())
                )
                or self._hashtag_body_alignment(
                    article_title,
                    exact_hashtag_overlap,
                )
            )
            article_count = context.get("article_count", 0)
            majority_consistent = True
            if article_count >= 3 and not strong_event_consistency:
                member_embeddings = context.get("member_embeddings", [])
                sample_step = max(1, ceil(len(member_embeddings) / 24))
                sampled_embeddings = member_embeddings[::sample_step][:24]
                member_similarities = [
                    cosine_similarity(news_embedding, member_embedding)
                    for member_embedding in sampled_embeddings
                    if member_embedding
                ]
                majority_consistent = self._is_majority_consistent(
                    member_similarities,
                    len(sampled_embeddings),
                )
            candidate_recalled = bool(
                similarity >= EVENT_CANDIDATE_SIMILARITY_THRESHOLD
                or exact_hashtag_overlap
                or core_entity_overlap
                or title_core_phrase_overlap
                or event_family_overlap
            )
            match_score = self._calculate_match_score(
                hashtag_match=same_hashtag,
                core_entity_match=same_core_entity,
                embedding_similarity=similarity,
                time_close=within_event_window,
                title_topic_match=title_topic_match,
                core_phrase_match=core_phrase_match,
                action_match=bool(action_overlap),
                family_match=same_event_family,
                fingerprint_match=bool(fingerprint_entity_overlap),
                weak_fingerprint_match=bool(eligible_weak_fingerprint_overlap),
            )
            hard_conflict = self._has_hard_topic_conflict(
                article_action_topics,
                context.get("action_topics", set()),
                article_event_entities,
                context.get("event_entities", set()),
                article_event_families,
                context.get("event_families", set()),
            )
            candidate_reason = "matched"
            if hard_conflict:
                candidate_reason = "hard_topic_conflict"
            elif not candidate_recalled:
                candidate_reason = "not_recalled"
            elif (
                person_overlap
                and not person_event_object_match
                and not (
                    same_core_entity
                    or core_phrase_match
                    or same_event_family
                )
                and not (
                    scored_keyword_overlap
                    - person_overlap
                    - event_action_overlap
                )
            ):
                candidate_reason = "person_without_action_object"
            elif same_hashtag and not (
                strong_event_consistency
                or hashtag_body_consistency
                or (title_topic_match and majority_consistent)
            ):
                candidate_reason = "hashtag_without_core_event"
            elif (
                eligible_weak_fingerprint_overlap
                and not strong_event_consistency
                and not same_hashtag
                and not (
                    weak_embedding_consistency
                    and majority_consistent
                )
                and title_similarity < 0.05
                and not title_topic_match
            ):
                candidate_reason = "weak_fingerprint_only"
            elif (
                context.get("article_count", 0) >= 3
                and not strong_event_consistency
                and not majority_consistent
            ):
                candidate_reason = "event_purity_drift"
            elif match_score < EVENT_MATCH_SCORE_THRESHOLD:
                candidate_reason = "score_below_threshold"

            print(
                "聚合候选:",
                "candidate_event_id:", event.event_id,
                "embedding_similarity:", round(similarity, 6),
                "representative_similarity:", (
                    round(representative_similarity, 6)
                    if representative_similarity is not None
                    else "unavailable"
                ),
                "domain_entity_overlap:", sorted(domain_entity_overlap),
                "event_entity_overlap:", sorted(event_entity_overlap),
                "fingerprint_entity_overlap:", sorted(fingerprint_entity_overlap),
                "anchor_fingerprint_overlap:", sorted(anchor_fingerprint_overlap),
                "weak_fingerprint_overlap:", sorted(weak_fingerprint_overlap),
                "eligible_weak_fingerprint_overlap:", sorted(eligible_weak_fingerprint_overlap),
                "person_overlap:", sorted(person_overlap),
                "event_action_overlap:", sorted(event_action_overlap),
                "hashtag_overlap:", sorted(exact_hashtag_overlap),
                "event_family_overlap:", sorted(event_family_overlap),
                "article_action_topics:", sorted(article_action_topics),
                "event_action_topics:", sorted(context.get("action_topics", set())),
                "action_overlap:", sorted(action_overlap),
                "title_core_phrase_overlap:", sorted(title_core_phrase_overlap),
                "keyword_overlap:", sorted(overlap),
                "title_similarity:", round(title_similarity, 6),
                "match_score:", match_score,
                "majority_consistent:", majority_consistent,
                "decision_reason:", candidate_reason,
            )

            if candidate_reason != "matched":
                candidate_rank = (
                    match_score,
                    similarity,
                    len(overlap),
                    len(domain_entity_overlap),
                    len(event_entity_overlap),
                    title_similarity,
                )
                if candidate_rank > fallback_rank:
                    fallback_event = event
                    fallback_similarity = similarity
                    fallback_overlap = overlap
                    fallback_domain_entity_overlap = domain_entity_overlap
                    fallback_event_entity_overlap = event_entity_overlap
                    fallback_match_score = match_score
                    fallback_rank = candidate_rank
                    fallback_reason = (
                        f"{candidate_reason}:event_id={event.event_id}"
                    )
                continue

            if (
                match_score,
                similarity,
                len(overlap),
                len(domain_entity_overlap),
                len(event_entity_overlap),
                title_similarity,
            ) > (
                best_score,
                best_similarity,
                len(best_overlap),
                len(best_domain_entity_overlap),
                len(best_event_entity_overlap),
                best_title_similarity,
            ):
                best_event = event
                best_similarity = similarity
                best_overlap = overlap
                best_domain_entity_overlap = domain_entity_overlap
                best_event_entity_overlap = event_entity_overlap
                best_score = match_score
                best_title_similarity = title_similarity
                best_representative_similarity = representative_similarity or 0.0

        if best_event is not None:
            return (
                best_event,
                best_similarity,
                best_overlap,
                best_domain_entity_overlap,
                best_event_entity_overlap,
                best_score,
                "matched:score="
                f"{best_score},representative_similarity="
                f"{best_representative_similarity:.6f}",
            )

        if fallback_event is not None:
            return (
                None,
                fallback_similarity,
                fallback_overlap,
                fallback_domain_entity_overlap,
                fallback_event_entity_overlap,
                fallback_match_score,
                fallback_reason,
            )

        return None, 0.0, set(), set(), set(), 0, "no_similar_event"

    def _event_match_context(self, events: list[Event]) -> dict[int, dict]:
        event_ids = [event.event_id for event in events]
        rows = (
            self.db.query(
                Article.event_id,
                Article.news_id,
                Article.title,
                Article.publish_time,
                Article.created_at,
                Analysis.keywords,
                Analysis.embedding,
            )
            .join(Analysis, Analysis.news_id == Article.news_id)
            .filter(Article.event_id.in_(event_ids))
            .all()
        )

        result = {
            event_id: {
                "keywords": set(),
                "domain_entities": set(),
                "event_entities": set(),
                "title_event_entities": set(),
                "hashtags": set(),
                "event_families": set(),
                "action_topics": set(),
                "fingerprint_entities": set(),
                "weak_fingerprint_entities": set(),
                "person_entities": set(),
                "event_actions": set(),
                "anchor_event_entities": set(),
                "anchor_fingerprint_entities": set(),
                "title_core_phrases": set(),
                "titles": [],
                "publish_times": [],
                "timeline_times": [],
                "representative_embedding": None,
                "member_embeddings": [],
                "representative_order": None,
                "article_count": 0,
                "keyword_counts": Counter(),
                "domain_entity_counts": Counter(),
                "event_entity_counts": Counter(),
                "title_event_entity_counts": Counter(),
                "event_family_counts": Counter(),
                "action_topic_counts": Counter(),
                "fingerprint_entity_counts": Counter(),
                "weak_fingerprint_entity_counts": Counter(),
                "person_entity_counts": Counter(),
                "event_action_counts": Counter(),
                "title_core_phrase_counts": Counter(),
            }
            for event_id in event_ids
        }
        for (
            event_id,
            news_id,
            title,
            publish_time,
            created_at,
            keywords,
            embedding,
        ) in rows:
            context = result[event_id]
            context["article_count"] += 1
            context["keyword_counts"].update(self._normalize_keywords(keywords))
            context["domain_entity_counts"].update(
                self._extract_entities(title, keywords, DOMAIN_ENTITY_ALIASES)
            )
            context["event_entity_counts"].update(
                self._extract_event_entities(title, keywords)
            )
            context["title_event_entity_counts"].update(
                self._extract_event_entities(title, None)
            )
            context["hashtags"].update(self._extract_hashtags(title))
            context["event_family_counts"].update(
                self._extract_event_families(title, keywords)
            )
            context["action_topic_counts"].update(
                self._extract_action_topics(title, keywords)
            )
            context["fingerprint_entity_counts"].update(
                self._extract_fingerprint_entities(title, keywords)
            )
            context["weak_fingerprint_entity_counts"].update(
                self._extract_weak_fingerprint_entities(title, keywords)
            )
            context["person_entity_counts"].update(
                self._extract_person_entities(title, keywords)
            )
            context["event_action_counts"].update(
                self._extract_event_actions(title, keywords)
            )
            context["title_core_phrase_counts"].update(
                self._extract_title_core_phrases(title)
            )
            if title:
                context["titles"].append(title)
            if embedding:
                context["member_embeddings"].append(embedding)
            if publish_time:
                context["publish_times"].append(publish_time)
            timeline_time = publish_time or created_at
            if timeline_time:
                context["timeline_times"].append(timeline_time)

            representative_order = (
                created_at is None,
                created_at.isoformat() if created_at is not None else "",
                int(news_id),
            )
            if (
                context["representative_order"] is None
                or representative_order < context["representative_order"]
            ):
                context["representative_order"] = representative_order
                context["representative_embedding"] = embedding

        consensus_fields = {
            "keywords": "keyword_counts",
            "domain_entities": "domain_entity_counts",
            "event_entities": "event_entity_counts",
            "title_event_entities": "title_event_entity_counts",
            "event_families": "event_family_counts",
            "action_topics": "action_topic_counts",
            "fingerprint_entities": "fingerprint_entity_counts",
            "weak_fingerprint_entities": "weak_fingerprint_entity_counts",
            "person_entities": "person_entity_counts",
            "event_actions": "event_action_counts",
            "title_core_phrases": "title_core_phrase_counts",
        }
        for context in result.values():
            article_count = context["article_count"]
            support = 1 if article_count <= 2 else max(2, ceil(article_count * 0.25))
            anchor_support = (
                1 if article_count <= 2 else max(2, ceil(article_count * 0.50))
            )
            for output_field, count_field in consensus_fields.items():
                context[output_field] = {
                    value
                    for value, count in context[count_field].items()
                    if count >= support
                }
            context["anchor_event_entities"] = {
                value
                for value, count in context["event_entity_counts"].items()
                if count >= anchor_support
            }
            context["anchor_fingerprint_entities"] = {
                value
                for value, count in context["fingerprint_entity_counts"].items()
                if count >= anchor_support
            }
        return result

    @staticmethod
    def _calculate_match_score(
        *,
        hashtag_match: bool,
        core_entity_match: bool,
        embedding_similarity: float,
        time_close: bool,
        title_topic_match: bool,
        core_phrase_match: bool,
        action_match: bool,
        family_match: bool,
        fingerprint_match: bool,
        weak_fingerprint_match: bool,
    ) -> int:
        score = 0
        if hashtag_match:
            score += 2
        if core_entity_match:
            score += 2
        if embedding_similarity >= EVENT_CANDIDATE_SIMILARITY_THRESHOLD:
            score += 1
        if time_close:
            score += 1
        if title_topic_match:
            score += 1
        if core_phrase_match:
            score += 1
        if action_match:
            score += 1
        if family_match:
            score += 2
        if fingerprint_match:
            score += 1
        if weak_fingerprint_match:
            score += 1
        return score

    @staticmethod
    def _is_majority_consistent(
        member_similarities: list[float],
        article_count: int,
    ) -> bool:
        """Require mature events to agree with members, not only the centroid."""
        if article_count <= 2:
            return True
        if not member_similarities:
            return False
        consistent_members = sum(
            similarity >= 0.58 for similarity in member_similarities
        )
        return consistent_members >= ceil(article_count * 0.50)

    @staticmethod
    def _title_match_score(
        title_similarity: float,
        shared_title_bigrams: int,
    ) -> int:
        if (
            shared_title_bigrams < TITLE_MIN_SHARED_BIGRAMS
            or title_similarity < TITLE_SIMILARITY_THRESHOLD
        ):
            return 0
        if title_similarity >= TITLE_STRONG_SIMILARITY_THRESHOLD:
            return 2
        return 1

    @classmethod
    def _title_similarity(
        cls,
        article_title: str | None,
        event_titles: list[str],
    ) -> tuple[float, int]:
        article_bigrams = cls._title_bigrams(article_title)
        article_core_phrases = cls._extract_title_core_phrases(article_title)
        best_similarity = 0.0
        best_shared_count = 0

        for event_title in event_titles:
            event_bigrams = cls._title_bigrams(event_title)
            shared_bigrams = len(article_bigrams & event_bigrams)
            bigram_union = len(article_bigrams | event_bigrams)
            bigram_similarity = (
                shared_bigrams / bigram_union if bigram_union else 0.0
            )

            event_core_phrases = cls._extract_title_core_phrases(event_title)
            shared_core_phrases = len(
                article_core_phrases & event_core_phrases
            )
            core_union = len(article_core_phrases | event_core_phrases)
            core_similarity = (
                shared_core_phrases / core_union if core_union else 0.0
            )
            similarity = max(bigram_similarity, core_similarity)
            shared_count = max(shared_bigrams, shared_core_phrases)
            if (similarity, shared_count) > (best_similarity, best_shared_count):
                best_similarity = similarity
                best_shared_count = shared_count

        return best_similarity, best_shared_count

    @staticmethod
    def _title_bigrams(title: str | None) -> set[str]:
        normalized = AggregationService._normalize_text(
            AggregationService._strip_hashtags(title)
        )
        normalized = AggregationService._strip_temporal_numbers(normalized)
        normalized = re.sub(r"[^\w]+", "", normalized)
        normalized = normalized.replace("_", "")
        if len(normalized) < 2:
            return set()
        return {
            normalized[index:index + 2]
            for index in range(len(normalized) - 1)
        }

    @classmethod
    def _extract_hashtags(cls, title: str | None) -> set[str]:
        """Return normalized, exact hashtag topics from a social title."""
        hashtags = set()
        for value in re.findall(r"#([^#\r\n]{2,80})#", str(title or "")):
            normalized = cls._normalize_text(value).replace(" ", "")
            if normalized:
                hashtags.add(normalized)
        return hashtags

    @staticmethod
    def _strip_hashtags(title: str | None) -> str:
        """Remove topic labels so a hashtag cannot masquerade as body evidence."""
        return re.sub(r"#([^#\r\n]{2,80})#", " ", str(title or ""))

    @classmethod
    def _hashtag_body_alignment(
        cls,
        title: str | None,
        hashtags: set[str],
    ) -> bool:
        body = cls._normalize_text(cls._strip_hashtags(title)).replace(" ", "")
        if not body:
            return False
        for hashtag in hashtags:
            topic = re.sub(r"[^\u4e00-\u9fff]", "", hashtag)
            for width in (3, 2):
                for index in range(max(0, len(topic) - width + 1)):
                    phrase = topic[index:index + width]
                    if phrase in GENERIC_HASHTAG_BRIDGES:
                        continue
                    if phrase in body:
                        return True
            body_characters = set(re.sub(r"[^\u4e00-\u9fff]", "", body))
            if len(set(topic) & body_characters) >= 3:
                return True
        return False

    @classmethod
    def _extract_title_core_phrases(cls, title: str | None) -> set[str]:
        """Extract conservative 4-12 character title tokens for event matching."""
        text = cls._strip_temporal_numbers(cls._strip_hashtags(title))
        if not text.strip():
            return set()

        segments = re.findall(r"[\u4e00-\u9fffa-zA-Z0-9.]+", text)
        phrases = set()
        for segment in segments:
            compact = cls._normalize_text(segment).replace(" ", "")
            if len(compact) < TITLE_CORE_MIN_LENGTH:
                continue
            if len(compact) <= TITLE_CORE_MAX_LENGTH:
                phrases.add(compact)
            for length in (4, 6):
                if len(compact) < length:
                    continue
                phrases.update(
                    compact[index:index + length]
                    for index in range(len(compact) - length + 1)
                )

        generic_phrases = {
            cls._normalize_text(value).replace(" ", "")
            for value in GENERIC_KEYWORDS
            if len(cls._normalize_text(value).replace(" ", "")) >= 4
        }
        return {
            phrase
            for phrase in phrases
            if TITLE_CORE_MIN_LENGTH <= len(phrase) <= TITLE_CORE_MAX_LENGTH
            and phrase not in generic_phrases
            and not phrase.isdigit()
        }

    @staticmethod
    def _strip_temporal_numbers(value: str | None) -> str:
        text = str(value or "")
        text = re.sub(
            r"(?<!\d)20\d{2}(?:年|[-/.])\d{1,2}(?:月|[-/.])?\d{0,2}日?",
            " ",
            text,
        )
        text = re.sub(r"(?<!\d)\d{1,2}月\d{1,2}日", " ", text)
        text = re.sub(r"(?<!\d)\d{1,2}(?::\d{2}){1,2}(?!\d)", " ", text)
        text = re.sub(r"(?<!\d)\d+(?:\.\d+)?%?(?!\d)", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _title_core_topic_match(
        cls,
        article_title: str | None,
        event_titles: list[str],
        shared_keywords: set[str],
        article_title_event_entities: set[str],
        event_title_entities: set[str],
        title_score: int,
    ) -> bool:
        if title_score >= 2:
            return True
        if len(article_title_event_entities & event_title_entities) >= 2:
            return True

        article_text = cls._normalize_text(article_title)
        if not article_text:
            return False
        for event_title in event_titles:
            event_text = cls._normalize_text(event_title)
            shared_title_keywords = {
                keyword
                for keyword in shared_keywords
                if len(keyword) >= 2
                and keyword in article_text
                and keyword in event_text
            }
            if len(shared_title_keywords) >= 2:
                return True
            if len(shared_keywords) >= 2 and shared_title_keywords:
                return True
        return False

    @staticmethod
    def _is_time_close(
        article_publish_time: datetime | None,
        event_publish_times: list[datetime],
        *,
        window_hours: int = EVENT_STRONG_TIME_WINDOW_HOURS,
    ) -> bool:
        if not article_publish_time or not event_publish_times:
            return False
        for event_publish_time in event_publish_times:
            try:
                difference = abs(
                    (article_publish_time - event_publish_time).total_seconds()
                )
            except (AttributeError, TypeError):
                continue
            if difference <= window_hours * 3600:
                return True
        return False

    @classmethod
    def _normalize_keywords(cls, keywords: list[str] | None) -> set[str]:
        if not keywords:
            return set()
        if isinstance(keywords, str):
            keywords = [keywords]

        normalized_keywords = set()
        for keyword in keywords:
            normalized = cls._normalize_text(keyword)
            normalized_keywords.update(
                part for part in normalized.split() if part
            )
        return normalized_keywords

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        normalized = str(value or "").strip().casefold()
        for source, target in TEXT_ALIASES:
            normalized = normalized.replace(source.casefold(), target.casefold())
        normalized = re.sub(r"[^\w]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    @classmethod
    def _extract_entities(
        cls,
        title: str | None,
        keywords: list[str] | None,
        aliases_by_name: dict[str, tuple[str, ...]],
    ) -> set[str]:
        keyword_text = " ".join(
            str(keyword)
            for keyword in (
                keywords if isinstance(keywords, list) else [keywords]
            )
            if keyword
        )
        normalized_text = cls._normalize_text(
            f"{title or ''} {keyword_text}"
        )
        entities = set()

        for canonical_name, aliases in aliases_by_name.items():
            for alias in aliases:
                normalized_alias = cls._normalize_text(alias)
                if not normalized_alias:
                    continue
                if re.fullmatch(r"[a-z0-9 ]+", normalized_alias):
                    pattern = (
                        r"(?<![a-z0-9])"
                        + re.escape(normalized_alias)
                        + r"(?![a-z0-9])"
                    )
                    matched = re.search(pattern, normalized_text)
                else:
                    matched = normalized_alias in normalized_text
                if matched:
                    entities.add(canonical_name)
                    break
        return entities

    @classmethod
    def _extract_event_entities(
        cls,
        title: str | None,
        keywords: list[str] | None,
    ) -> set[str]:
        entities = cls._extract_entities(
            title,
            keywords,
            EVENT_ENTITY_ALIASES,
        )
        entities.update(
            f"话题:{hashtag}"
            for hashtag in cls._extract_hashtags(title)
        )
        keyword_text = " ".join(
            str(keyword)
            for keyword in (
                keywords if isinstance(keywords, list) else [keywords]
            )
            if keyword
        )
        normalized_text = cls._normalize_text(f"{title or ''} {keyword_text}")

        people = entities & PERSON_EVENT_ENTITIES
        sport_events = entities & SPORT_EVENT_ENTITIES
        for person in people:
            for sport_event in sport_events:
                entities.add(f"人物事件:{person}:{sport_event}")

        years = set(re.findall(r"(?<!\d)(20\d{2})(?!\d)", normalized_text))
        actions = {
            canonical_name
            for canonical_name, aliases in STRUCTURED_ACTION_ALIASES.items()
            if any(cls._normalize_text(alias) in normalized_text for alias in aliases)
        }
        for person in people:
            for year in years:
                for action in actions:
                    entities.add(f"人物时间动作:{person}:{year}:{action}")

        if re.search(r"(?:对阵|迎战|大战|对决|\bvs?\b)", normalized_text):
            participants = sorted(entities & MATCH_PARTICIPANT_ENTITIES)
            for sport_event in sport_events:
                for index, first in enumerate(participants):
                    for second in participants[index + 1:]:
                        entities.add(f"赛事对阵:{sport_event}:{first}:{second}")

        for company in entities & COMPANY_ENTITIES:
            for action in actions:
                entities.add(f"公司动作:{company}:{action}")

        for subject, aliases in POLICY_SUBJECT_ALIASES.items():
            if not any(cls._normalize_text(alias) in normalized_text for alias in aliases):
                continue
            if "监管" in actions:
                entities.add(f"政策主体:{subject}:监管")

        if "deepseek" in normalized_text and "融资" in normalized_text:
            entities.add("DeepSeek融资")
        if "deepseek" in normalized_text and re.search(
            r"(?<![a-z0-9])ipo(?![a-z0-9])",
            normalized_text,
        ):
            entities.add("DeepSeek IPO")
        if (
            ("央行" in normalized_text or "中国人民银行" in normalized_text)
            and "货币政策" in normalized_text
        ):
            entities.add("央行货币政策")

        original_text = f"{title or ''} {keyword_text}"
        typhoon_pattern = (
            r"台风[‘'\"“]?([\u4e00-\u9fff]{2,4})"
            r"(?=登陆|生成|来袭|逼近|影响|[’'\"”\s，。,]|$)"
        )
        for typhoon_name in re.findall(typhoon_pattern, original_text):
            if typhoon_name not in {"登陆我国", "即将登陆", "预警信号", "最新消息"}:
                entities.add(f"台风:{typhoon_name}")

        for entity in tuple(entities):
            entities.update(ENTITY_IMPLICATIONS.get(entity, set()))
        return entities

    @classmethod
    def _extract_event_families(
        cls,
        title: str | None,
        keywords: list[str] | None,
    ) -> set[str]:
        keyword_text = " ".join(
            str(keyword)
            for keyword in (
                keywords if isinstance(keywords, list) else [keywords]
            )
            if keyword
        )
        normalized_text = cls._normalize_text(f"{title or ''} {keyword_text}")
        families = set()
        for family, aliases in EVENT_FAMILY_ALIASES.items():
            matched_aliases = {
                alias
                for alias in aliases
                if cls._normalize_text(alias) in normalized_text
            }
            if not matched_aliases:
                continue
            if all(
                cls._looks_like_person_entity(
                    cls._normalize_text(alias), alias
                )
                for alias in matched_aliases
            ):
                # A person name alone identifies a subject, not an event.
                continue
            anchors = EVENT_FAMILY_ANCHORS.get(family, ())
            has_anchor = any(
                cls._normalize_text(anchor) in normalized_text
                for anchor in anchors
            )
            if not anchors or has_anchor or len(matched_aliases) >= 2:
                families.add(family)
        return families

    @classmethod
    def _extract_fingerprint_entities(
        cls,
        title: str | None,
        keywords: list[str] | None,
    ) -> set[str]:
        """Return strong event fingerprints; generic nouns remain weak signals."""
        body_title = cls._strip_hashtags(title)
        known_entities = {
            cls._normalize_text(entity)
            for entity in cls._extract_event_entities(body_title, None)
            if not str(entity).startswith("话题:")
            and entity not in PERSON_EVENT_ENTITIES
        }
        candidates = cls._fingerprint_candidates(body_title, keywords)
        strong = set(known_entities)
        normalized_body = cls._normalize_text(body_title).replace(" ", "")
        for candidate in candidates:
            if cls._looks_like_person_entity(candidate, body_title):
                continue
            if (
                re.search(r"[a-z]", candidate)
                and candidate.replace(" ", "") not in normalized_body
            ):
                continue
            if candidate in {
                cls._normalize_text(value) for value in LOCATION_EVENT_ENTITIES
            }:
                strong.add(candidate)
            elif re.search(r"[a-z]", candidate) and len(candidate) >= 3:
                strong.add(candidate)
            elif len(candidate.replace(" ", "")) >= 3:
                strong.add(candidate)
        return strong

    @classmethod
    def _extract_weak_fingerprint_entities(
        cls,
        title: str | None,
        keywords: list[str] | None,
    ) -> set[str]:
        candidates = cls._fingerprint_candidates(cls._strip_hashtags(title), keywords)
        return candidates - cls._extract_fingerprint_entities(title, keywords)

    @classmethod
    def _extract_person_entities(
        cls,
        title: str | None,
        keywords: list[str] | None,
    ) -> set[str]:
        body_title = cls._strip_hashtags(title)
        candidates = cls._fingerprint_candidates(body_title, keywords)
        people = {
            candidate
            for candidate in candidates
            if cls._looks_like_person_entity(candidate, body_title)
        }
        people.update(
            cls._normalize_text(entity)
            for entity in cls._extract_event_entities(body_title, None)
            if entity in PERSON_EVENT_ENTITIES
        )
        return people

    @classmethod
    def _extract_event_actions(
        cls,
        title: str | None,
        keywords: list[str] | None,
    ) -> set[str]:
        keyword_values = (
            keywords if isinstance(keywords, list) else [keywords]
        )
        normalized = cls._normalize_text(
            f"{cls._strip_hashtags(title)} "
            + " ".join(str(value) for value in keyword_values if value)
        )
        return {
            action
            for action in EVENT_ACTION_TERMS
            if cls._normalize_text(action) in normalized
        }

    @classmethod
    def _fingerprint_candidates(
        cls,
        title: str | None,
        keywords: list[str] | None,
    ) -> set[str]:
        candidates = {
            keyword
            for keyword in cls._normalize_keywords(keywords)
            if 2 <= len(keyword) <= 24
            and keyword not in FINGERPRINT_STOPWORDS
            and not keyword.isdigit()
            and not re.fullmatch(r"(?:角度|阶段|话题|编号)\d+", keyword)
        }
        normalized_title = cls._normalize_text(title)
        candidates.update(
            token
            for token in re.findall(
                r"(?<![a-z0-9])[a-z][a-z0-9.+-]{1,23}", normalized_title
            )
            if token not in FINGERPRINT_STOPWORDS
        )
        return {candidate for candidate in candidates if candidate}

    @classmethod
    def _looks_like_person_entity(cls, entity: str, title: str | None) -> bool:
        compact = entity.replace(" ", "")
        if entity in EVENT_ACTION_TERMS or entity in ACTION_TOPIC_ALIASES:
            return False
        if entity in {cls._normalize_text(value) for value in LOCATION_EVENT_ENTITIES}:
            return False
        if entity in {cls._normalize_text(value) for value in PERSON_EVENT_ENTITIES}:
            return True
        return bool(
            re.fullmatch(r"[\u4e00-\u9fff]{2,4}", compact)
            and compact[0] in COMMON_CHINESE_SURNAMES
            and compact in cls._normalize_text(title).replace(" ", "")
        )

    @classmethod
    def _extract_action_topics(
        cls,
        title: str | None,
        keywords: list[str] | None,
    ) -> set[str]:
        keyword_text = " ".join(
            str(keyword)
            for keyword in (
                keywords if isinstance(keywords, list) else [keywords]
            )
            if keyword
        )
        normalized_text = cls._normalize_text(f"{title or ''} {keyword_text}")
        actions = {
            action
            for action, aliases in ACTION_TOPIC_ALIASES.items()
            if any(cls._normalize_text(alias) in normalized_text for alias in aliases)
        }
        if "足球比赛" in actions and not (
            "世界杯" in normalized_text
            or re.search(r"(?<![a-z0-9])fifa(?![a-z0-9])", normalized_text)
            or (
                "足球" in normalized_text
                and any(
                    term in normalized_text
                    for term in ("半决赛", "决赛", "对阵", "晋级", "淘汰")
                )
            )
        ):
            actions.remove("足球比赛")
        return actions

    @staticmethod
    def _has_hard_topic_conflict(
        article_actions: set[str],
        event_actions: set[str],
        article_entities: set[str],
        event_entities: set[str],
        article_families: set[str],
        event_families: set[str],
    ) -> bool:
        for article_action in article_actions:
            for event_action in event_actions:
                pair = frozenset((article_action, event_action))
                if pair not in HARD_CONFLICT_ACTION_PAIRS:
                    continue
                if pair == frozenset(("AI功能", "AI政策")):
                    apple_subjects = {"苹果", "iPhone"}
                    if not (
                        apple_subjects & (article_entities | event_entities)
                        or "苹果AI功能" in (article_families | event_families)
                    ):
                        continue
                return True
        return False

    def merge_similar_events(self) -> list[tuple[int, int]]:
        """Merge only very high-confidence duplicate events.

        This is an explicit maintenance operation. Normal article aggregation does
        not call it, so existing data is never rewritten implicitly.
        """
        with _AGGREGATION_LOCK:
            merged_pairs: list[tuple[int, int]] = []
            while True:
                events = (
                    self.db.query(Event)
                    .filter(Event.embedding.isnot(None))
                    .order_by(Event.event_id.asc())
                    .all()
                )
                contexts = self._event_match_context(events)
                selected_pair = None

                for index, target in enumerate(events):
                    target_context = contexts.get(target.event_id, {})
                    for source in events[index + 1:]:
                        similarity = cosine_similarity(
                            target.embedding,
                            source.embedding,
                        )
                        if similarity < EVENT_POST_MERGE_SIMILARITY_THRESHOLD:
                            continue
                        source_context = contexts.get(source.event_id, {})
                        if not self._event_titles_highly_similar(
                            target_context.get("titles", []),
                            source_context.get("titles", []),
                        ):
                            continue
                        selected_pair = (target, source)
                        break
                    if selected_pair is not None:
                        break

                if selected_pair is None:
                    break

                target, source = selected_pair
                self._merge_event_rows(target, source)
                merged_pairs.append((source.event_id, target.event_id))
                self.db.flush()

            if merged_pairs:
                self.db.commit()
            return merged_pairs

    @classmethod
    def _event_titles_highly_similar(
        cls,
        first_titles: list[str],
        second_titles: list[str],
    ) -> bool:
        for first_title in first_titles:
            first_phrases = cls._extract_title_core_phrases(first_title)
            first_hashtags = cls._extract_hashtags(first_title)
            for second_title in second_titles:
                core_overlap = first_phrases & cls._extract_title_core_phrases(
                    second_title
                )
                title_similarity, _ = cls._title_similarity(
                    first_title,
                    [second_title],
                )
                exact_hashtag = bool(
                    first_hashtags & cls._extract_hashtags(second_title)
                )
                if (
                    len(core_overlap) >= TITLE_CORE_MIN_OVERLAP
                    and (
                        title_similarity >= TITLE_STRONG_SIMILARITY_THRESHOLD
                        or exact_hashtag
                    )
                ) or (
                    exact_hashtag
                    and title_similarity >= 0.10
                ):
                    return True
        return False

    def _merge_event_rows(self, target: Event, source: Event) -> None:
        target_count = max(int(target.embedding_count or 1), 1)
        source_count = max(int(source.embedding_count or 1), 1)
        target.embedding = self._weighted_embedding_center(
            target.embedding,
            target_count,
            source.embedding,
            source_count,
        )
        target.embedding_count = target_count + source_count
        target.update_time = datetime.now()

        for article in self.db.query(Article).filter(
            Article.event_id == source.event_id
        ).all():
            article.event_id = target.event_id
        for analysis in self.db.query(Analysis).filter(
            Analysis.event_id == source.event_id
        ).all():
            analysis.event_id = target.event_id

        optional_models = (EventHeatHistory, AIResult, ArticleVerification)
        inspector = inspect(self.db.connection())
        for model in optional_models:
            if not inspector.has_table(model.__tablename__):
                continue
            for row in self.db.query(model).filter(
                model.event_id == source.event_id
            ).all():
                row.event_id = target.event_id

        self.db.delete(source)

    @staticmethod
    def _weighted_embedding_center(
        first_embedding: list[float],
        first_count: int,
        second_embedding: list[float],
        second_count: int,
    ) -> list[float]:
        if len(first_embedding) != len(second_embedding):
            raise ValueError("event embeddings must have the same dimension")
        combined = [
            float(first) * first_count + float(second) * second_count
            for first, second in zip(first_embedding, second_embedding)
        ]
        norm = sqrt(sum(value * value for value in combined))
        if norm == 0:
            return [0.0 for _ in combined]
        return [value / norm for value in combined]

    def _create_event(self, article: Article, analysis: Analysis) -> Event:
        event = Event(
            title=article.title,
            summary=article.content[:200] if article.content else "",
            heat=0,
            risk_level=analysis.risk_level,
            stage=analysis.stage,
            embedding=analysis.embedding,
            embedding_count=1,
            create_time=datetime.now(),
            update_time=datetime.now(),
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    @staticmethod
    def _update_event_embedding(
        event: Event,
        new_embedding: list[float],
    ) -> None:
        old_count = event.embedding_count or 1
        event.embedding = merge_embedding_center(
            event.embedding,
            old_count,
            new_embedding,
        )
        event.embedding_count = old_count + 1
        event.update_time = datetime.now()
