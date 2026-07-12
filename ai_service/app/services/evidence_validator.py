from app.schemas.event import Article
from app.schemas.verification import VerificationContextEvidence, VerificationEvidence


class EvidenceValidator:
    def validate(
        self,
        evidence: list[VerificationEvidence],
        articles: list[Article],
        target_news_id: int | str,
    ) -> list[VerificationEvidence]:
        article_index = {}
        ambiguous_ids = set()
        for article in articles:
            if article.news_id is None:
                continue
            key = self._id_key(article.news_id)
            if key in article_index:
                ambiguous_ids.add(key)
                article_index.pop(key, None)
            elif key not in ambiguous_ids:
                article_index[key] = article
        target_key = self._id_key(target_news_id)
        result = []
        seen = set()
        for item in evidence:
            key = self._id_key(item.news_id)
            article = article_index.get(key)
            if article is None or key == target_key or item.quote not in article.content:
                continue
            canonical = VerificationEvidence(
                news_id=article.news_id,
                source=article.source,
                url=article.url,
                quote=item.quote,
                stance=item.stance,
                reason_code=item.reason_code,
                relevance_score=item.relevance_score,
            )
            identity = (key, canonical.quote, canonical.stance)
            if identity not in seen:
                seen.add(identity)
                result.append(canonical)
        return result

    def validate_context(
        self,
        evidence: list[VerificationContextEvidence],
        articles: list[Article],
        target_news_id: int | str,
    ) -> list[VerificationContextEvidence]:
        article_index = self._article_index(articles)
        target_key = self._id_key(target_news_id)
        result = []
        seen = set()
        for item in evidence:
            key = self._id_key(item.news_id)
            article = article_index.get(key)
            if article is None or key == target_key or item.quote not in article.content:
                continue
            canonical = VerificationContextEvidence(
                news_id=article.news_id,
                source=article.source,
                url=article.url,
                quote=item.quote,
                relation=item.relation,
                reason_code=item.reason_code,
                relevance_score=item.relevance_score,
            )
            identity = (key, canonical.quote, canonical.relation)
            if identity not in seen:
                seen.add(identity)
                result.append(canonical)
        return result

    @classmethod
    def _article_index(cls, articles: list[Article]) -> dict[str, Article]:
        article_index = {}
        ambiguous_ids = set()
        for article in articles:
            if article.news_id is None:
                continue
            key = cls._id_key(article.news_id)
            if key in article_index:
                ambiguous_ids.add(key)
                article_index.pop(key, None)
            elif key not in ambiguous_ids:
                article_index[key] = article
        return article_index

    @staticmethod
    def _id_key(value: int | str | None) -> str:
        return "" if value is None else str(value).strip()
