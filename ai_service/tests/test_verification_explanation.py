import json

import pytest

import app.services.verification_service as verification_service_module
from app.core.config import Settings
from app.llm.base import LLMProvider
from app.llm.prompt_types import PromptBundle
from app.main import app
from app.schemas.event import EventContext
from app.services.credibility_assessment_service import CredibilityAssessmentService
from app.services.source_registry import SourceProfile, StaticSourceRegistry
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


def test_fallback_limits_claim_explanation_evidence_to_twenty() -> None:
    context = event(supported_items())
    baseline = VerificationService().verify(context, 1)
    claim = baseline.claim_results[0]
    evidence = [
        claim.evidence[0].model_copy(update={"news_id": news_id})
        for news_id in range(2, 41)
    ]
    oversized_claim = claim.model_copy(
        update={"evidence": evidence, "context_evidence": []}
    )
    oversized_response = baseline.model_copy(
        update={"claim_results": [oversized_claim]}
    )

    explanation = VerificationExplanationService(
        StubProvider(output="not-json")
    ).explain(context, context.articles[0], oversized_response)

    assert len(oversized_claim.evidence) == 39
    assert len(explanation.claim_explanations[0].evidence) == 20
    assert [item.news_id for item in explanation.claim_explanations[0].evidence] == list(
        range(2, 22)
    )
    assert explanation.why[0].evidence_refs == list(range(2, 22))


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


def test_single_article_says_there_is_no_independent_evidence() -> None:
    items = [article(1, "现场有2人受伤。", "目标媒体")]

    _, response = explained_service(items, StubProvider(output="not-json"))

    explanation = response.ai_explanation
    assert response.overall_verdict == "insufficient_evidence"
    assert "没有其他独立新闻" in explanation.claim_explanations[0].explanation
    assert "不等于文章已经被证明虚假" in explanation.conclusion


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


def test_model_score_fields_trigger_safe_fallback_without_changing_risk() -> None:
    items = supported_items()
    baseline = VerificationService().verify(event(items), 1)
    output = model_output(baseline)
    output["risk_score"] = 0
    provider = StubProvider(json.dumps(output, ensure_ascii=False))

    original, response = explained_service(items, provider)

    assert response.ai_explanation.status == "fallback"
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


def test_registered_identity_is_not_exposed_in_user_explanation() -> None:
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
    assert "来源身份已经确认" not in rendered
    assert "注册表" not in rendered


def test_registered_evidence_source_remains_technical_but_not_user_visible() -> None:
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
    assert "来源身份已确认" not in evidence.explanation
    assert "逐字材料" in evidence.explanation


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


def test_single_article_display_explains_absence_of_independent_evidence() -> None:
    items = [article(1, "现场有2人受伤。", "目标媒体")]

    _, response = explained_service(items, StubProvider(output="not-json"))

    assert response.display_result.evidence_cards == []
    assert any("没有其他独立新闻" in item for item in response.display_result.reasons)


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
    assert "来源覆盖、核心事实一致性、未发现明显冲突和多来源交叉印证" in prompt
    assert "支持因素、来源情况、一致性判断、限制因素" in prompt


def test_display_uses_generic_scope_limitations_without_registry_text() -> None:
    _, response = explained_service(
        supported_items(),
        StubProvider(error=TimeoutError()),
    )

    rendered = json.dumps(response.display_result.model_dump(mode="json"), ensure_ascii=False)
    assert "本次核验仅使用当前输入的新闻材料，没有联网检索其他报道。" in rendered
    assert "当前结论表示输入材料之间的证据关系，不代表最终权威认定。" in rendered
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
