import json

import pytest

import app.services.verification_service as verification_service_module
from app.core.config import Settings
from app.llm.base import LLMProvider
from app.llm.prompt_types import PromptBundle
from app.main import app
from app.schemas.event import EventContext
from app.services.credibility_assessment_service import CredibilityAssessmentService
from app.services.source_registry import (
    SourceProfile,
    StaticSourceRegistry,
    project_source_registry,
)
from app.services.source_traceability import SourceTraceabilityEvaluator
from app.services.verification_explanation import VerificationExplanationService
from app.services.verification_service import VerificationService, get_verification_service


class StubProvider(LLMProvider):
    name = "stub"

    def __init__(self, output="", error: Exception | None = None) -> None:
        self.output = output
        self.error = error
        self.calls = 0
        self.last_prompt = None

    def generate(self, prompt: PromptBundle) -> str:
        self.calls += 1
        self.last_prompt = prompt
        if self.error is not None:
            raise self.error
        return self.output


def article(news_id, content, source, *, title="事件报道", url=None, **extra):
    return {
        "news_id": news_id,
        "title": title,
        "content": content,
        "source": source,
        "url": url or f"https://source-{news_id}.example.com/{news_id}",
        "publish_time": "2026-07-13 10:00:00",
        "platform": "新闻网站",
        **extra,
    }


def event(items) -> EventContext:
    return EventContext.model_validate(
        {
            "event_id": 1,
            "title": "事故情况核验",
            "summary": "该摘要仅作为背景。",
            "articles": items,
            "analysis": {},
        }
    )


def supported_items():
    return [
        article(1, "事故造成3人受伤。", "目标媒体"),
        article(2, "现场信息显示共有3人受伤，正在接受治疗。", "滨江发布"),
        article(3, "另一份报道提到事故中3名人员受伤。", "海州电视台"),
    ]


def contradicted_items():
    return [
        article(1, "事故造成3人受伤。", "目标媒体"),
        article(2, "现场消息称事故造成3人死亡。", "海州市应急管理局"),
        article(3, "另一报道确认事故中有3人死亡。", "海州广播电视台"),
    ]


def conflicting_items():
    return [
        article(1, "事故造成3人受伤。", "目标媒体"),
        article(2, "现场信息显示共有3人受伤，正在接受治疗。", "来源甲"),
        article(3, "事故造成3人死亡。", "来源乙"),
    ]


def model_output(response, *, source_phrase="来源角色只用于说明材料背景，不替代事实证据"):
    claim = response.claim_results[0]
    evidence = [
        {
            "news_id": item.news_id,
            "source": item.source,
            "quote": item.quote,
            "explanation": "该逐字引用用于说明当前证据关系。",
        }
        for item in [*claim.evidence, *claim.context_evidence]
    ]
    return {
        "headline": "具体证据解释",
        "conclusion": "模型不能覆盖既有结论。",
        "why": [
            {
                "type": "source_identity",
                "title": "来源身份与证据分开理解",
                "explanation": source_phrase,
                "claim_ids": [claim.claim_id],
                "evidence_refs": [],
            }
        ],
        "claim_explanations": [
            {
                "claim_id": claim.claim_id,
                "claim": claim.claim,
                "conclusion": "模型不能修改主张结论。",
                "explanation": "解释直接绑定已有主张和逐字证据。",
                "evidence": evidence,
            }
        ],
        "score_explanation": "证据、来源和语言风险使用既有明细解释。",
        "limitations": ["解释范围仅限当前输入文章。"],
    }


def explained_service(items, provider, assessment_service=None):
    baseline_service = VerificationService(
        credibility_assessment_service=assessment_service or CredibilityAssessmentService()
    )
    baseline = baseline_service.verify(event(items), 1)
    explanation = VerificationExplanationService(provider)
    service = VerificationService(
        credibility_assessment_service=assessment_service or CredibilityAssessmentService(),
        explanation_service=explanation,
    )
    return baseline, service.verify(event(items), 1)


def without_explanation(response):
    payload = response.model_dump(mode="json")
    payload.pop("ai_explanation")
    payload.pop("display_result")
    return payload


def test_explanation_can_be_explicitly_disabled(monkeypatch) -> None:
    response = VerificationService().verify(event(supported_items()), 1)

    assert response.ai_explanation is None
    assert response.display_result is None
    monkeypatch.setenv("AI_VERIFY_EXPLANATION_ENABLED", "false")
    assert Settings(llm_provider="fake").verify_explanation_enabled is False
    assert Settings(llm_provider="fake").verify_explanation_article_max_chars == 6000


