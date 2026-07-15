import json

from app.llm.base import LLMProvider
from app.llm.prompt_types import PromptBundle
from app.schemas.event import EventContext
from app.services.report_service import ReportService


class StaticReportProvider(LLMProvider):
    name = "deepseek"

    def __init__(self, output: dict) -> None:
        self.output = json.dumps(output, ensure_ascii=False)

    def generate(self, prompt: PromptBundle) -> str:
        return self.output


def event_17_payload() -> dict:
    return {
        "event_id": 17,
        "title": "海州市清源新能源产业园储能站停运事件",
        "summary": "系统背景，不作为独立新闻证据。",
        "update_time": "2026-07-13 10:00:00",
        "analysis": {
            "keywords": ["储能站", "温度异常", "冷却系统"],
            "sentiment": {"positive": 0.1, "neutral": 0.6, "negative": 0.3},
            "heat": 76,
            "stage": "成长期",
            "risk_level": "中",
        },
        "articles": [
            {
                "news_id": 53,
                "title": "储能电站出现温度异常报警",
                "content": "2026年7月12日上午9时30分，位于海州市滨江新区清源新能源产业园内的清源新能源有限公司储能电站出现电池舱温度异常报警。公司运行负责人周明远组织值班人员按照预案切断故障区域电源。",
                "source": "媒体甲",
                "url": "https://example.com/53",
                "publish_time": "2026-07-12 12:20:00",
                "platform": "新闻网站",
            },
            {
                "news_id": 54,
                "title": "初步排查冷却系统情况",
                "content": "初步排查显示冷却系统循环泵控制模块故障，导致部分电池模块散热能力下降。异常与冷却系统循环泵控制模块失效有关，具体原因仍在进一步调查。",
                "source": "媒体乙",
                "url": "https://example.com/54",
                "publish_time": "2026-07-12 18:00:00",
                "platform": "新闻网站",
            },
            {
                "news_id": 55,
                "title": "后续排查进展",
                "content": "冷却系统循环泵控制模块故障是本次温度异常的初步原因。",
                "source": "媒体丙",
                "url": "https://example.com/55",
                "publish_time": "2026-07-13 09:10:00",
                "platform": "新闻网站",
            },
        ],
    }


def model_report(overrides: dict | None = None) -> dict:
    report = {
        "overview": {
            "time": "2026年7月12日上午9时30分",
            "location": "海州市滨江新区清源新能源产业园",
            "cause": "初步原因指向冷却系统循环泵控制模块故障，具体原因仍在进一步调查。",
            "persons": ["周明远", "清源新能源有限公司"],
            "summary": "报道提及储能电站出现异常报警及后续排查情况。",
        },
        "summary": "现有报道提及温度异常报警、初步排查和后续调查状态。",
        "trend_analysis": "模型文本会由服务端最终化。",
        "risk_analysis": "模型文本会由服务端最终化。",
        "suggestions": ["持续跟踪事件调查进展及可信来源发布的后续信息。", "持续跟踪可信来源信息，关注事件事实的后续补充。"],
        "limitations": ["模型产生的限制文本不会直接用于最终结果。"],
    }
    if overrides:
        for key, value in overrides.items():
            if key == "overview":
                report["overview"].update(value)
            else:
                report[key] = value
    return report


def grounded_report(overrides: dict | None = None):
    event = EventContext.model_validate(event_17_payload())
    return ReportService(provider=StaticReportProvider(model_report(overrides))).generate(event)


def test_event_17_provider_overview_is_not_false_cleared() -> None:
    report = grounded_report()

    assert report.overview.time == "2026年7月12日上午9时30分"
    assert report.overview.location == "海州市滨江新区清源新能源产业园"
    assert report.overview.cause == "初步原因指向冷却系统循环泵控制模块故障，具体原因仍在进一步调查。"


def test_event_17_time_candidate_normalizes_morning_clock() -> None:
    event = EventContext.model_validate(event_17_payload())
    decision = ReportService._ground_event_time("2026-07-12 09:30", event.articles)

    assert decision.value == "2026年7月12日上午9时30分"
    assert decision.reason_code is None


def test_event_17_more_specific_location_is_grounded_by_hierarchy() -> None:
    event = EventContext.model_validate(event_17_payload())
    decision = ReportService._ground_location("海州市滨江新区清源新能源产业园", event.articles)

    assert decision.value == "海州市滨江新区清源新能源产业园"


def test_event_17_cause_combines_cross_article_evidence() -> None:
    event = EventContext.model_validate(event_17_payload())
    decision = ReportService._ground_cause("冷却系统循环泵控制模块故障，仍在调查", event.articles)

    assert decision.value is not None
    assert "冷却系统循环泵控制模块故障" in decision.value
    assert "初步原因" in decision.value
    assert "进一步调查" in decision.value


def test_event_17_persons_only_keep_named_natural_persons() -> None:
    report = grounded_report()

    assert report.overview.persons == ["周明远"]


def test_organization_is_not_a_report_person_and_grounded_person_is_recovered() -> None:
    report = grounded_report({"overview": {"persons": ["清源新能源有限公司"]}})

    assert report.overview.persons == ["周明远"]


def test_event_17_limitations_do_not_claim_supported_slots_are_missing() -> None:
    report = grounded_report()
    limitations = " ".join(report.limitations)

    assert "未明确事件发生时间" not in limitations
    assert "未提供可确认的事件地点" not in limitations
    assert "初步原因" not in limitations or "已提供初步原因" in limitations
    assert "最终调查结论尚未正式公布" in limitations


def test_suggestions_are_semantically_deduplicated() -> None:
    report = grounded_report()

    follow_up = [item for item in report.suggestions if "持续跟踪" in item and "可信来源" in item]
    assert len(follow_up) == 1
    assert "事件调查进展" in follow_up[0]


def test_deepseek_trend_is_preserved_instead_of_replaced_by_reporting_template() -> None:
    report = grounded_report()

    assert "模型文本会由服务端最终化" in report.trend_analysis
    assert "报道发布于" not in report.trend_analysis
    assert "不能据此判断舆情升降" in report.trend_analysis


def test_unsupported_model_overview_values_are_safely_cleared() -> None:
    report = grounded_report({"overview": {"time": "2020年1月1日上午8时", "location": "不存在的地点", "cause": "人为破坏"}})

    assert report.overview.time is None
    assert report.overview.location is None
    assert report.overview.cause is None


def test_grounding_decisions_have_internal_reason_codes_without_public_leakage() -> None:
    event = EventContext.model_validate(event_17_payload())
    decision = ReportService._ground_event_time("2020年1月1日上午8时", event.articles)
    report = grounded_report({"overview": {"time": "2020年1月1日上午8时"}})

    assert decision.reason_code == "time_normalization_mismatch"
    assert "time_normalization_mismatch" not in " ".join(report.limitations)


def test_report_prompt_person_rule_is_enforced_by_finalization() -> None:
    report = grounded_report({"overview": {"persons": ["周明远", "工作人员", "相关部门"]}})

    assert report.overview.persons == ["周明远"]
