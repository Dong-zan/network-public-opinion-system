from app.core.news_identity import normalized_news_id
from app.schemas.event import Article, EventContext
from app.schemas.verification import (
    EvidenceSourceAssessment,
    SourceRole,
    VerificationResponse,
)
from app.services.source_traceability import SourceTraceabilityEvaluator


class EvidenceSourceAssessmentService:
    def __init__(
        self,
        evaluator: SourceTraceabilityEvaluator | None = None,
    ) -> None:
        self.evaluator = evaluator or SourceTraceabilityEvaluator()

    def assess(
        self,
        event: EventContext,
        response: VerificationResponse,
    ) -> list[EvidenceSourceAssessment]:
        articles = {
            normalized_news_id(article.news_id): article
            for article in event.articles
            if normalized_news_id(article.news_id) is not None
        }
        results = []
        seen = set()
        for claim in response.claim_results:
            for evidence in [*claim.evidence, *claim.context_evidence]:
                key = normalized_news_id(evidence.news_id)
                if key is None or key in seen or key not in articles:
                    continue
                seen.add(key)
                article = articles[key]
                assessment = self.evaluator.evaluate(article)
                role = self._source_role(article)
                results.append(
                    EvidenceSourceAssessment(
                        news_id=article.news_id,
                        source=article.source,
                        source_role=role,
                        identity_status=assessment.status,
                        registered_source=assessment.registered_source,
                        domain_match=assessment.domain_match,
                        metadata_coverage=assessment.metadata_coverage,
                        explanation=self._explanation(article, assessment, role),
                    )
                )
        return results

    @staticmethod
    def _source_role(article: Article) -> SourceRole:
        values = " ".join(
            value.strip().casefold()
            for value in (article.source_type, article.account_type)
            if value and value.strip()
        )
        mappings = (
            (("government", "政务", "政府"), "government_notice"),
            (("regulator", "监管"), "regulator"),
            (("emergency", "应急"), "emergency_management"),
            (("fire", "消防"), "fire_rescue"),
            (("operator", "company", "企业", "运营"), "operator"),
            (("expert", "专家"), "expert_group"),
            (("witness", "目击"), "witness"),
            (("social", "自媒体", "社交"), "social_account"),
            (("media", "新闻媒体", "媒体"), "news_media"),
        )
        for markers, role in mappings:
            if any(marker in values for marker in markers):
                return role
        if "新闻" in article.platform:
            return "news_media"
        return "unknown"

    @staticmethod
    def _explanation(article: Article, assessment, role: SourceRole) -> str:
        role_label = {
            "government_notice": "政务发布",
            "regulator": "监管机构",
            "emergency_management": "应急管理机构",
            "fire_rescue": "消防救援机构",
            "operator": "运营主体",
            "expert_group": "专家机构",
            "news_media": "新闻媒体",
            "witness": "目击者",
            "social_account": "社交账号",
            "anonymous_source": "匿名来源",
            "unknown": "新闻来源",
        }[role]
        present = []
        if article.source.strip():
            present.append("来源名称")
        if assessment.hostname:
            present.append("链接")
        if article.publish_time and article.publish_time.strip():
            present.append("发布时间")
        if present:
            return f"输入中标记为{role_label}，具有{'、'.join(present)}。"
        return f"输入中标记为{role_label}。"