def test_explanation_is_enabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("AI_VERIFY_EXPLANATION_ENABLED", raising=False)

    assert Settings(llm_provider="fake").verify_explanation_enabled is True


def test_default_factory_returns_fallback_explanation_in_fake_mode(monkeypatch) -> None:
    monkeypatch.setattr(
        verification_service_module,
        "settings",
        Settings(llm_provider="fake", verify_explanation_enabled=True),
    )
    get_verification_service.cache_clear()
    try:
        service = get_verification_service()
        response = service.verify(event(supported_items()), 1)
    finally:
        get_verification_service.cache_clear()

    assert service.explanation_service is not None
    assert response.ai_explanation is not None
    assert response.ai_explanation.status == "fallback"
    assert response.display_result is not None


def test_default_factory_uses_project_crawler_source_registry(monkeypatch) -> None:
    monkeypatch.setattr(
        verification_service_module,
        "settings",
        Settings(llm_provider="fake", verify_explanation_enabled=True),
    )
    get_verification_service.cache_clear()
    items = [
        article(
            1,
            "事故造成2人受伤。",
            "人民网",
            url="http://society.people.com.cn/n1/2026/0713/c1008-1.html",
        )
    ]
    try:
        response = get_verification_service().verify(event(items), 1)
    finally:
        get_verification_service.cache_clear()

    source = response.credibility_assessment.source_assessment
    assert source.status == "verified"
    assert source.domain_match is True
    assert source.canonical_name == "人民网"
    assert source.source_category == "官方新闻媒体"


def test_enabled_explanation_uses_specific_verified_evidence() -> None:
    baseline = VerificationService().verify(event(supported_items()), 1)
    provider = StubProvider(json.dumps(model_output(baseline), ensure_ascii=False))

    _, response = explained_service(supported_items(), provider)

    explanation = response.ai_explanation
    assert explanation.status == "success"
    assert explanation.analysis_method == "llm"
    assert provider.calls == 1
    assert {item.source for item in explanation.claim_explanations[0].evidence} == {
        "滨江发布",
        "海州电视台",
    }
    assert all("3" in item.quote and "受伤" in item.quote for item in explanation.claim_explanations[0].evidence)
    assert "<untrusted_event_and_articles>" in provider.last_prompt.user_prompt
    assert "不得修改、推翻或重新计算" in provider.last_prompt.system_prompt
    assert "evidence_source_context" in provider.last_prompt.user_prompt
    assert response.display_result is not None


def test_fenced_json_with_surrounding_text_and_harmless_extras_is_accepted() -> None:
    items = supported_items()
    baseline = VerificationService().verify(event(items), 1)
    output = model_output(baseline)
    output["presentation_note"] = "仅用于组织展示"
    output["claim_explanations"][0]["evidence"][0]["display_hint"] = "重点证据"
    raw = (
        "以下是结构化说明：\n```json\n"
        + json.dumps(output, ensure_ascii=False)
        + "\n```\n说明结束。"
    )

    _, response = explained_service(items, StubProvider(raw))

    assert response.ai_explanation.status == "success"
    assert response.ai_explanation.analysis_method == "llm"
    assert response.ai_explanation.headline == output["headline"]


def test_partial_model_output_uses_field_level_fallback() -> None:
    items = supported_items()
    output = {
        "headline": "多篇材料形成交叉印证",
        "conclusion": "当前两个独立来源与目标主张一致，但结论仅限现有材料。",
        "claim_explanations": {
            "claim_id": 1,
            "explanation": "两个独立来源分别给出了相同的伤亡人数。",
        },
        "limitations": "说明仅基于当前事件中的新闻材料。",
    }

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
    )

    explanation = response.ai_explanation
    assert explanation.status == "success"
    assert explanation.analysis_method == "llm"
    assert explanation.headline == output["headline"]
    assert explanation.conclusion == output["conclusion"]
    assert explanation.why
    assert explanation.claim_explanations[0].explanation == output[
        "claim_explanations"
    ]["explanation"]
    assert len(explanation.claim_explanations[0].evidence) == 2
    assert explanation.limitations == [
        "本次基于当前事件内的多篇新闻进行交叉比较，重点呈现共同信息、差异和来源关系。"
    ]


