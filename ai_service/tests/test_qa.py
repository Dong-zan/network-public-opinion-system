from app.llm.base import LLMProvider
from app.llm.prompt_types import PromptBundle
from app.schemas.event import EventContext
from app.services.qa_service import QAService


class RecordingProvider(LLMProvider):
    name = "deepseek-test"

    def __init__(self, answer: str = "这是模型返回的回答。") -> None:
        self.answer = answer
        self.prompts: list[PromptBundle] = []

    def generate(self, prompt: PromptBundle) -> str:
        self.prompts.append(prompt)
        return self.answer


def ask(client, event: dict, question: str):
    return client.post("/ai/ask", json={"event": event, "question": question})


def test_ask_event_summary(client, event_payload) -> None:
    response = ask(client, event_payload, "这个事件发生了什么？")

    assert response.status_code == 200
    assert "某地发生事故并开展救援" in response.json()["answer"]
    assert "情况通报" in response.json()["answer"]


def test_empty_question(client, event_payload) -> None:
    response = ask(client, event_payload, "   ")

    assert response.status_code == 200
    assert "无法回答" in response.json()["answer"]


def test_empty_articles_no_fake_sources(client, event_payload) -> None:
    event_payload["articles"] = []

    response = ask(client, event_payload, "有哪些媒体报道？")

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert "离线 Fake Provider 模式" in answer
    assert "当前信息不足：当前事件上下文中没有找到支持该问题的相关证据" not in answer
    assert "人民网" not in answer


def test_risk_explanation_uses_upstream_result(client, event_payload) -> None:
    response = ask(client, event_payload, "为什么风险高？")

    answer = response.json()["answer"]
    assert "上游分析" in answer
    assert "不重新计算" in answer
    assert "重新判断" not in answer
    assert "风险等级为“高”" in answer


def test_trend_without_time_series_uses_provider(client, event_payload) -> None:
    response = ask(client, event_payload, "是在升温还是降温？")

    answer = response.json()["answer"]
    assert "离线 Fake Provider 模式" in answer
    assert "缺少连续时间序列，因此无法判断" not in answer


def test_source_answer_from_articles(client, event_payload) -> None:
    response = ask(client, event_payload, "有哪些媒体报道？")

    assert "人民网" in response.json()["answer"]


def test_article_detail_by_news_id(client, event_payload) -> None:
    response = ask(client, event_payload, "news_id=1001 这篇报道说了什么？")

    answer = response.json()["answer"]
    assert "人民网：救援工作正在进行" in answer
    assert "组织救援" in answer


def test_generic_multi_article_question_uses_evidence_qa(event_payload) -> None:
    event_payload["articles"].append(
        {
            "news_id": 1002,
            "title": "事故原因仍在调查",
            "content": "报道表示事故原因仍需等待后续调查结果。",
            "source": "媒体乙",
        }
    )
    event = EventContext.model_validate(event_payload)
    service = QAService()

    result = service.answer(event, "这些报道如何描述事故原因？")

    assert service._classify(event, "这些报道如何描述事故原因？") == "evidence"
    assert "离线 Fake Provider 模式" in result.answer
    assert "事故原因仍在调查" in result.answer
    assert "找到报道" not in result.answer


def test_generic_news_words_do_not_select_specific_article(event_payload) -> None:
    event = EventContext.model_validate(event_payload)
    service = QAService()

    assert service._classify(event, "相关新闻对救援进展怎么说？") == "evidence"
    assert service._classify(event, "多篇新闻中关于救援有哪些说法？") == "multi_evidence"


def test_source_name_selects_specific_article(event_payload) -> None:
    event = EventContext.model_validate(event_payload)
    service = QAService()

    result = service.answer(event, "人民网那篇新闻说了什么？")

    assert service._classify(event, "人民网那篇新闻说了什么？") == "article"
    assert "人民网：救援工作正在进行" in result.answer


def test_quoted_title_selects_specific_article(event_payload) -> None:
    event = EventContext.model_validate(event_payload)
    service = QAService()

    result = service.answer(event, "《人民网：救援工作正在进行》这篇报道的内容是什么？")

    assert "组织救援" in result.answer


def test_many_articles_selects_relevant_context(event_payload) -> None:
    event_payload["articles"] = [
        {
            "news_id": 2001,
            "title": "无关的市场信息",
            "content": "市场今日保持平稳。",
            "source": "媒体甲",
        },
        {
            "news_id": 2002,
            "title": "救援通道已经打通",
            "content": "现场救援队伍已经打通关键通道。",
            "source": "媒体乙",
        },
        {
            "news_id": 2003,
            "title": "无关的体育信息",
            "content": "比赛按计划举行。",
            "source": "媒体丙",
        },
    ]
    event = EventContext.model_validate(event_payload)
    service = QAService(top_k=1)

    selected = service.select_relevant_articles(event, "救援通道进展如何？")
    result = service.answer(event, "救援通道进展如何？")

    assert [article.news_id for article in selected] == [2002]
    assert "救援通道已经打通" in result.answer
    assert "市场今日保持平稳" not in result.answer


def test_partial_analysis_does_not_crash(client, event_payload) -> None:
    event_payload["analysis"] = {}

    response = ask(client, event_payload, "为什么风险高？")

    assert response.status_code == 200
    assert "离线 Fake Provider 模式" in response.json()["answer"]


def test_greeting_with_empty_event_returns_provider_answer() -> None:
    provider = RecordingProvider("你好，我可以直接回答你的问题。")
    service = QAService(provider=provider)
    event = EventContext.model_validate({"event_id": 1, "analysis": {}})

    result = service.answer(event, "你好")

    assert result.answer == "你好，我可以直接回答你的问题。"
    assert len(provider.prompts) == 1
    assert "你好" in provider.prompts[0].user_prompt
    assert "当前信息不足" not in result.answer


def test_missing_risk_level_returns_provider_answer(event_payload) -> None:
    event_payload["analysis"].pop("risk_level")
    provider = RecordingProvider("现有材料可用于讨论风险，但没有上游风险等级。")
    service = QAService(provider=provider)
    event = EventContext.model_validate(event_payload)

    result = service.answer(event, "请分析这个事件的风险")

    assert result.answer == "现有材料可用于讨论风险，但没有上游风险等级。"
    assert len(provider.prompts) == 1
    assert "请分析这个事件的风险" in provider.prompts[0].user_prompt
    assert "某地发生事故并开展救援" in provider.prompts[0].user_prompt


def test_unrelated_question_returns_provider_answer(event_payload) -> None:
    provider = RecordingProvider("你好，这是模型对该问题的直接回应。")
    service = QAService(provider=provider)
    event = EventContext.model_validate(event_payload)

    result = service.answer(event, "你好")

    assert result.answer == "你好，这是模型对该问题的直接回应。"
    assert len(provider.prompts) == 1


def test_complete_risk_data_keeps_deterministic_answer(event_payload) -> None:
    provider = RecordingProvider("不应被调用")
    service = QAService(provider=provider)
    event = EventContext.model_validate(event_payload)

    result = service.answer(event, "为什么风险高？")

    assert "上游分析结果显示当前风险等级为“高”" in result.answer
    assert provider.prompts == []


def test_empty_summary_falls_back_to_articles(client, event_payload) -> None:
    event_payload["summary"] = ""

    response = ask(client, event_payload, "简单介绍一下这个事件")

    answer = response.json()["answer"]
    assert "某地发生事故并开展救援" in answer
    assert "组织救援" in answer
