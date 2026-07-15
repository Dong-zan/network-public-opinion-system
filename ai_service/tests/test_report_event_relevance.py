import json

from app.llm.base import LLMProvider
from app.llm.prompt_types import PromptBundle
from app.schemas.event import EventContext
from app.services.report_features import extract_report_features
from app.services.report_service import ReportService


class StaticProvider(LLMProvider):
    name = "deepseek"

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def generate(self, prompt: PromptBundle) -> str:
        del prompt
        return json.dumps(self.payload, ensure_ascii=False)


def social_event() -> EventContext:
    return EventContext.model_validate(
        {
            "event_id": 9,
            "title": "离职前同事退还婚礼份子钱",
            "summary": "围绕职场人情与社交分寸展开讨论。",
            "articles": [
                {
                    "news_id": 1,
                    "title": "离职多年后退还份子钱",
                    "content": "一位离职五年多的前同事突然退还当年的婚礼份子钱，并附上致歉和祝福。",
                    "source": "社交平台账号",
                    "publish_time": "2026-07-15 11:46:00",
                },
                {
                    "news_id": 2,
                    "title": "职场人情引发讨论",
                    "content": "讨论主要围绕不占便宜、尊重他人以及成年人交往中的分寸感。",
                    "source": "社交平台账号",
                    "publish_time": "2026-07-15 12:15:00",
                },
            ],
            "analysis": {
                "keywords": ["份子钱", "离职", "体面", "职场", "社交"],
                "sentiment": {"positive": 0.7, "neutral": 0.2, "negative": 0.1},
                "heat": 28.5,
                "stage": "萌芽期",
                "risk_level": "低",
                "history": [],
            },
        }
    )


def social_model_report() -> dict:
    return {
        "overview": {
            "time": None,
            "location": None,
            "cause": None,
            "persons": [],
            "summary": "离职多年的前同事退还婚礼份子钱，引发对职场人情和社交分寸的讨论。",
        },
        "summary": "讨论焦点不是款项本身，而是主动退还所体现的边界感和不占便宜的态度。",
        "trend_analysis": "较早内容讲述退还份子钱的行为，后续讨论转向职场关系结束后如何处理人情往来。缺少连续热度数据，无法判断整体舆情升降。伤亡情况尚未明确。",
        "risk_analysis": "上游分析结果显示当前风险等级为“低”。潜在争议主要来自对份子钱是否属于人情债的不同理解，可能形成价值观分歧。最终调查结论尚未提供。",
        "suggestions": [
            "观察讨论是否从赞赏个人体面转向对职场人情压力的批评。",
            "区分当事人的个体选择与普遍职场规则，避免过度概括。",
            "重点核验伤亡情况。",
        ],
        "limitations": [
            "材料来自同一社交来源，无法判断该经历是否得到当事双方确认。",
            "事件地点尚未明确。",
            "最终调查结论尚未提供。",
        ],
    }


def test_non_incident_event_does_not_create_accident_information_gaps() -> None:
    event = social_event()
    features = extract_report_features(event, event.articles)

    assert features.relevant_fact_aspects == ()
    assert features.critical_information_gaps == ()


def test_deepseek_analysis_is_preserved_and_irrelevant_accident_text_is_removed() -> None:
    event = social_event()
    report = ReportService(provider=StaticProvider(social_model_report())).generate(event)
    visible = " ".join(
        [report.trend_analysis, report.risk_analysis]
        + report.suggestions
        + report.limitations
    )

    assert "职场关系结束后如何处理人情往来" in report.trend_analysis
    assert "份子钱是否属于人情债" in report.risk_analysis
    assert "赞赏个人体面" in " ".join(report.suggestions)
    assert "伤亡" not in visible
    assert "最终调查结论" not in visible
    assert "地点" not in " ".join(report.limitations)
    assert "事件发生时间" not in " ".join(report.limitations)
    assert "报道活跃度" not in report.trend_analysis


def test_sports_person_names_are_recovered_when_model_omits_them() -> None:
    event = EventContext.model_validate(
        {
            "event_id": 10,
            "title": "法国队无缘决赛",
            "articles": [
                {
                    "news_id": 10,
                    "content": "法国队队长姆巴佩回应称球队表现不足，主帅德尚赛后质疑裁判。",
                    "source": "体育媒体",
                }
            ],
            "analysis": {"risk_level": "低"},
        }
    )
    payload = social_model_report()
    payload["overview"] = {
        "time": None,
        "location": None,
        "cause": None,
        "persons": [],
        "summary": "法国队失利后，队长和主帅分别作出回应。",
    }
    payload["summary"] = "法国队失利后的回应引发讨论。"
    payload["trend_analysis"] = "报道重点集中在姆巴佩和德尚的赛后回应。缺少连续热度数据，无法判断整体舆情升降。"
    payload["risk_analysis"] = "上游分析结果显示当前风险等级为“低”。争议集中在球队表现与裁判评价。"
    payload["suggestions"] = ["区分球队表现评价与裁判争议。", "关注后续正式赛后说明。"]
    payload["limitations"] = ["当前只有一篇体育媒体报道。"]

    report = ReportService(provider=StaticProvider(payload)).generate(event)

    assert "姆巴佩" in report.overview.persons
    assert "德尚" in report.overview.persons