def test_missing_evidence_refs_are_derived_from_verified_claim() -> None:
    items = supported_items()
    baseline = VerificationService().verify(event(items), 1)
    output = model_output(baseline)
    output["why"][0].update(
        {
            "type": "evidence",
            "title": "两条独立证据相互印证",
            "explanation": "两个独立来源对目标伤亡人数给出一致表述。",
            "claim_ids": [1],
            "evidence_refs": [],
        }
    )

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
    )

    reason = response.ai_explanation.why[0]
    assert response.ai_explanation.status == "success"
    assert reason.title == "两条独立证据相互印证"
    assert set(reason.evidence_refs) == {2, 3}


@pytest.mark.parametrize(
    ("items", "verdict", "sources"),
    [
        (supported_items(), "supported", {"滨江发布", "海州电视台"}),
        (
            contradicted_items(),
            "contradicted",
            {"海州市应急管理局", "海州广播电视台"},
        ),
    ],
)
def test_fallback_names_sources_and_quotes(items, verdict, sources) -> None:
    provider = StubProvider(error=TimeoutError())

    _, response = explained_service(items, provider)

    explanation = response.ai_explanation
    assert response.overall_verdict == verdict
    assert explanation.status == "fallback"
    evidence = explanation.claim_explanations[0].evidence
    assert {item.source for item in evidence} == sources
    assert all(item.quote for item in evidence)


def test_conflicting_explanation_preserves_support_and_contradiction() -> None:
    provider = StubProvider(error=ConnectionError())

    _, response = explained_service(conflicting_items(), provider)

    explanation = response.ai_explanation
    assert response.overall_verdict == "conflicting"
    assert "支持与反驳材料并存" in explanation.conclusion
    evidence_text = " ".join(
        item.explanation for item in explanation.claim_explanations[0].evidence
    )
    assert "支持" in evidence_text
    assert "反驳" in evidence_text


def test_single_article_fallback_describes_material_instead_of_repeating_evidence_gap() -> None:
    items = [article(1, "现场有2人受伤。", "目标媒体")]

    _, response = explained_service(items, StubProvider(output="not-json"))

    explanation = response.ai_explanation
    assert response.overall_verdict == "insufficient_evidence"
    assert "可核验的事实要素" in explanation.claim_explanations[0].explanation
    assert "尚待交叉核验" in explanation.conclusion
    assert "没有其他独立新闻" not in json.dumps(
        explanation.model_dump(mode="json"),
        ensure_ascii=False,
    )


def test_single_article_uses_llm_source_language_and_content_analysis() -> None:
    items = [
        article(
            1,
            "事故造成2人受伤。",
            "人民网",
            url="http://society.people.com.cn/n1/2026/0713/c1008-1.html",
        )
    ]
    assessment_service = CredibilityAssessmentService(
        source_evaluator=SourceTraceabilityEvaluator(project_source_registry())
    )
    baseline = VerificationService(
        credibility_assessment_service=assessment_service
    ).verify(event(items), 1)
    assert baseline.credibility_assessment.source_assessment.status == "verified"
    assert (
        baseline.credibility_assessment.source_assessment.source_category
        == "官方新闻媒体"
    )
    output = {
        "headline": "人民网来源可追溯，正文陈述具体且克制",
        "conclusion": (
            "人民网的来源名称与对应站点一致，正文对伤情作出具体陈述；"
            "当前仅能评估材料本身，事实主张尚待交叉核验。"
        ),
        "why": [
            {
                "type": "source_quality",
                "title": "来源身份具有明确可追溯性",
                "explanation": (
                    "人民网的来源名称与对应站点一致，属于官方新闻媒体；"
                    "该因素支持材料溯源，但不直接证明正文事实。"
                ),
                "claim_ids": [],
                "evidence_refs": [],
            },
            {
                "type": "language",
                "title": "正文语气较为克制",
                "explanation": (
                    "标题和正文没有使用煽动性或绝对化措辞，表述集中在具体伤情。"
                ),
                "claim_ids": [],
                "evidence_refs": [],
            },
            {
                "type": "claim_quality",
                "title": "事实主张具体",
                "explanation": (
                    "正文明确陈述“事故造成2人受伤”，对象和伤情清楚，"
                    "便于后续针对同一主张继续核验。"
                ),
                "claim_ids": [1],
                "evidence_refs": [],
            },
        ],
        "claim_explanations": [
            {
                "claim_id": 1,
                "claim": baseline.claim_results[0].claim,
                "conclusion": "该具体主张已进入核验范围，尚待交叉核验。",
                "explanation": (
                    "文章直接给出伤情数量和类型，主张边界明确，"
                    "可以与后续公开信息逐项比对。"
                ),
                "evidence": [],
            }
        ],
        "score_explanation": "证据、来源和语言风险仅按既有评分明细解释。",
        "limitations": ["当前只有单篇材料，尚未完成跨来源核验。"],
    }
    provider = StubProvider(json.dumps(output, ensure_ascii=False))

    _, response = explained_service(items, provider, assessment_service)

    assert response.ai_explanation.status == "success"
    assert response.ai_explanation.headline == output["headline"]
    assert provider.last_prompt is not None
    assert "[本次分析重点]单篇新闻材料分析" in provider.last_prompt.user_prompt
    assert '"confirmed": true' in provider.last_prompt.user_prompt
    assert '"classification": "官方新闻媒体"' in provider.last_prompt.user_prompt
    assert response.display_result.reasons[:3] == [
        item["explanation"] for item in output["why"]
    ]
    rendered = json.dumps(response.display_result.model_dump(mode="json"), ensure_ascii=False)
    assert "没有其他独立新闻" not in rendered
    assert "现有独立证据不足" not in rendered
    assert rendered.count("未联网进行跨来源事实确认") == 1


