from dataclasses import dataclass
from urllib.parse import urlparse

from app.schemas.event import Article
from app.schemas.verification import SourceAssessment
from app.services.source_registry import SourceRegistry, StaticSourceRegistry


@dataclass(frozen=True)
class SourceTraceabilityConfig:
    version: str = "source-traceability-v1"
    verified_risk: float = 15.0
    partially_verified_risk: float = 40.0
    unknown_risk: float = 50.0
    mismatch_risk: float = 75.0
    metadata_fields: int = 10


class SourceTraceabilityEvaluator:
    def __init__(
        self,
        registry: SourceRegistry | None = None,
        config: SourceTraceabilityConfig | None = None,
    ) -> None:
        self.registry = registry or StaticSourceRegistry()
        self.config = config or SourceTraceabilityConfig()

    def evaluate(self, article: Article) -> SourceAssessment:
        hostname = self._hostname(article.url)
        profile = self.registry.find(article.source)
        domain_match = self._domain_match(hostname, profile.verified_domains) if profile and hostname else None
        coverage = self._metadata_coverage(article, hostname)
        signals = self._signals(article, hostname, profile is not None, domain_match)

        if profile and domain_match is True:
            traceability = round(min(100.0, 70.0 + coverage * 0.3), 1)
            return SourceAssessment(
                status="verified",
                traceability_score=traceability,
                risk_score=round(max(5.0, self.config.verified_risk - (traceability - 70.0) * 0.1), 1),
                registered_source=True,
                canonical_name=profile.canonical_name,
                hostname=hostname,
                domain_match=True,
                metadata_coverage=coverage,
                signals=signals,
            )
        if profile and hostname and domain_match is False:
            return SourceAssessment(
                status="mismatch",
                traceability_score=round(coverage * 0.5, 1),
                risk_score=self.config.mismatch_risk,
                registered_source=True,
                canonical_name=profile.canonical_name,
                hostname=hostname,
                domain_match=False,
                metadata_coverage=coverage,
                signals=signals,
            )
        if profile or coverage >= 50:
            return SourceAssessment(
                status="partially_verified",
                traceability_score=round(min(75.0, coverage * 0.75), 1),
                risk_score=self.config.partially_verified_risk,
                registered_source=profile is not None,
                canonical_name=profile.canonical_name if profile else None,
                hostname=hostname,
                domain_match=domain_match,
                metadata_coverage=coverage,
                signals=signals,
            )
        return SourceAssessment(
            status="unknown",
            traceability_score=None,
            risk_score=self.config.unknown_risk,
            registered_source=False,
            canonical_name=None,
            hostname=hostname,
            domain_match=None,
            metadata_coverage=coverage,
            signals=signals,
        )

    @staticmethod
    def _hostname(url: str) -> str | None:
        value = url.strip()
        if not value:
            return None
        try:
            hostname = urlparse(value).hostname
        except ValueError:
            return None
        return hostname.casefold() if hostname else None

    @staticmethod
    def _domain_match(hostname: str | None, domains: tuple[str, ...]) -> bool:
        if not hostname:
            return False
        return any(hostname == domain.casefold() or hostname.endswith("." + domain.casefold()) for domain in domains)

    def _metadata_coverage(self, article: Article, hostname: str | None) -> float:
        values = (
            bool(article.source.strip()),
            bool(article.url.strip()),
            hostname is not None,
            article.publish_time is not None and bool(article.publish_time.strip()),
            article.author is not None and bool(article.author.strip()),
            article.is_official is not None,
            article.account_type is not None and bool(article.account_type.strip()),
            article.source_type is not None and bool(article.source_type.strip()),
            bool(article.reference_urls),
            bool(article.quoted_news_ids) or (article.duplicate_group_id is not None and bool(article.duplicate_group_id.strip())),
        )
        return round(sum(values) / self.config.metadata_fields * 100, 1)

    @staticmethod
    def _signals(article: Article, hostname: str | None, registered: bool, domain_match: bool | None) -> list[str]:
        signals = []
        if article.source.strip():
            signals.append("source_present")
        if hostname:
            signals.append("url_hostname_present")
        if article.publish_time:
            signals.append("publish_time_present")
        if article.author:
            signals.append("author_present")
        if article.reference_urls:
            signals.append("reference_urls_present")
        if article.quoted_news_ids:
            signals.append("quoted_news_ids_present")
        if article.duplicate_group_id:
            signals.append("duplicate_group_id_present")
        if registered:
            signals.append("source_registered")
        if domain_match is True:
            signals.append("registered_domain_matched")
        if domain_match is False:
            signals.append("registered_domain_mismatch")
        return signals
