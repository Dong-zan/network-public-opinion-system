"""Seed one idempotent, full-chain public-opinion test event."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from backend_app.database import SessionLocal
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event


SEED_KEY = "seed-test-event-world-cup-referee-controversy-v1"
EVENT_TITLE = "世界杯裁判“吹黑哨”争议舆情事件（联调测试）"

COMMON_CONTEXT = [
    (
        "【联调测试数据】本事件为网络舆情系统联调而构造，不对应任何真实球队、裁判或现实赛事。"
        "模拟背景设定在一届国际足球杯赛淘汰赛阶段，蓝海队与金城队在中立球场争夺四强席位。"
        "两队在小组赛阶段表现接近，赛前舆论普遍认为比赛胜负可能取决于定位球、防守强度和临场判罚。"
        "比赛吸引大量电视观众及网络直播用户，多个体育社区提前建立讨论专区，相关话题在开赛前已经进入热榜。"
    ),
    (
        "争议发生在下半场。蓝海队一次禁区内进攻被判无效，随后金城队获得点球并反超比分；补时阶段，"
        "蓝海队又有一粒进球因越位被取消。转播画面提供了数个不同机位，但部分慢镜头的截取起点、播放速度"
        "和画面清晰度并不一致。支持双方的账号据此形成相反判断，“裁判吹黑哨”迅速成为情绪化标签，"
        "而完整比赛规则、视频助理裁判沟通过程和现场技术条件在早期讨论中没有得到同等程度传播。"
    ),
    (
        "舆情扩散过程中，新闻媒体、球队支持者、规则解说员、赛事组织方和自媒体分别提供了不同信息。"
        "部分账号引用未经核实的聊天截图，声称裁判与某方存在利益关系；另一些账号逐帧分析画面，认为至少"
        "有一项判罚符合规则。大量转载只保留结论，没有保留原视频时间点和信息来源，导致同一段材料被包装成"
        "多个看似独立的证据。平台随后对明显伪造图片增加提示，但关于判罚尺度是否一致的争论仍在继续。"
    ),
    (
        "这一模拟事件同时具备事件聚合、情感分析、热度变化、真实性核验和AI问答所需的信息结构。"
        "报道涉及比赛时间线、官方回应、媒体核查、网民态度与后续复核结果，各篇文章发布时间依次推进。"
        "正文保留互相支持、互相质疑和后续更新的表述，便于测试系统能否区分事实、观点、传闻及待确认信息，"
        "也便于观察系统在文章增加后如何更新风险等级、关键词、事件阶段和综合报告。"
    ),
]


ARTICLES = [
    {
        "title": "淘汰赛两次关键判罚引发争议，“黑哨”话题赛后升温",
        "source": "环球体育网",
        "url": "https://example.com/test-event/world-cup-referee/initial-report",
        "publish_time": datetime(2026, 7, 10, 23, 5),
        "platform": "新闻网站",
        "author": "记者 林启",
        "account_id": "global-sports-001",
        "account_name": "环球体育网赛事频道",
        "account_type": "新闻媒体",
        "is_official": False,
        "repost_count": 320,
        "comment_count": 680,
        "like_count": 1450,
        "heat_score": 32.0,
        "sentiment": (0.12, 0.43, 0.45),
        "risk_level": "低",
        "stage": "萌芽期",
        "keywords": ["世界杯", "裁判判罚", "点球", "越位", "黑哨争议"],
        "sections": [
            (
                "比赛结束后，本报记者整理现场记录发现，最早出现争议的是第六十七分钟的禁区接触。"
                "蓝海队前锋倒地后，主裁判示意比赛继续，视频助理裁判进行了短暂复核但未建议场边回看。"
                "八分钟后金城队进攻球员在另一侧禁区倒地，主裁判判罚点球。两个判罚间隔较短，"
                "成为球迷比较执法尺度的主要依据。由于赛事技术频道尚未发布复核音频，外界只能依据转播画面推测。"
            ),
            (
                "赛后混合采访区内，蓝海队主教练表示球队尊重比赛结果，但希望赛事方解释两次身体接触采用不同标准的原因。"
                "金城队主教练则认为点球判罚清楚，并提醒公众不要把对判罚的质疑升级为对裁判个人的攻击。"
                "当值裁判组按照赛事规定没有接受媒体采访。现场监督仅确认相关判罚已被记录在比赛报告中，"
                "并称是否启动额外复核需要等待技术委员会决定。"
            ),
            (
                "截至发稿，带有“黑哨”字样的话题阅读量快速上升，但热传内容中既有完整比赛片段，也有经过裁切的短视频。"
                "一张所谓内部转账记录截图被多个账号转发，原始发布者没有说明来源，图片中的日期格式也与赛事所在地常用格式不符。"
                "本报尚未找到能够验证该截图真实性的独立材料，因此不把它作为判罚受到操纵的证据。"
            ),
            (
                "多名规则专家建议将争议拆分处理：首先判断具体动作是否达到犯规标准，其次判断视频助理裁判是否有权介入，"
                "最后再讨论两次判罚是否体现一致尺度。专家强调，判罚存在争议不等同于裁判存在利益输送。"
                "在正式比赛报告公布前，媒体应继续核对画面、规则条文和各方可确认陈述。"
            ),
        ],
    },
    {
        "title": "赛事纪律委员会回应争议判罚：已启动技术复核，网传交易截图系伪造",
        "source": "赛事纪律委员会",
        "url": "https://example.com/test-event/world-cup-referee/official-response",
        "publish_time": datetime(2026, 7, 11, 9, 20),
        "platform": "官方公告平台",
        "author": "赛事纪律委员会新闻办公室",
        "account_id": "competition-official-2026",
        "account_name": "赛事纪律委员会",
        "account_type": "赛事官方机构",
        "is_official": True,
        "repost_count": 1180,
        "comment_count": 1320,
        "like_count": 4360,
        "heat_score": 48.0,
        "sentiment": (0.18, 0.55, 0.27),
        "risk_level": "中",
        "stage": "发酵期",
        "keywords": ["官方回应", "技术复核", "伪造截图", "视频助理裁判", "纪律调查"],
        "sections": [
            (
                "赛事纪律委员会上午发布书面说明，确认裁判技术小组已调取完整转播信号、门线及越位校准数据、"
                "视频助理裁判工作日志和比赛监督报告。说明称，技术复核属于例行质量评估，不预设判罚正确或错误，"
                "也不代表已经对裁判启动纪律处分。委员会将在核对关键时间点后公布可公开部分，并保护裁判组正常履职权益。"
            ),
            (
                "针对网络传播的所谓转账截图，委员会表示图中账户编号不符合赛事财务系统编码规则，"
                "截图所列时间也早于相关裁判组最终指派时间。赛事信息安全部门比对后认定该图片由多张无关页面拼接而成，"
                "已经向传播平台提交伪造材料说明。委员会提醒公众保存原始链接，不要继续传播无法说明来源的个人信息。"
            ),
            (
                "公告同时解释，视频助理裁判只有在进球、点球、直接红牌和认错处罚对象等特定场景出现清晰明显错误时才能介入。"
                "是否建议主裁判回看，不仅取决于接触是否存在，还取决于主裁判现场描述、动作强度、控球可能性和画面能否推翻原判断。"
                "因此，不同事件的复核时长不能单独作为偏袒某队的证明。"
            ),
            (
                "蓝海队随后确认已通过正式渠道提交技术问询，没有提出利益输送指控。金城队表示将配合提供比赛资料。"
                "赛事方呼吁球队工作人员避免使用侮辱性表述，并称已记录数十条针对裁判及其家属的威胁信息。"
                "如相关言论涉嫌违法，将依法转交所在地执法机构。技术复核结论预计在四十八小时内发布。"
            ),
        ],
    },
    {
        "title": "多机位逐帧核查争议比赛：点球依据充分，越位画面仍有解释空间",
        "source": "体坛深度",
        "url": "https://example.com/test-event/world-cup-referee/media-follow-up",
        "publish_time": datetime(2026, 7, 11, 14, 40),
        "platform": "新闻客户端",
        "author": "调查记者 周衡、规则编辑 陈默",
        "account_id": "sports-depth-app",
        "account_name": "体坛深度调查组",
        "account_type": "专业体育媒体",
        "is_official": False,
        "repost_count": 2640,
        "comment_count": 3580,
        "like_count": 7820,
        "heat_score": 64.0,
        "sentiment": (0.16, 0.49, 0.35),
        "risk_level": "中",
        "stage": "扩散期",
        "keywords": ["逐帧核查", "多机位", "判罚尺度", "媒体调查", "信息核验"],
        "sections": [
            (
                "体坛深度获得赛事公共转播库中的四个机位画面，并邀请两名不参与本届赛事执法的退役国际级裁判分别观看。"
                "两名专家均认为，金城队获得点球的动作包含防守球员从侧后方踩踏进攻球员脚面的过程，"
                "主裁判位置能够观察到接触，视频助理裁判维持原判具有规则依据。专家同时指出，慢动作会放大接触观感，"
                "判断时仍需结合正常速度下动作造成的实际影响。"
            ),
            (
                "对于补时阶段被取消的进球，公共画面显示蓝海队接球队员肩部可能略微越过倒数第二名防守队员，"
                "但现有公开视频没有叠加官方校准线。网络上流传的一条“绝对不越位”分析视频使用了不同帧作为传球时刻，"
                "其选帧比球真正离脚晚约两帧。另一个支持越位结论的视频则过度锐化边缘，也不能替代官方系统数据。"
            ),
            (
                "报道追踪了二十个高传播账号，发现其中十二个账号使用几乎相同的标题和剪辑顺序，最早来源是一段没有署名的短视频。"
                "这些转载被部分用户误认为来自多个独立媒体。另有三个账号主动更正了转账截图相关内容，"
                "但更正帖传播量明显低于原帖。信息传播的不对称，使已经被官方否认的材料仍在部分讨论区反复出现。"
            ),
            (
                "本报认为，目前材料可以支持“判罚值得解释”和“网络存在误导剪辑”两项判断，不能支持“裁判收受利益”的指控。"
                "技术复核仍应回答越位校准、第一次禁区接触不判罚的现场判断，以及裁判组沟通是否符合流程。"
                "在完整报告公布前，将规则争议直接归结为操纵比赛会放大对立，也可能伤害正常监督的可信度。"
            ),
        ],
    },
    {
        "title": "“黑哨”话题冲上热榜：球迷质疑、规则科普与攻击性言论同时增长",
        "source": "热点观察实验室",
        "url": "https://example.com/test-event/world-cup-referee/public-discussion",
        "publish_time": datetime(2026, 7, 11, 20, 15),
        "platform": "社交媒体",
        "author": "数据研究员 许澄",
        "account_id": "hot-topic-lab",
        "account_name": "热点观察实验室",
        "account_type": "网络舆情观察机构",
        "is_official": False,
        "repost_count": 8950,
        "comment_count": 12600,
        "like_count": 28400,
        "heat_score": 82.0,
        "sentiment": (0.08, 0.31, 0.61),
        "risk_level": "高",
        "stage": "高潮期",
        "keywords": ["热榜", "网民讨论", "情绪对立", "网络暴力", "规则科普"],
        "sections": [
            (
                "热点观察实验室对公开讨论样本进行去重后发现，话题在官方回应发布后并未立即降温，反而因回应内容被不同阵营截取而再次上升。"
                "支持蓝海队的用户集中讨论第一次禁区接触和补时越位，支持金城队的用户则大量转发点球踩踏画面。"
                "中立讨论主要关注视频助理裁判流程、官方校准线和两次判罚是否具有可比性。"
            ),
            (
                "样本中负面表达占比明显提高，但负面情绪并不都指向同一对象。一部分用户批评赛事透明度，"
                "一部分用户攻击裁判个人，还有用户质疑媒体使用“黑哨”标题制造流量。规则科普内容的收藏率较高，"
                "传播速度却低于带有愤怒表情和绝对化结论的短视频。多个社区管理员开始置顶完整时间线和官方说明。"
            ),
            (
                "风险较高的内容包括公开裁判家庭住址、号召线下围堵以及继续传播伪造交易截图。平台已删除部分个人信息，"
                "并对相关账号采取限制推荐措施。与此同时，也有球迷组织发起“只谈判罚、不攻击个人”的倡议，"
                "邀请退役裁判直播讲解规则。该倡议获得两队部分知名支持者转发，但尚未完全改变对立气氛。"
            ),
            (
                "从舆情治理角度看，后续信息应同时满足速度和可验证性：赛事方需要提供关键画面、规则依据和流程解释，"
                "球队应约束工作人员避免暗示未经证实的利益关系，平台则需区分正常质疑与人身威胁。"
                "如果最终报告只给出结论而缺乏证据链，争议可能继续转化为对赛事公信力的长期怀疑。"
            ),
        ],
    },
    {
        "title": "技术复核公布：维持比赛结果，承认首次争议处置沟通不够充分",
        "source": "国际足球周刊",
        "url": "https://example.com/test-event/world-cup-referee/final-progress",
        "publish_time": datetime(2026, 7, 12, 16, 30),
        "platform": "视频资讯平台",
        "author": "特派记者 顾远",
        "account_id": "international-football-weekly",
        "account_name": "国际足球周刊",
        "account_type": "体育期刊媒体",
        "is_official": False,
        "repost_count": 6120,
        "comment_count": 9340,
        "like_count": 22100,
        "heat_score": 91.0,
        "sentiment": (0.21, 0.46, 0.33),
        "risk_level": "高",
        "stage": "持续期",
        "keywords": ["复核结论", "维持赛果", "流程改进", "公信力", "后续进展"],
        "sections": [
            (
                "赛事技术委员会公布复核摘要，认定金城队点球判罚和补时越位判罚均有足够技术依据，比赛结果保持不变。"
                "官方校准图显示，传球瞬间蓝海队接球队员可判罚部位越过防守队员约数厘米。委员会同时确认，"
                "第一次禁区接触属于可以接受的现场判断范围，但裁判组内部沟通记录过于简略，未能为赛后解释提供充分信息。"
            ),
            (
                "复核摘要没有发现裁判组、球队或赛事工作人员之间存在异常资金往来，也再次确认网络交易截图为伪造。"
                "技术委员会认为，公众对判罚尺度提出质疑具有合理性，但现有证据不支持操纵比赛指控。"
                "当值主裁判不会受到纪律处罚，不过裁判团队将参加针对重大争议沟通记录的专项培训。"
            ),
            (
                "蓝海队发表声明接受赛果，同时保留对第一次禁区接触尺度的不同意见，并呼吁停止骚扰裁判及家属。"
                "金城队表示将专注后续比赛。此前传播绝对化指控的部分自媒体删除了相关视频，也有账号将标题改为“判罚争议复盘”。"
                "不过，少数讨论仍认为官方既是赛事组织者又是调查者，要求引入独立裁判专家参与公开评议。"
            ),
            (
                "事件进入后续治理阶段后，讨论重点由单一判罚逐渐转向赛事透明度。委员会承诺在未来重要比赛中增加赛后技术说明，"
                "并研究在不干扰比赛的前提下公开部分视频裁判沟通。媒体专家认为，这一改进可能降低信息真空，"
                "但无法替代稳定一致的执法标准。该事件的长期影响将取决于后续比赛是否落实公开承诺，以及平台能否持续治理伪造材料和人身攻击。"
            ),
        ],
    },
]


def build_content(sections: list[str]) -> str:
    content = "\n\n".join([*COMMON_CONTEXT, *sections])
    if len(content) < 1000:
        raise ValueError(f"article content is too short: {len(content)}")
    return content


def get_or_create_event(db) -> tuple[Event, bool]:
    event = db.query(Event).filter(Event.title == EVENT_TITLE).first()

    if event:
        extra = event.extra if isinstance(event.extra, dict) else {}
        if extra.get("seed_key") != SEED_KEY:
            raise RuntimeError(
                "An event with the seed title already exists but is not owned by this script."
            )
        return event, False

    event = Event(
        title=EVENT_TITLE,
        summary=(
            "模拟国际足球杯赛淘汰赛关键判罚引发网络争议。舆情经历初始质疑、官方回应、"
            "媒体核查、网民激烈讨论和技术复核公布五个阶段，用于测试事件聚合、NLP分析、AI问答与AI报告。"
        ),
        heat=91.0,
        risk_level="高",
        stage="持续期",
        create_time=datetime(2026, 7, 10, 22, 30),
        update_time=datetime(2026, 7, 12, 16, 30),
        status="active",
        extra={"seed_key": SEED_KEY, "purpose": "full-chain-integration-test"},
    )
    db.add(event)
    db.flush()
    return event, True


def seed_articles_and_analyses(db, event: Event) -> tuple[int, int]:
    created_articles = 0
    created_analyses = 0
    previous_news_ids: list[int] = []

    for item in ARTICLES:
        content = build_content(item["sections"])
        article = db.query(Article).filter(Article.url == item["url"]).first()

        if article:
            if int(article.event_id or 0) != int(event.event_id):
                raise RuntimeError(
                    f"Article URL already belongs to another event: {item['url']}"
                )
        else:
            article = Article(
                event_id=event.event_id,
                title=item["title"],
                content=content,
                source=item["source"],
                url=item["url"],
                publish_time=item["publish_time"],
                platform=item["platform"],
                author=item["author"],
                account_id=item["account_id"],
                account_name=item["account_name"],
                account_type=item["account_type"],
                is_official=item["is_official"],
                crawl_time=item["publish_time"],
                repost_count=item["repost_count"],
                comment_count=item["comment_count"],
                like_count=item["like_count"],
                reference_urls=[],
                quoted_news_ids=[],
                parent_news_id=None,
                duplicate_group_id=SEED_KEY,
                created_at=item["publish_time"],
            )
            db.add(article)
            db.flush()
            created_articles += 1

        analysis = (
            db.query(Analysis)
            .filter(Analysis.news_id == article.news_id)
            .first()
        )

        if analysis:
            if int(analysis.event_id or 0) != int(event.event_id):
                raise RuntimeError(
                    f"Analysis belongs to another event: news_id={article.news_id}"
                )
        else:
            positive, neutral, negative = item["sentiment"]
            analysis = Analysis(
                news_id=article.news_id,
                event_id=event.event_id,
                summary=content[:300],
                processed_text=content,
                source=item["source"],
                publish_time=item["publish_time"].strftime("%Y-%m-%d %H:%M:%S"),
                url=item["url"],
                missing_fields=[],
                keywords=item["keywords"],
                positive=positive,
                neutral=neutral,
                negative=negative,
                heat_score=item["heat_score"],
                stage=item["stage"],
                risk_level=item["risk_level"],
                similar_news=list(previous_news_ids),
                created_at=item["publish_time"],
            )
            db.add(analysis)
            created_analyses += 1

        previous_news_ids.append(int(article.news_id))

    return created_articles, created_analyses


def validate_seed(db, event: Event) -> dict:
    event_count = db.query(Event).filter(Event.title == EVENT_TITLE).count()
    articles = (
        db.query(Article)
        .filter(Article.event_id == event.event_id)
        .order_by(Article.publish_time.asc())
        .all()
    )
    analyses = (
        db.query(Analysis)
        .filter(Analysis.event_id == event.event_id)
        .all()
    )
    analysis_by_news_id = {int(item.news_id): item for item in analyses}
    content_lengths = [len(item.content or "") for item in articles]
    heat_distribution = [
        analysis_by_news_id[int(article.news_id)].heat_score
        for article in articles
        if int(article.news_id) in analysis_by_news_id
    ]
    every_article_has_analysis = all(
        int(article.news_id) in analysis_by_news_id for article in articles
    )

    if event_count != 1:
        raise RuntimeError(f"Expected 1 seeded event, found {event_count}")
    if len(articles) != 5:
        raise RuntimeError(f"Expected 5 articles, found {len(articles)}")
    if len(analyses) != 5 or not every_article_has_analysis:
        raise RuntimeError("Each seeded article must have exactly one analysis")
    if min(content_lengths) < 1000:
        raise RuntimeError("Every seeded article must contain at least 1000 characters")
    if heat_distribution != sorted(heat_distribution):
        raise RuntimeError("Heat scores must increase over time")

    return {
        "event_id": int(event.event_id),
        "event_count": event_count,
        "article_count": len(articles),
        "analysis_count": len(analyses),
        "every_article_has_analysis": every_article_has_analysis,
        "average_content_length": round(sum(content_lengths) / len(content_lengths), 2),
        "content_lengths": content_lengths,
        "heat_score_distribution": heat_distribution,
    }


def main() -> None:
    db = SessionLocal()

    try:
        event, event_created = get_or_create_event(db)
        created_articles, created_analyses = seed_articles_and_analyses(db, event)
        db.flush()
        result = validate_seed(db, event)
        db.commit()
        result.update(
            {
                "event_created": event_created,
                "articles_created": created_articles,
                "analyses_created": created_analyses,
            }
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