def test_single_article_uses_dynamic_article_grounded_analysis_dimensions() -> None:
    items = [
        article(
            1,
            "该办法明确申请材料应当完整，并说明办理条件和适用对象。",
            "政策信息平台",
            title="某办法第17条办理规则解读",
        )
    ]
    baseline = VerificationService().verify(event(items), 1)
    claim = baseline.claim_results[0]
    output = {
        "headline": "第17条的办理要求表述清楚，适用边界仍需结合原文条款",
        "conclusion": (
            "文章清楚区分了办理条件和适用对象，正文可以帮助定位需要核对的规则。"
            "具体适用范围仍应结合办法原文，当前事实主张尚待交叉核验。"
        ),
        "why": [
            {
                "type": "claim_structure",
                "title": "核心主张边界清楚",
                "explanation": "正文分别说明申请材料、办理条件和适用对象，读者可以区分文章讨论的不同规则要素。",
                "claim_ids": [claim.claim_id],
                "evidence_refs": [],
            },
            {
                "type": "internal_consistency",
                "title": "标题与正文主题一致",
                "explanation": "标题聚焦第17条办理规则，正文也围绕办理要求展开，没有转向无关事件。",
                "claim_ids": [claim.claim_id],
                "evidence_refs": [],
            },
            {
                "type": "attribution",
                "title": "规则表述需要回到原文定位",
                "explanation": "文章把要求归于该办法，核验时应定位对应条款，确认解读没有扩大或缩小适用对象。",
                "claim_ids": [claim.claim_id],
                "evidence_refs": [],
            },
            {
                "type": "misreading_risk",
                "title": "摘要不能替代完整适用条件",
                "explanation": "办理条件通常需要结合上下文理解，引用文章结论时应保留适用对象和条件范围。",
                "claim_ids": [claim.claim_id],
                "evidence_refs": [],
            },
            {
                "type": "verification_path",
                "title": "后续核验路径具体",
                "explanation": "优先比对办法原文中的对应条款、定义和适用范围，再检查文章概括是否与原文一致。",
                "claim_ids": [claim.claim_id],
                "evidence_refs": [],
            },
        ],
        "claim_explanations": [
            {
                "claim_id": claim.claim_id,
                "claim": claim.claim,
                "conclusion": "该主张边界清楚，但具体适用范围尚待交叉核验。",
                "explanation": (
                    "文章把材料完整性、办理条件和适用对象作为同一规则的组成部分；"
                    "当前可以确认文章如何表述，后续应逐项对照办法原文。"
                ),
                "evidence": [],
            }
        ],
        "score_explanation": "确定性评分只解释现有来源、语言和证据维度。",
        "limitations": [
            "只有一篇新闻。",
            "缺少独立来源。",
            "未联网检索。",
        ],
    }
    provider = StubProvider(json.dumps(output, ensure_ascii=False))

    _, response = explained_service(items, provider)

    display = response.display_result
    assert display.analysis_mode == "single_article_audit"
    assert display.evidence_score_applicable is False
    assert len(display.analysis_sections) == 5
    assert len(display.claim_reviews) == len(baseline.claim_results)
    assert display.claim_reviews[0].explanation == output["claim_explanations"][0][
        "explanation"
    ]
    assert "第17条" in display.headline
    assert len(response.ai_explanation.limitations) == 1
    assert len(display.uncertainties) == 1
    rendered = json.dumps(display.model_dump(mode="json"), ensure_ascii=False)
    assert "只有一篇新闻" not in rendered
    assert "缺少独立来源" not in rendered
    assert provider.last_prompt is not None
    assert "不得预设固定领域" in provider.last_prompt.system_prompt
    assert "灵活选择5至8个相关维度" in provider.last_prompt.user_prompt


