import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.parse import urlsplit, urlunsplit

from app.schemas.event import Article
from app.core.news_identity import normalized_news_id
from app.services.claim_extractor import AtomicClaim, ClaimExtractor
from app.services.stance_classifier import StanceClassifier


@dataclass(frozen=True)
class RetrievedEvidence:
    article: Article
    quote: str
    stance: str
    reason_code: str
    relevance_score: float


@dataclass(frozen=True)
class RetrievalResult:
    evidence: tuple[RetrievedEvidence, ...]
    sentence_limit_applied: bool
    article_truncated: bool


@dataclass(frozen=True)
class CandidateSelection:
    articles: tuple[Article, ...]
    duplicate_count: int
    candidate_limit_applied: bool
    article_truncated_count: int
    near_duplicate_fact_difference_count: int


@dataclass(frozen=True)
class DuplicateDecision:
    is_duplicate: bool
    reason_code: str | None = None
    same_url_with_fact_difference: bool = False


class EvidenceRetriever:
    def __init__(
        self,
        classifier: StanceClassifier | None = None,
        *,
        max_candidates: int = 50,
        max_sentences_per_article: int = 100,
        article_max_chars: int = 5000,
    ) -> None:
        self.classifier = classifier or StanceClassifier()
        self.extractor = ClaimExtractor()
        self.max_candidates = max(max_candidates, 1)
        self.max_sentences_per_article = max(max_sentences_per_article, 1)
        self.article_max_chars = max(article_max_chars, 1)

    def select_candidates(
        self,
        articles: list[Article],
        target: Article,
    ) -> CandidateSelection:
        selected = []
        duplicate_count = 0
        near_duplicate_fact_difference_count = 0
        candidate_limit_applied = False
        target_body = self._normalized_body(target.content)
        target_url = self._normalized_url(target.url)
        target_signatures = self._fact_signatures(target.content)
        seen_ids = set()
        seen_urls = set()
        seen_hashes = set()
        article_truncated_count = sum(
            1
            for article in articles
            if article is not target
            and not self._same_news_id(article.news_id, target.news_id)
            and self._id_key(article.news_id) is not None
            and bool(article.content.strip())
            and len(article.content) > self.article_max_chars
        )

        for article in articles:
            if article is target or self._same_news_id(article.news_id, target.news_id):
                continue
            if self._id_key(article.news_id) is None or not article.content.strip():
                continue
            if len(selected) >= self.max_candidates:
                candidate_limit_applied = True
                break

            body = self._normalized_body(article.content)
            url = self._normalized_url(article.url)
            body_hash = self._body_hash(body)
            news_key = self._id_key(article.news_id)
            signatures = self._fact_signatures(article.content)
            if (url and url == target_url) or (body and body == target_body):
                duplicate_count += 1
                continue
            near_fact_difference = False
            if self._highly_similar_bodies(body, target_body):
                if signatures == target_signatures:
                    duplicate_count += 1
                    continue
                near_fact_difference = True
            if news_key in seen_ids or (url and url in seen_urls) or body_hash in seen_hashes:
                duplicate_count += 1
                continue
            duplicate = False
            for existing in selected:
                existing_body = self._normalized_body(existing.content)
                if not self._highly_similar_bodies(body, existing_body):
                    continue
                if signatures == self._fact_signatures(existing.content):
                    duplicate = True
                    break
                near_fact_difference = True
            if duplicate:
                duplicate_count += 1
                continue
            if near_fact_difference:
                near_duplicate_fact_difference_count += 1
            selected.append(article)
            seen_ids.add(news_key)
            if url:
                seen_urls.add(url)
            seen_hashes.add(body_hash)

        return CandidateSelection(
            articles=tuple(selected),
            duplicate_count=duplicate_count,
            candidate_limit_applied=candidate_limit_applied,
            article_truncated_count=article_truncated_count,
            near_duplicate_fact_difference_count=near_duplicate_fact_difference_count,
        )

    def retrieve(
        self,
        claim: AtomicClaim,
        candidates: tuple[Article, ...],
        target_publish_time: str | None = None,
    ) -> RetrievalResult:
        evidence = []
        sentence_limit_applied = False
        article_truncated = False
        for article in candidates:
            content = article.content
            if len(content) > self.article_max_chars:
                content = content[: self.article_max_chars]
                article_truncated = True
            sentences = self._sentences(content)
            if len(sentences) > self.max_sentences_per_article:
                sentences = sentences[: self.max_sentences_per_article]
                sentence_limit_applied = True
            ranked = sorted(
                (
                    (self.classifier.relevance(claim, sentence), index, sentence)
                    for index, sentence in enumerate(sentences)
                ),
                key=lambda item: (-item[0], item[1]),
            )
            if not ranked or ranked[0][0] < 0.2:
                continue
            _, _, quote = ranked[0]
            decision = self.classifier.classify(
                claim,
                quote,
                target_publish_time=target_publish_time,
                evidence_publish_time=article.publish_time,
            )
            if decision.stance == "irrelevant":
                continue
            evidence.append(
                RetrievedEvidence(
                    article=article,
                    quote=quote,
                    stance=decision.stance,
                    reason_code=decision.reason_code,
                    relevance_score=decision.relevance_score,
                )
            )
        return RetrievalResult(
            evidence=tuple(evidence),
            sentence_limit_applied=sentence_limit_applied,
            article_truncated=article_truncated,
        )

    def articles_are_duplicates(self, left: Article, right: Article) -> bool:
        return self.graph_duplicate_decision(left, right).is_duplicate

    def graph_duplicate_decision(
        self,
        left: Article,
        right: Article,
    ) -> DuplicateDecision:
        if self._same_news_id(left.news_id, right.news_id):
            return DuplicateDecision(True, "same_news_id")
        left_url = self._normalized_url(left.url)
        right_url = self._normalized_url(right.url)
        if left_url and left_url == right_url:
            left_signatures = self._fact_signatures(left.content)
            right_signatures = self._fact_signatures(right.content)
            if left_signatures and right_signatures and left_signatures != right_signatures:
                return DuplicateDecision(
                    False,
                    same_url_with_fact_difference=True,
                )
            return DuplicateDecision(True, "same_normalized_url")
        left_body = self._normalized_body(left.content)
        right_body = self._normalized_body(right.content)
        if left_body and left_body == right_body:
            return DuplicateDecision(True, "same_normalized_body")
        if (
            self._highly_similar_bodies(left_body, right_body)
            and self._fact_signatures(left.content) == self._fact_signatures(right.content)
        ):
            return DuplicateDecision(True, "highly_similar_same_fact_signature")
        return DuplicateDecision(False)

    def _fact_signatures(self, content: str) -> frozenset[tuple]:
        signatures = []
        for _, claim in self.extractor.extract_text(content[: self.article_max_chars]):
            if claim.claim_type == "other":
                continue
            slots = tuple(sorted((key, str(value)) for key, value in claim.slots.items()))
            signatures.append(
                (
                    claim.claim_type,
                    claim.certainty,
                    claim.polarity,
                    claim.modality_reason,
                    slots,
                )
            )
        return frozenset(signatures)

    @staticmethod
    def _sentences(content: str) -> list[str]:
        return [
            sentence.strip()
            for sentence in re.split(r"(?<=[。！？；;])|\n+", content)
            if sentence.strip() and not ClaimExtractor.contains_instruction(sentence)
        ]

    def _normalized_body(self, content: str) -> str:
        bounded = content[: self.article_max_chars]
        return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", bounded).lower()

    @staticmethod
    def _normalized_url(url: str) -> str:
        value = url.strip()
        if not value:
            return ""
        try:
            parts = urlsplit(value)
        except ValueError:
            return value.lower().rstrip("/")
        path = parts.path.rstrip("/") or "/"
        return urlunsplit(
            (parts.scheme.lower(), parts.netloc.lower(), path, parts.query, "")
        )

    @staticmethod
    def _body_hash(body: str) -> str:
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    @staticmethod
    def _same_news_id(left: int | str | None, right: int | str | None) -> bool:
        left_key = normalized_news_id(left)
        right_key = normalized_news_id(right)
        return left_key is not None and left_key == right_key

    @staticmethod
    def _id_key(value: int | str | None) -> str | None:
        return normalized_news_id(value)

    @staticmethod
    def _highly_similar_bodies(left: str, right: str) -> bool:
        if not left or not right:
            return False
        if left == right:
            return True
        if SequenceMatcher(None, left, right, autojunk=False).ratio() >= 0.9:
            return True
        left_grams = EvidenceRetriever._ngrams(left)
        right_grams = EvidenceRetriever._ngrams(right)
        if not left_grams or not right_grams:
            return False
        similarity = len(left_grams & right_grams) / len(left_grams | right_grams)
        return similarity >= 0.9

    @staticmethod
    def _ngrams(text: str, size: int = 3) -> set[str]:
        if len(text) < size:
            return {text} if text else set()
        return {text[index : index + size] for index in range(len(text) - size + 1)}
