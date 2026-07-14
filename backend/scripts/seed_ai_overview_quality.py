"""Seed a detailed news event for AI overview extraction quality checks."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


from backend_app.database import Base, SessionLocal, engine
from backend_app.models.analysis import Analysis
from backend_app.models.article import Article
from backend_app.models.event import Event


ARTICLES = [
    {
        "title": "海州市滨江新区一储能站因设备故障启动保护性停运",
        "source": "海州日报",
        "url": "https://example.com/haizhou-daily/energy-storage-incident",
        "publish_time": datetime(2026, 7, 12, 12, 20),
        "content": (
            "2026年7月12日上午9时30分，位于海州市滨江新区清源新能源产业园内的"
            "清源新能源有限公司储能电站出现电池舱温度异常报警。公司运行负责人周明远"
            "组织值班人员按照预案切断故障区域电源，储能站于9时36分启动自动保护并全面停运。"
            "滨江消防救援支队和海州市应急管理局工作人员随后赶到现场，疏散园区内36名工作人员。"
            "现场未发生明火，无人员伤亡。清源新能源有限公司通报称，初步排查显示冷却系统循环泵"
            "控制模块故障，导致部分电池模块散热能力下降。受事件影响，产业园部分生产线暂停约4小时，"
            "储能站恢复运行时间将根据设备检测和安全评估结果确定。"
        ),
        "platform": "新闻网站",
        "author": "记者 林岚",
        "is_official": False,
    },
    {
        "title": "滨江新区通报清源储能站处置情况：无人员伤亡",
        "source": "滨江发布",
        "url": "https://example.com/binjiang-release/notice-20260712",
        "publish_time": datetime(2026, 7, 12, 14, 5),
        "content": (
            "海州市滨江新区管理委员会7月12日下午发布情况通报：当日上午9时30分，"
            "清源新能源产业园储能站监测系统发现电池舱温度异常。清源新能源有限公司立即停止"
            "充放电作业并报告有关部门。9时45分，滨江消防救援支队、区应急处置中心和生态环境"
            "监测人员抵达现场，对电池舱进行降温、断电和气体检测。截至中午12时，异常温度已降至"
            "安全范围，现场无明火、无有害气体泄漏、无人员伤亡。经设备厂商与专家组初步检查，"
            "异常与冷却系统循环泵控制模块失效有关，具体原因仍在进一步调查。新区要求园区运营方"
            "清源新能源有限公司完成全站设备排查和安全评估后方可恢复运行。"
        ),
        "platform": "政务发布",
        "author": "滨江新区管理委员会",
        "is_official": True,
    },
    {
        "title": "清源新能源储能站进入全面检测阶段，园区生产秩序恢复",
        "source": "海州广播电视台",
        "url": "https://example.com/haizhou-tv/follow-up-20260713",
        "publish_time": datetime(2026, 7, 13, 9, 10),
        "content": (
            "记者7月13日从海州市应急管理局获悉，发生于7月12日上午的滨江新区清源新能源"
            "产业园储能站温度异常事件已转入设备检测阶段。海州市应急管理局相关负责人介绍，"
            "事发时储能站自动监测系统首先发出报警，清源新能源有限公司运行负责人周明远带领"
            "值班人员完成断电和人员撤离，消防救援人员随后对现场持续降温。专家组认为，冷却系统"
            "循环泵控制模块故障是本次温度异常的初步原因，未发现电池燃烧和有害物质外泄。此前暂停的"
            "园区生产线已于7月12日下午恢复生产，但储能站仍保持停运。海州市应急管理局要求运营企业"
            "更换故障部件、检查同批次设备，并在第三方安全评估通过后申请恢复运行。"
        ),
        "platform": "广播电视",
        "author": "记者 赵晨",
        "is_official": False,
    },
]


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        event = Event(
            title="海州市清源新能源产业园储能站停运事件",
            summary=(
                "2026年7月12日，海州市滨江新区清源新能源产业园储能站因冷却系统故障"
                "出现温度异常并保护性停运，现场无人员伤亡，相关部门已开展调查和安全评估。"
            ),
            heat=76.0,
            risk_level="中",
            stage="成长期",
            create_time=datetime(2026, 7, 12, 9, 30),
            update_time=datetime(2026, 7, 13, 9, 10),
            status="active",
            extra={"purpose": "ai-overview-quality"},
        )
        db.add(event)
        db.flush()
        event_id = int(event.event_id)

        news_ids: list[int] = []

        for index, item in enumerate(ARTICLES, start=1):
            article = Article(
                event_id=event_id,
                title=item["title"],
                content=item["content"],
                source=item["source"],
                url=item["url"],
                publish_time=item["publish_time"],
                platform=item["platform"],
                author=item["author"],
                account_id=f"overview-quality-{event_id}-{index}",
                account_name=item["source"],
                account_type="媒体" if not item["is_official"] else "官方机构",
                is_official=item["is_official"],
                crawl_time=item["publish_time"],
                repost_count=120 * index,
                comment_count=45 * index,
                like_count=180 * index,
                reference_urls=[],
                quoted_news_ids=[],
                parent_news_id=None,
                duplicate_group_id=f"overview-quality-{event_id}",
                created_at=item["publish_time"],
            )
            db.add(article)
            db.flush()
            news_ids.append(int(article.news_id))

            analysis = Analysis(
                news_id=article.news_id,
                event_id=event_id,
                summary=item["content"][:180],
                processed_text=f"{item['title']} {item['content']}",
                source=item["source"],
                publish_time=item["publish_time"].strftime("%Y-%m-%d %H:%M:%S"),
                url=item["url"],
                missing_fields=[],
                keywords=["储能站", "设备故障", "清源新能源", "滨江新区"],
                positive=0.1,
                neutral=0.5,
                negative=0.4,
                heat_score=72.0 + index,
                stage="成长期",
                risk_level="中",
                similar_news=news_ids[:-1],
                created_at=item["publish_time"],
            )
            db.add(analysis)

        db.commit()

        print(
            json.dumps(
                {
                    "event_id": event_id,
                    "article_count": len(ARTICLES),
                    "analysis_count": len(ARTICLES),
                    "ai_result_created": False,
                },
                ensure_ascii=False,
            )
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