def test_model_cannot_change_verdict_or_existing_response_fields() -> None:
    items = supported_items()
    baseline = VerificationService().verify(event(items), 1)
    output = model_output(baseline)
    output["conclusion"] = "文章已经被永久证实为虚假。"
    output["claim_explanations"][0]["conclusion"] = "该主张已经被反驳。"
    provider = StubProvider(json.dumps(output, ensure_ascii=False))

    original, response = explained_service(items, provider)

    assert response.overall_verdict == "supported"
    assert response.ai_explanation.conclusion.startswith("当前输入中的多来源材料")
    assert response.ai_explanation.claim_explanations[0].conclusion == "该主张在当前输入材料中得到多来源支持。"
    assert without_explanation(response) == without_explanation(original)


def test_model_score_fields_are_ignored_without_discarding_safe_text() -> None:
    items = supported_items()
    baseline = VerificationService().verify(event(items), 1)
    output = model_output(baseline)
    output["risk_score"] = 0
    provider = StubProvider(json.dumps(output, ensure_ascii=False))

    original, response = explained_service(items, provider)

    assert response.ai_explanation.status == "success"
    assert response.ai_explanation.analysis_method == "llm"
    assert response.ai_explanation.headline == output["headline"]
    assert response.credibility_assessment.risk_score == original.credibility_assessment.risk_score


def test_model_cannot_introduce_new_score_number() -> None:
    items = supported_items()
    baseline = VerificationService().verify(event(items), 1)
    output = model_output(baseline)
    output["score_explanation"] = "模型另外给出999分。"

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
    )

    assert "999" not in response.ai_explanation.score_explanation
    assert response.ai_explanation.score_breakdown.total_risk_score == response.credibility_assessment.risk_score


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("news_id", 999),
        ("source", "伪造来源"),
        ("quote", "输入中不存在的伪造引用"),
    ],
)
def test_invalid_model_evidence_is_removed(field, value) -> None:
    items = supported_items()
    baseline = VerificationService().verify(event(items), 1)
    output = model_output(baseline)
    output["claim_explanations"][0]["evidence"][0][field] = value

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
    )

    evidence = response.ai_explanation.claim_explanations[0].evidence
    assert all(item.news_id != 999 for item in evidence)
    assert all(item.source != "伪造来源" for item in evidence)
    assert all(item.quote != "输入中不存在的伪造引用" for item in evidence)


def test_unknown_claim_id_and_evidence_reason_are_removed() -> None:
    items = supported_items()
    baseline = VerificationService().verify(event(items), 1)
    output = model_output(baseline)
    output["claim_explanations"].append(
        {
            "claim_id": 999,
            "claim": "伪造主张",
            "conclusion": "伪造结论",
            "explanation": "不应保留。",
            "evidence": [],
        }
    )
    output["why"].append(
        {
            "type": "evidence",
            "title": "伪造证据原因",
            "explanation": "没有合法证据引用。",
            "claim_ids": [999],
            "evidence_refs": [999],
        }
    )

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
    )

    assert all(item.claim_id != 999 for item in response.ai_explanation.claim_explanations)
    assert all(item.title != "伪造证据原因" for item in response.ai_explanation.why)


def test_unconfigured_source_authentication_cannot_be_called_confirmed_authority() -> None:
    items = supported_items()
    items[0]["author"] = "记者甲"
    baseline = VerificationService().verify(event(items), 1)
    source = baseline.credibility_assessment.source_assessment
    assert source.status == "unknown"
    assert source.registered_source is None
    output = model_output(baseline, source_phrase="权威来源已确认。")

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
    )

    rendered = json.dumps(response.ai_explanation.model_dump(mode="json"), ensure_ascii=False)
    assert "权威来源已确认" not in rendered


