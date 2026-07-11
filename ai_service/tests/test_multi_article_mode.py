from app.llm.base import LLMProvider
from app.llm.fake_provider import FakeLLMProvider
from app.llm.prompts import PromptBundle
from app.schemas.event import EventContext
from app.services.qa_service import QAService


class CapturingProvider(LLMProvider):
    name = "deepseek"

    def __init__(self, answer: str = "模型答案") -> None:
        self.answer = answer
        self.prompt: PromptBundle | None = None

    def generate(self, prompt: PromptBundle) -> str:
        self.prompt = prompt
        return self.answer


def two_article_event() -> EventContext:
    return EventContext.model_validate(
        {
            "event_id": 12,
            "title": "事故调查与救援",
            "summary": "事件背景摘要。",
            "update_time": "2026-07-12 09:00:00",
            "articles": [
                {
                    "news_id": 1002,
                    "title": "救援工作进展",
                    "content": "救援工作已经展开，目前尚无最终调查结论。",
                    "source": "媒体乙",
                    "publish_time": "2026-07-12 11:00:00",
                },
                {
                    "news_id": 1001,
                    "title": "现场情况记录",
                    "content": "现场处置工作正在进行，具体原因仍在调查。",
                    "source": "媒体甲",
                    "publish_time": "2026-07-12 10:00:00",
                },
            ],
            "analysis": {"keywords": ["救援", "调查"]},
        }
    )


def test_multi_article_question_includes_all_valid_articles_in_prompt() -> None:
    event = two_article_event()
    provider = CapturingProvider()
    service = QAService(provider=provider, top_k=5)

    service.answer(event, "综合当前两篇报道，按照报道发布时间说明已知进展。")

    assert provider.prompt is not None
    assert "news_id: 1001" in provider.prompt.user_prompt
    assert "news_id: 1002" in provider.prompt.user_prompt
    assert "现场处置工作正在进行" in provider.prompt.user_prompt
    assert "救援工作已经展开" in provider.prompt.user_prompt


def test_two_articles_below_top_k_are_both_selected() -> None:
    event = two_article_event()
    service = QAService(provider=FakeLLMProvider(), top_k=5)

    selected = service.select_relevant_articles(event, "综合当前两篇报道说明进展")

    assert [article.news_id for article in selected] == [1001, 1002]


def test_low_relevance_first_article_is_not_dropped_in_multi_mode() -> None:
    event = two_article_event()
    event.articles[1].title = "一般情况记录"
    event.articles[1].content = "现场处置工作正在进行。"
    service = QAService(provider=FakeLLMProvider(), top_k=5)

    selected = service.select_relevant_articles(event, "综合两篇报道说明救援工作")

    assert {article.news_id for article in selected} == {1001, 1002}


def test_multi_articles_are_sorted_only_by_publish_time() -> None:
    event = two_article_event()
    event.update_time = "2020-01-01 00:00:00"
    service = QAService(provider=FakeLLMProvider(), top_k=5)

    selected = service.select_relevant_articles(event, "按照时间顺序分别说明两篇报道")

    assert [article.publish_time for article in selected] == [
        "2026-07-12 10:00:00",
        "2026-07-12 11:00:00",
    ]


def test_multiple_explicit_news_ids_are_all_included_even_above_top_k() -> None:
    event = two_article_event()
    service = QAService(provider=FakeLLMProvider(), top_k=1)

    selected = service.select_relevant_articles(event, "请比较 news_id=1001、1002")

    assert [article.news_id for article in selected] == [1001, 1002]


def test_repeated_news_id_syntax_answers_every_requested_article() -> None:
    event = two_article_event()
    service = QAService(provider=FakeLLMProvider(), top_k=1)

    answer = service.answer(
        event,
        "请分别说明news_id=1001和news_id=1002各自提供了什么信息，然后总结两篇报道。",
    ).answer

    assert "news_id=1001" in answer
    assert "news_id=1002" in answer
    assert "现场处置工作正在进行" in answer
    assert "救援工作已经展开" in answer


def test_extracts_all_repeated_news_ids() -> None:
    question = "分别说明news_id=1001和news_id=1002的内容"

    assert QAService._extract_news_ids(question) == ["1001", "1002"]


def test_multiple_news_id_answer_does_not_return_after_first_article() -> None:
    event = two_article_event()
    service = QAService(provider=FakeLLMProvider(), top_k=1)

    answer = service.answer(event, "分别说明 news_id=1002 和 news_id=1001").answer

    assert answer.count("该文章明确提及") == 2
    assert answer.index("news_id=1001") < answer.index("news_id=1002")
    assert "简短综合" in answer


def test_missing_requested_news_id_keeps_existing_article_answer() -> None:
    event = two_article_event()
    service = QAService(provider=FakeLLMProvider(), top_k=1)

    answer = service.answer(event, "分别说明 news_id=1001 和 news_id=9999").answer

    assert "news_id=1001" in answer
    assert "现场处置工作正在进行" in answer
    assert "未找到" in answer
    assert "news_id=9999" in answer


def test_single_news_id_still_returns_only_target_article() -> None:
    event = two_article_event()
    service = QAService(provider=FakeLLMProvider(), top_k=5)

    result = service.answer(event, "news_id=1001 这篇文章说了什么？")

    assert "现场处置工作正在进行" in result.answer
    assert "救援工作已经展开" not in result.answer


def test_final_answer_hides_internal_field_names() -> None:
    event = two_article_event()
    provider = CapturingProvider(
        "is_official、account_type、source_type字段均为空；"
        "event.summary 没有信息；provider_name 使用 top_k 和 article_max_chars 处理 "
        "PromptBundle 与 EventContext。"
    )
    service = QAService(provider=provider, top_k=5)

    answer = service.answer(event, "综合两篇报道说明进展").answer

    for internal_name in (
        "is_official",
        "account_type",
        "source_type",
        "event.summary",
        "provider_name",
        "article_max_chars",
        "top_k",
        "PromptBundle",
        "EventContext",
    ):
        assert internal_name not in answer
    assert "当前输入未提供足够的来源身份信息" in answer


def test_unverified_answer_does_not_use_proven_language() -> None:
    event = two_article_event()
    provider = CapturingProvider("事实证明事故原因已经证实，并得到官方确认。")
    service = QAService(provider=provider, top_k=5)

    answer = service.answer(event, "综合两篇报道说明事故原因").answer

    assert "事实证明" not in answer
    assert "已经证实" not in answer
    assert "官方确认" not in answer
    assert "现有材料" in answer


def test_single_media_statement_is_not_labeled_as_verified_fact() -> None:
    event = two_article_event()
    event.articles = [event.articles[0]]
    service = QAService(provider=FakeLLMProvider(), top_k=5)

    answer = service.answer(event, "这篇报道对调查结论怎么说？").answer

    assert "救援工作进展" in answer
    assert "尚无最终调查结论" in answer
    assert "已确认事实" not in answer
    assert "已经证实" not in answer