def test_confirmed_source_identity_can_be_used_without_proving_the_fact() -> None:
    items = supported_items()
    items[0].update(
        {
            "source": "测试日报",
            "url": "https://news.test.local/1",
        }
    )
    assessment_service = CredibilityAssessmentService(
        source_evaluator=SourceTraceabilityEvaluator(
            StaticSourceRegistry(
                (SourceProfile(canonical_name="测试日报", verified_domains=("news.test.local",)),)
            )
        )
    )
    baseline = VerificationService(
        credibility_assessment_service=assessment_service
    ).verify(event(items), 1)
    assert baseline.credibility_assessment.source_assessment.status == "verified"
    output = model_output(baseline, source_phrase="来源身份已经确认，但这不替代事实证据。")

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
        assessment_service,
    )

    assert response.ai_explanation.status == "success"
    rendered = json.dumps(response.ai_explanation.model_dump(mode="json"), ensure_ascii=False)
    assert "来源身份已经确认" in rendered
    assert "不替代事实证据" in rendered
    assert "注册表" not in rendered


def test_verified_news_portal_cannot_be_called_official_media() -> None:
    items = supported_items()
    items[0].update(
        {
            "source": "测试门户",
            "url": "https://news.portal.test/1",
        }
    )
    assessment_service = CredibilityAssessmentService(
        source_evaluator=SourceTraceabilityEvaluator(
            StaticSourceRegistry(
                (
                    SourceProfile(
                        canonical_name="测试门户",
                        verified_domains=("news.portal.test",),
                        source_category="新闻门户",
                        ownership_type="商业媒体平台",
                    ),
                )
            )
        )
    )
    baseline = VerificationService(
        credibility_assessment_service=assessment_service
    ).verify(event(items), 1)
    output = model_output(
        baseline,
        source_phrase="测试门户属于官方新闻媒体，因此正文内容属实。",
    )

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
        assessment_service,
    )

    rendered = json.dumps(response.ai_explanation.model_dump(mode="json"), ensure_ascii=False)
    assert "官方新闻媒体" not in rendered
    assert "内容属实" not in rendered


def test_confirmed_evidence_source_identity_can_be_explained_safely() -> None:
    items = supported_items()
    assessment_service = CredibilityAssessmentService(
        source_evaluator=SourceTraceabilityEvaluator(
            StaticSourceRegistry(
                (
                    SourceProfile(
                        canonical_name="滨江发布",
                        verified_domains=("source-2.example.com",),
                    ),
                )
            )
        )
    )
    baseline = VerificationService(
        credibility_assessment_service=assessment_service
    ).verify(event(items), 1)
    output = model_output(baseline)
    output["claim_explanations"][0]["evidence"][0]["explanation"] = (
        "滨江发布的来源身份已确认，其逐字引用与目标主张一致。"
    )

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
        assessment_service,
    )

    assessment = next(
        item for item in response.evidence_source_assessments if item.news_id == 2
    )
    evidence = next(
        item
        for item in response.ai_explanation.claim_explanations[0].evidence
        if item.news_id == 2
    )
    assert assessment.identity_status == "verified"
    assert assessment.domain_match is True
    assert "来源身份已确认" in evidence.explanation
    assert "逐字引用与目标主张一致" in evidence.explanation


def test_score_breakdown_uses_deterministic_weights() -> None:
    _, response = explained_service(supported_items(), StubProvider(output="not-json"))
    breakdown = response.ai_explanation.score_breakdown
    assessment = response.credibility_assessment

    assert breakdown.evidence_contribution == round(breakdown.evidence_risk * 0.60, 1)
    assert breakdown.source_contribution == round(breakdown.source_risk * 0.25, 1)
    assert breakdown.language_contribution == round(breakdown.language_risk * 0.15, 1)
    assert breakdown.total_risk_score == assessment.risk_score


@pytest.mark.parametrize("provider", [StubProvider(error=TimeoutError()), StubProvider(output="not-json")])
def test_api_returns_200_and_fallback_when_explanation_fails(client, provider) -> None:
    service = VerificationService(
        explanation_service=VerificationExplanationService(provider)
    )
    app.dependency_overrides[get_verification_service] = lambda: service
    try:
        response = client.post(
            "/ai/verify",
            json={"event": event(supported_items()).model_dump(mode="json"), "target_news_id": 1},
        )
    finally:
        app.dependency_overrides.pop(get_verification_service, None)

    assert response.status_code == 200
    assert response.json()["ai_explanation"]["status"] == "fallback"
    assert response.json()["display_result"] is not None
    assert provider.calls == 1


def test_supported_display_lists_two_sources_and_exact_quotes() -> None:
    items = supported_items()
    baseline = VerificationService().verify(event(items), 1)
    output = model_output(baseline)
    output["conclusion"] = (
        "目标文章中的3人受伤主张与两个独立来源的材料表述一致，当前材料未见直接冲突。"
    )
    output["claim_explanations"][0]["conclusion"] = (
        "3人受伤主张得到两个独立来源支持。"
    )
    for item in output["claim_explanations"][0]["evidence"]:
        item["explanation"] = (
            f"{item['source']}原文“{item['quote']}”明确给出相同伤亡人数，"
            "因此支持目标主张。"
        )

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
    )

    display = response.display_result
    assert response.ai_explanation.status == "success"
    assert display.conclusion == output["conclusion"]
    assert {card.source for card in display.evidence_cards} == {
        "滨江发布",
        "海州电视台",
    }
    assert all(card.quote for card in display.evidence_cards)
    assert all(card.source in card.explanation for card in display.evidence_cards)


def test_contradicted_display_contains_specific_refuting_evidence() -> None:
    _, response = explained_service(
        contradicted_items(),
        StubProvider(error=TimeoutError()),
    )

    cards = response.display_result.evidence_cards
    assert response.overall_verdict == "contradicted"
    assert cards
    assert all(card.stance == "contradicts" for card in cards)
    assert all("反驳" in card.explanation for card in cards)
    assert {card.source for card in cards} == {
        "海州市应急管理局",
        "海州广播电视台",
    }


def test_conflicting_display_contains_support_and_refutation() -> None:
    _, response = explained_service(
        conflicting_items(),
        StubProvider(error=ConnectionError()),
    )

    stances = {card.stance for card in response.display_result.evidence_cards}
    assert response.overall_verdict == "conflicting"
    assert {"supports", "contradicts"} <= stances


def test_single_article_display_prioritizes_material_analysis() -> None:
    items = [article(1, "现场有2人受伤。", "目标媒体")]

    _, response = explained_service(items, StubProvider(output="not-json"))

    assert response.display_result.evidence_cards == []
    assert any("语气相对克制" in item for item in response.display_result.reasons)
    assert all(
        "没有其他独立新闻" not in item
        for item in response.display_result.reasons
    )


def test_display_deduplicates_quotes_and_keeps_one_card_per_article() -> None:
    _, response = explained_service(
        supported_items(),
        StubProvider(error=TimeoutError()),
    )

    cards = response.display_result.evidence_cards
    assert len({card.quote for card in cards}) == len(cards)
    assert len({str(card.news_id) for card in cards}) == len(cards)


def test_government_metadata_does_not_equal_registered_identity() -> None:
    items = supported_items()
    items[1].update(
        {
            "source_type": "government",
            "account_type": "政务发布",
            "is_official": True,
            "url": "https://notice.example.test/2",
        }
    )

    _, response = explained_service(items, StubProvider(error=TimeoutError()))

    assessment = next(
        item for item in response.evidence_source_assessments if item.news_id == 2
    )
    card = next(item for item in response.display_result.evidence_cards if item.news_id == 2)
    assert assessment.source_role == "government_notice"
    assert assessment.registered_source is None
    assert assessment.domain_match is None
    assert assessment.identity_status == "unknown"
    assert assessment.explanation == "输入中标记为政务发布，具有来源名称、链接、发布时间。"
    assert card.source_description == "政务发布"
    assert "注册表" not in card.source_description


def test_explanation_prompt_omits_source_authentication_state() -> None:
    items = supported_items()
    items[1].update(
        {
            "source_type": "government",
            "account_type": "政务发布",
            "is_official": True,
        }
    )
    baseline = VerificationService().verify(event(items), 1)
    provider = StubProvider(json.dumps(model_output(baseline), ensure_ascii=False))

    explained_service(items, provider)

    prompt = provider.last_prompt.system_prompt + provider.last_prompt.user_prompt
    assert "registered_source" not in prompt
    assert "domain_match" not in prompt
    assert "identity_status" not in prompt
    assert "本地来源注册表" not in prompt
    assert '"source_role": "government_notice"' in prompt
    assert '"is_official_input": true' in prompt
    assert '"metadata_coverage"' not in prompt
    assert '"source_metadata_coverage"' not in prompt


def test_optional_provenance_absence_is_not_user_visible() -> None:
    items = supported_items()
    baseline = VerificationService().verify(event(items), 1)
    output = model_output(
        baseline,
        source_phrase="当前缺少作者、账号类型和引用链接，来源元数据不足。",
    )
    output["limitations"].append("未提供被引新闻和重复组信息。")
    output["claim_explanations"][0]["evidence"][0]["explanation"] = (
        "由于缺少转载关系，暂时无法说明这段材料。"
    )

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
    )

    rendered = json.dumps(
        {
            "ai_explanation": response.ai_explanation.model_dump(mode="json"),
            "display_result": response.display_result.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )
    for phrase in (
        "缺少作者",
        "账号类型",
        "引用链接",
        "来源元数据不足",
        "未提供被引新闻",
        "重复组信息",
        "缺少转载关系",
    ):
        assert phrase not in rendered


def test_unknown_optional_source_role_uses_neutral_user_text() -> None:
    items = supported_items()
    items[1]["platform"] = ""

    _, response = explained_service(items, StubProvider(error=TimeoutError()))

    assessment = next(
        item for item in response.evidence_source_assessments if item.news_id == 2
    )
    card = next(item for item in response.display_result.evidence_cards if item.news_id == 2)
    assert assessment.source_role == "unknown"
    assert assessment.explanation == "输入中标记为新闻来源，具有来源名称、链接、发布时间。"
    assert card.source_description == "新闻来源"
    rendered = json.dumps(
        {
            "assessment": assessment.model_dump(mode="json"),
            "card": card.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )
    assert "来源角色未明确" not in rendered
    assert "来源类型未明确" not in rendered
    assert "来源元数据较少" not in rendered


def test_display_uses_generic_scope_limitations_without_registry_text() -> None:
    _, response = explained_service(
        supported_items(),
        StubProvider(error=TimeoutError()),
    )

    rendered = json.dumps(response.display_result.model_dump(mode="json"), ensure_ascii=False)
    assert "本次共比较3篇事件材料" in rendered
    assert "没有联网检索" not in rendered
    assert "结论对应当前材料范围" in rendered
    assert "注册表" not in rendered
    assert "域名匹配" not in rendered


def test_internal_source_role_fields_are_not_exposed_in_user_text() -> None:
    items = supported_items()
    items[1].update(
        {
            "source_type": "government_notice",
            "account_type": "政务账号",
            "is_official": True,
        }
    )
    baseline = VerificationService().verify(event(items), 1)
    output = model_output(baseline)
    output["why"][0]["explanation"] = (
        "滨江发布的source_role为government_notice，海州电视台为news_media。"
    )
    output["claim_explanations"][0]["evidence"][0]["explanation"] = (
        "该来源为政务发布（government_notice），属于官方通报。"
        "该来源被标记为is_official_input，仅表示上游输入标记，不构成权威性证明。"
    )
    output["claim_explanations"][0]["evidence"][1]["explanation"] = (
        "该来源为新闻媒体（news_media），其原文支持目标主张。"
    )

    _, response = explained_service(
        items,
        StubProvider(json.dumps(output, ensure_ascii=False)),
    )

    rendered = json.dumps(
        {
            "ai_explanation": response.ai_explanation.model_dump(mode="json"),
            "display_result": response.display_result.model_dump(mode="json"),
        },
        ensure_ascii=False,
    )
    for internal_name in (
        "government_notice",
        "news_media",
        "is_official_input",
        "source_role",
        "account_type",
        "source_type",
    ):
        assert internal_name not in rendered
    assert "政务发布" in rendered
    assert "新闻媒体" in rendered


def test_new_display_fields_do_not_change_existing_verification_result() -> None:
    items = supported_items()
    original = VerificationService().verify(event(items), 1)
    _, explained = explained_service(items, StubProvider(error=TimeoutError()))

    original_payload = original.model_dump(mode="json")
    explained_payload = explained.model_dump(mode="json")
    for payload in (original_payload, explained_payload):
        payload.pop("ai_explanation")
        payload.pop("display_result")

    assert explained_payload == original_payload
