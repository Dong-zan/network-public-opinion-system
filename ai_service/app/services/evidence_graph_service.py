import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from app.core.config import settings
from app.core.news_identity import normalized_news_id
from app.schemas.evidence_graph import (
    EvidenceClaimCluster,
    EvidenceGraphEdge,
    EvidenceGraphMetrics,
    EvidenceGraphNode,
    EvidenceGraphResponse,
    EvidenceTimelineEntry,
)
from app.schemas.event import Article, EventContext
from app.schemas.verification import VerificationContextEvidence, VerificationEvidence
from app.services.claim_canonicalizer import CanonicalClaim, ClaimCanonicalizer
from app.services.claim_extractor import AtomicClaim, ClaimExtractor
from app.services.evidence_retriever import EvidenceRetriever
from app.services.evidence_validator import EvidenceValidator
from app.services.event_evolution_analyzer import EventEvolutionAnalyzer
from app.services.source_clusterer import SourceClusterer, SourceDescriptor
from app.services.stance_classifier import StanceClassifier


@dataclass(frozen=True)
class ArticleRecord:
    index: int
    article: Article
    node_id: str
    source_node_id: str
    duplicate_of_index: int | None
    duplicate_reason_code: str | None


@dataclass(frozen=True)
class ClaimRecord:
    article_record: ArticleRecord
    claim_index: int
    claim: AtomicClaim
    canonical: CanonicalClaim
    node_id: str


class EvidenceGraphService:
    _edge_order = {
        "contains": 0,
        "published_by": 1,
        "asserts": 2,
        "supports": 3,
        "contradicts": 4,
        "updates": 5,
        "duplicates": 6,
    }

    def __init__(
        self,
        extractor: ClaimExtractor | None = None,
        classifier: StanceClassifier | None = None,
        validator: EvidenceValidator | None = None,
        retriever: EvidenceRetriever | None = None,
        canonicalizer: ClaimCanonicalizer | None = None,
        evolution_analyzer: EventEvolutionAnalyzer | None = None,
        source_clusterer: SourceClusterer | None = None,
        *,
        max_articles: int = 50,
        max_claims_per_article: int = 5,
        max_edges: int = 500,
        article_max_chars: int = 5000,
    ) -> None:
        self.extractor = extractor or ClaimExtractor()
        self.classifier = classifier or StanceClassifier(self.extractor)
        self.validator = validator or EvidenceValidator()
        self.retriever = retriever or EvidenceRetriever(
            self.classifier,
            article_max_chars=article_max_chars,
        )
        self.canonicalizer = canonicalizer or ClaimCanonicalizer()
        self.evolution_analyzer = evolution_analyzer or EventEvolutionAnalyzer()
        self.source_clusterer = source_clusterer or SourceClusterer()
        self.max_articles = max(max_articles, 1)
        self.max_claims_per_article = max(max_claims_per_article, 1)
        self.max_edges = max(max_edges, 1)
        self.article_max_chars = max(article_max_chars, 1)

    def build(self, event: EventContext) -> EvidenceGraphResponse:
        limitations = [
            "第一阶段仅分析当前事件输入中的文章，不联网搜索外部信息。",
            "冲突比例、转载比例和未解决主张比例仅描述当前证据图结构，不是真实性概率。",
        ]
        risk_flags = []
        input_articles = list(event.articles)
        selected_articles = input_articles[: self.max_articles]
        if len(input_articles) > self.max_articles:
            limitations.append(
                f"文章数量超过{self.max_articles}篇，已按输入顺序确定性截断。"
            )
            risk_flags.append("evidence_graph_input_truncated")

        duplicate_map, duplicate_reasons, same_url_fact_difference = self._duplicate_map(
            selected_articles
        )
        if duplicate_map:
            limitations.append("转载或高度重复文章保留在图中，但不增加独立来源数量。")
            risk_flags.append("duplicate_reprints_present")
        if same_url_fact_difference:
            limitations.append("部分相同URL文章包含不同关键事实，已保留为独立文章。")
            risk_flags.append("same_url_with_fact_difference")

        source_node_ids, source_nodes, source_identities = self._source_nodes(
            selected_articles
        )
        article_records, article_nodes = self._article_records(
            selected_articles,
            source_node_ids,
            duplicate_map,
            duplicate_reasons,
        )
        event_node = self._event_node(event)
        claim_records, claim_nodes, claim_limit_applied, content_truncated = (
            self._claim_records(article_records)
        )
        if claim_limit_applied:
            limitations.append(
                f"部分文章主张数量超过每篇{self.max_claims_per_article}条，已确定性截断。"
            )
            risk_flags.append("evidence_graph_input_truncated")
        if content_truncated:
            limitations.append(
                f"部分文章正文超过{self.article_max_chars}字符，已确定性截断后提取主张。"
            )
            risk_flags.append("evidence_graph_input_truncated")

        base_edges = self._base_edges(event_node, article_records, claim_records)
        raw_relation_edges, missing_identifier = self._relation_edges(
            article_records,
            claim_records,
            source_identities,
        )
        logical_relation_edges = self._compact_relation_edges(
            raw_relation_edges,
            claim_records,
        )
        if missing_identifier:
            limitations.append("部分文章缺少可用news_id，未参与跨文章证据关系校验。")
            risk_flags.append("missing_article_identifiers")

        displayed_relation_edges = logical_relation_edges[: self.max_edges]
        omitted_relation_edges = logical_relation_edges[self.max_edges :]
        edges = sorted(
            [*base_edges, *displayed_relation_edges],
            key=lambda edge: (
                self._edge_order[edge.edge_type],
                edge.source_node_id,
                edge.target_node_id,
                edge.edge_id,
            ),
        )
        omitted_by_type = {
            edge_type: sum(edge.edge_type == edge_type for edge in omitted_relation_edges)
            for edge_type in ("supports", "contradicts", "updates")
            if any(edge.edge_type == edge_type for edge in omitted_relation_edges)
        }
        if omitted_relation_edges:
            limitations.append(
                "部分语义关系边因展示上限被省略，但主张簇状态和指标基于完整逻辑关系计算。"
            )
            risk_flags.append("evidence_graph_input_truncated")
            risk_flags.append("evidence_graph_relation_edges_truncated")

        clusters = self._claim_clusters(
            claim_records,
            logical_relation_edges,
            source_identities,
        )
        timeline = self._timeline(claim_records, logical_relation_edges)
        metrics = self._metrics(
            article_records,
            source_nodes,
            source_identities,
            claim_records,
            clusters,
            logical_relation_edges,
            base_edges,
            displayed_relation_edges,
            omitted_by_type,
        )
        if metrics.conflicting_cluster_count:
            risk_flags.append("conflicting_claims_present")
        if metrics.update_edge_count:
            risk_flags.append("evolving_information")
        if metrics.verifiable_cluster_count == 0 and clusters:
            risk_flags.append("no_verifiable_graph_claims")
        elif any(cluster.status == "unresolved" for cluster in clusters):
            risk_flags.append("unresolved_claims_present")
        if any(
            edge.edge_type == "contradicts"
            and edge.attributes.get("source_independence_known", False)
            and not edge.attributes.get("independent_sources", False)
            for edge in logical_relation_edges
        ):
            risk_flags.append("same_source_internal_inconsistency")
        if any(
            edge.edge_type in {"supports", "contradicts", "updates"}
            and not edge.attributes.get("source_independence_known", True)
            for edge in logical_relation_edges
        ):
            risk_flags.append("source_independence_unknown")
        if any(ClaimExtractor.contains_instruction(item.content) for item in selected_articles):
            risk_flags.append("untrusted_instruction_ignored")
        if not claim_records:
            limitations.append("当前文章中未提取到可用于构建证据图的结构化主张。")
            risk_flags.append("no_graph_claims")

        nodes = [event_node, *article_nodes, *source_nodes, *claim_nodes]
        return EvidenceGraphResponse(
            event_id=event.event_id,
            nodes=nodes,
            edges=edges,
            claim_clusters=clusters,
            timeline=timeline,
            metrics=metrics,
            risk_flags=self._stable_unique(risk_flags),
            limitations=self._stable_unique(limitations),
        )

    def _duplicate_map(
        self,
        articles: list[Article],
    ) -> tuple[dict[int, int], dict[int, str], bool]:
        representatives = []
        duplicate_map = {}
        duplicate_reasons = {}
        same_url_fact_difference = False
        for index, article in enumerate(articles):
            duplicate_of = None
            for representative in representatives:
                decision = self.retriever.graph_duplicate_decision(
                    article,
                    articles[representative],
                )
                same_url_fact_difference = (
                    same_url_fact_difference
                    or decision.same_url_with_fact_difference
                )
                if decision.is_duplicate:
                    duplicate_of = representative
                    duplicate_reasons[index] = decision.reason_code or "duplicate"
                    break
            if duplicate_of is None:
                representatives.append(index)
            else:
                duplicate_map[index] = duplicate_of
        return duplicate_map, duplicate_reasons, same_url_fact_difference

    def _source_nodes(
        self,
        articles: list[Article],
    ) -> tuple[list[str], list[EvidenceGraphNode], dict[str, tuple[str, str]]]:
        descriptors = [
            SourceDescriptor(source=article.source, url=article.url)
            for article in articles
        ]
        assignments = self.source_clusterer.cluster_indices(descriptors)
        groups: dict[int, list[int]] = {}
        for index, cluster in enumerate(assignments):
            groups.setdefault(cluster, []).append(index)

        node_id_by_group = {}
        nodes = []
        identities = {}
        for group in sorted(groups.values(), key=lambda values: min(values)):
            member_identities = [
                self.source_clusterer.identity(descriptors[index]) for index in group
            ]
            payload_data: Any = sorted(member_identities)
            if not any(any(identity) for identity in member_identities):
                payload_data = {"unknown_source_group": min(group)}
            payload = json.dumps(payload_data, ensure_ascii=False, sort_keys=True)
            node_id = f"source:{self._digest(payload)}"
            node_id_by_group[assignments[group[0]]] = node_id
            source_names = [articles[index].source.strip() for index in group if articles[index].source.strip()]
            hosts = [
                urlparse(articles[index].url).hostname or ""
                for index in group
                if articles[index].url.strip()
            ]
            label = source_names[0] if source_names else next((host for host in hosts if host), "未知来源")
            nodes.append(
                EvidenceGraphNode(
                    node_id=node_id,
                    node_type="source",
                    label=label,
                    attributes={
                        "source_names": self._stable_unique(source_names),
                        "hosts": self._stable_unique(hosts),
                        "article_count": len(group),
                    },
                )
            )
            identities[node_id] = next(
                (identity for identity in member_identities if any(identity)),
                ("", ""),
            )
        source_ids = [node_id_by_group[assignment] for assignment in assignments]
        nodes.sort(key=lambda node: node.node_id)
        return source_ids, nodes, identities

    def _article_records(
        self,
        articles: list[Article],
        source_node_ids: list[str],
        duplicate_map: dict[int, int],
        duplicate_reasons: dict[int, str],
    ) -> tuple[list[ArticleRecord], list[EvidenceGraphNode]]:
        records = []
        nodes = []
        anonymous_occurrences: dict[str, int] = {}
        for index, article in enumerate(articles):
            node_id = self._article_node_id(article, anonymous_occurrences)
            record = ArticleRecord(
                index=index,
                article=article,
                node_id=node_id,
                source_node_id=source_node_ids[index],
                duplicate_of_index=duplicate_map.get(index),
                duplicate_reason_code=duplicate_reasons.get(index),
            )
            records.append(record)
        for record in records:
            article = record.article
            duplicate_node = (
                records[record.duplicate_of_index].node_id
                if record.duplicate_of_index is not None
                else None
            )
            nodes.append(
                EvidenceGraphNode(
                    node_id=record.node_id,
                    node_type="article",
                    label=article.title.strip() or f"文章 {article.news_id or record.index + 1}",
                    attributes={
                        "news_id": article.news_id,
                        "source": article.source,
                        "url": article.url,
                        "publish_time": article.publish_time,
                        "platform": article.platform,
                        "duplicate_of": duplicate_node,
                    },
                )
            )
        return records, nodes

    def _article_node_id(
        self,
        article: Article,
        anonymous_occurrences: dict[str, int],
    ) -> str:
        news_id = normalized_news_id(article.news_id)
        if news_id is not None:
            identity = json.dumps(
                {
                    "news_id": news_id,
                    "url": self.retriever._normalized_url(article.url),
                    "title": " ".join(article.title.split()),
                    "source": " ".join(article.source.split()),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            return f"article:{self._digest(identity)}"

        anonymous_identity = json.dumps(
            {
                "url": self.retriever._normalized_url(article.url),
                "content_hash": self._digest(" ".join(article.content.split())),
                "title": " ".join(article.title.split()),
                "source": " ".join(article.source.split()),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        occurrence = anonymous_occurrences.get(anonymous_identity, 0) + 1
        anonymous_occurrences[anonymous_identity] = occurrence
        identity = f"{anonymous_identity}|occurrence={occurrence}"
        return f"article:{self._digest(identity)}"

    def _claim_records(
        self,
        article_records: list[ArticleRecord],
    ) -> tuple[list[ClaimRecord], list[EvidenceGraphNode], bool, bool]:
        records = []
        nodes = []
        claim_limit_applied = False
        content_truncated = False
        for article_record in article_records:
            article = article_record.article
            bounded_content = article.content[: self.article_max_chars]
            if len(article.content) > self.article_max_chars:
                content_truncated = True
            bounded_article = article.model_copy(update={"content": bounded_content})
            extracted = self.extractor.extract(
                bounded_article,
                self.max_claims_per_article + 1,
            )
            if len(extracted) > self.max_claims_per_article:
                claim_limit_applied = True
            for claim_index, claim in enumerate(
                extracted[: self.max_claims_per_article],
                start=1,
            ):
                canonical = self.canonicalizer.canonicalize(claim)
                identity = json.dumps(
                    {
                        "article": article_record.node_id,
                        "index": claim_index,
                        "cluster": canonical.cluster_id,
                        "quote": claim.target_quote,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                node_id = (
                    f"claim:{self._digest(identity)}"
                )
                record = ClaimRecord(
                    article_record=article_record,
                    claim_index=claim_index,
                    claim=claim,
                    canonical=canonical,
                    node_id=node_id,
                )
                records.append(record)
                nodes.append(
                    EvidenceGraphNode(
                        node_id=node_id,
                        node_type="claim",
                        label=self._short_label(claim.target_quote),
                        attributes={
                            "claim_type": claim.claim_type,
                            "slots": claim.slots,
                            "polarity": claim.polarity,
                            "certainty": claim.certainty,
                            "quote": claim.target_quote,
                            "news_id": article.news_id,
                            "cluster_id": canonical.cluster_id,
                            "verifiable": claim.verifiable,
                        },
                    )
                )
        return records, nodes, claim_limit_applied, content_truncated

    def _base_edges(
        self,
        event_node: EvidenceGraphNode,
        articles: list[ArticleRecord],
        claims: list[ClaimRecord],
    ) -> list[EvidenceGraphEdge]:
        edges = []
        for article in articles:
            edges.append(self._edge("contains", event_node.node_id, article.node_id))
            edges.append(
                self._edge("published_by", article.node_id, article.source_node_id)
            )
            if article.duplicate_of_index is not None:
                representative = articles[article.duplicate_of_index]
                edges.append(
                    self._edge(
                        "duplicates",
                        article.node_id,
                        representative.node_id,
                        reason_code=article.duplicate_reason_code,
                    )
                )
        for claim in claims:
            edges.append(
                self._edge("asserts", claim.article_record.node_id, claim.node_id)
            )
        return edges

    def _relation_edges(
        self,
        articles: list[ArticleRecord],
        claims: list[ClaimRecord],
        source_identities: dict[str, tuple[str, str]],
    ) -> tuple[list[EvidenceGraphEdge], bool]:
        representative_articles = [
            record for record in articles if record.duplicate_of_index is None
        ]
        validation_articles = [record.article for record in representative_articles]
        claims_by_article: dict[int, list[ClaimRecord]] = {}
        for claim in claims:
            if claim.article_record.duplicate_of_index is None:
                claims_by_article.setdefault(claim.article_record.index, []).append(claim)

        edges = []
        missing_identifier = any(
            normalized_news_id(record.article.news_id) is None
            for record in representative_articles
        )
        for left_position, left_article in enumerate(representative_articles):
            if normalized_news_id(left_article.article.news_id) is None:
                continue
            for right_article in representative_articles[left_position + 1 :]:
                if normalized_news_id(right_article.article.news_id) is None:
                    continue
                for left_claim in claims_by_article.get(left_article.index, []):
                    for right_claim in claims_by_article.get(right_article.index, []):
                        if left_claim.claim.claim_type != right_claim.claim.claim_type:
                            continue
                        if not left_claim.claim.verifiable or not right_claim.claim.verifiable:
                            continue
                        decision = self.classifier.compare_claims(
                            left_claim.claim,
                            right_claim.claim,
                            target_publish_time=left_article.article.publish_time,
                            evidence_publish_time=right_article.article.publish_time,
                        )
                        if decision.stance in {"supports", "contradicts"}:
                            if not self._validate_symmetric_quotes(
                                left_claim,
                                right_claim,
                                validation_articles,
                                decision.stance,
                                decision.reason_code,
                                decision.relevance_score,
                            ):
                                continue
                            edge_type = (
                                "supports"
                                if decision.stance == "supports"
                                else "contradicts"
                            )
                            source_claim, target_claim = sorted(
                                (left_claim, right_claim),
                                key=lambda item: item.node_id,
                            )
                            edges.append(
                                self._edge(
                                    edge_type,
                                    source_claim.node_id,
                                    target_claim.node_id,
                                    quote=source_claim.claim.target_quote,
                                    reason_code=decision.reason_code,
                                    attributes=self._relation_attributes(
                                        source_claim,
                                        target_claim,
                                        decision.relevance_score,
                                        symmetric=True,
                                        source_identities=source_identities,
                                    ),
                                )
                            )
                        elif decision.stance == "updates":
                            source_claim, target_claim = self._update_direction(
                                left_claim,
                                right_claim,
                            )
                            relation_reason_code = self._stable_update_reason_code(
                                source_claim,
                                target_claim,
                                decision.reason_code,
                            )
                            if not self._validate_update_quotes(
                                source_claim,
                                target_claim,
                                validation_articles,
                                relation_reason_code,
                                decision.relevance_score,
                            ):
                                continue
                            edges.append(
                                self._edge(
                                    "updates",
                                    source_claim.node_id,
                                    target_claim.node_id,
                                    quote=target_claim.claim.target_quote,
                                    reason_code=relation_reason_code,
                                    attributes=self._relation_attributes(
                                        source_claim,
                                        target_claim,
                                        decision.relevance_score,
                                        symmetric=False,
                                        source_identities=source_identities,
                                    ),
                                )
                            )
        return self._stable_edges(edges), missing_identifier

    def _validate_symmetric_quotes(
        self,
        left: ClaimRecord,
        right: ClaimRecord,
        articles: list[Article],
        stance: str,
        reason_code: str,
        relevance_score: float,
    ) -> bool:
        pairs = ((left, right), (right, left))
        for evidence_claim, target_claim in pairs:
            validated = self.validator.validate(
                [
                    VerificationEvidence(
                        news_id=evidence_claim.article_record.article.news_id,
                        source=evidence_claim.article_record.article.source,
                        url=evidence_claim.article_record.article.url,
                        quote=evidence_claim.claim.target_quote,
                        stance=stance,
                        reason_code=reason_code,
                        relevance_score=relevance_score,
                    )
                ],
                articles,
                target_claim.article_record.article.news_id or "",
            )
            if not validated:
                return False
        return True

    def _validate_update_quotes(
        self,
        earlier: ClaimRecord,
        later: ClaimRecord,
        articles: list[Article],
        reason_code: str,
        relevance_score: float,
    ) -> bool:
        pairs = ((earlier, later), (later, earlier))
        for evidence_claim, target_claim in pairs:
            validated = self.validator.validate_context(
                [
                    VerificationContextEvidence(
                        news_id=evidence_claim.article_record.article.news_id,
                        source=evidence_claim.article_record.article.source,
                        url=evidence_claim.article_record.article.url,
                        quote=evidence_claim.claim.target_quote,
                        relation="updates",
                        reason_code=reason_code,
                        relevance_score=relevance_score,
                    )
                ],
                articles,
                target_claim.article_record.article.news_id or "",
            )
            if not validated:
                return False
        return True

    def _relation_attributes(
        self,
        source: ClaimRecord,
        target: ClaimRecord,
        relevance_score: float,
        *,
        symmetric: bool,
        source_identities: dict[str, tuple[str, str]],
    ) -> dict[str, Any]:
        source_news_id = source.article_record.article.news_id
        target_news_id = target.article_record.article.news_id
        source_known = self._source_identity_known(source, source_identities)
        target_known = self._source_identity_known(target, source_identities)
        independence_known = source_known and target_known
        independent_sources = (
            independence_known
            and source.article_record.source_node_id != target.article_record.source_node_id
            and source.article_record.duplicate_of_index is None
            and target.article_record.duplicate_of_index is None
        )
        return {
            "symmetric": symmetric,
            "independent_sources": independent_sources,
            "source_independence_known": independence_known,
            "source_news_id": source_news_id,
            "target_news_id": target_news_id,
            "source_quote": source.claim.target_quote,
            "target_quote": target.claim.target_quote,
            "evidence_news_id": source_news_id,
            "relevance_score": relevance_score,
        }

    @staticmethod
    def _source_identity_known(
        claim: ClaimRecord,
        source_identities: dict[str, tuple[str, str]],
    ) -> bool:
        return any(source_identities.get(claim.article_record.source_node_id, ("", "")))

    def _update_direction(
        self,
        left: ClaimRecord,
        right: ClaimRecord,
    ) -> tuple[ClaimRecord, ClaimRecord]:
        left_time = self.evolution_analyzer.resolve_time(
            left.claim,
            left.article_record.article.publish_time,
        )
        right_time = self.evolution_analyzer.resolve_time(
            right.claim,
            right.article_record.article.publish_time,
        )
        if left_time and right_time and left_time.sort_key != right_time.sort_key:
            return (left, right) if left_time.sort_key < right_time.sort_key else (right, left)
        return (left, right) if left.node_id < right.node_id else (right, left)

    @staticmethod
    def _stable_update_reason_code(
        earlier: ClaimRecord,
        later: ClaimRecord,
        fallback: str,
    ) -> str:
        """Use the same update explanation regardless of pair traversal order."""
        reason_by_claim_type = {
            "casualty": "casualty_information_evolved",
            "response_status": "response_status_evolved",
            "conclusion_status": "conclusion_status_evolved",
        }
        if earlier.claim.claim_type == later.claim.claim_type:
            return reason_by_claim_type.get(earlier.claim.claim_type, fallback)
        return fallback

    def _compact_relation_edges(
        self,
        edges: list[EvidenceGraphEdge],
        claims: list[ClaimRecord],
    ) -> list[EvidenceGraphEdge]:
        claim_index = {claim.node_id: claim for claim in claims}
        supports_by_cluster: dict[str, list[EvidenceGraphEdge]] = {}
        others: dict[tuple[Any, ...], EvidenceGraphEdge] = {}
        for edge in edges:
            source_claim = claim_index[edge.source_node_id]
            target_claim = claim_index[edge.target_node_id]
            if edge.edge_type == "supports":
                supports_by_cluster.setdefault(
                    source_claim.canonical.cluster_id,
                    [],
                ).append(edge)
                continue
            cluster_pair = tuple(
                sorted(
                    (
                        source_claim.canonical.cluster_id,
                        target_claim.canonical.cluster_id,
                    )
                )
            )
            source_pair = tuple(
                sorted(
                    (
                        source_claim.article_record.source_node_id,
                        target_claim.article_record.source_node_id,
                    )
                )
            )
            key = (edge.edge_type, cluster_pair, source_pair)
            current = others.get(key)
            if current is None or edge.edge_id < current.edge_id:
                others[key] = edge

        compacted = list(others.values())
        for cluster_edges in supports_by_cluster.values():
            by_source_pair: dict[tuple[str, str], EvidenceGraphEdge] = {}
            source_ids = set()
            for edge in cluster_edges:
                source_claim = claim_index[edge.source_node_id]
                target_claim = claim_index[edge.target_node_id]
                pair = tuple(
                    sorted(
                        (
                            source_claim.article_record.source_node_id,
                            target_claim.article_record.source_node_id,
                        )
                    )
                )
                source_ids.update(pair)
                current = by_source_pair.get(pair)
                if current is None or edge.edge_id < current.edge_id:
                    by_source_pair[pair] = edge
            if not source_ids:
                continue
            representative_source = min(source_ids)
            internal = [
                edge
                for pair, edge in by_source_pair.items()
                if pair[0] == pair[1]
            ]
            compacted.extend(sorted(internal, key=lambda item: item.edge_id))
            for source_id in sorted(source_ids - {representative_source}):
                edge = by_source_pair.get(
                    tuple(sorted((representative_source, source_id)))
                )
                if edge:
                    compacted.append(edge)
        return sorted(
            self._stable_edges(compacted),
            key=lambda edge: (
                self._edge_order[edge.edge_type],
                edge.source_node_id,
                edge.target_node_id,
                edge.edge_id,
            ),
        )

    def _claim_clusters(
        self,
        claims: list[ClaimRecord],
        edges: list[EvidenceGraphEdge],
        source_identities: dict[str, tuple[str, str]],
    ) -> list[EvidenceClaimCluster]:
        grouped: dict[str, list[ClaimRecord]] = {}
        for claim in claims:
            grouped.setdefault(claim.canonical.cluster_id, []).append(claim)
        claim_index = {claim.node_id: claim for claim in claims}

        clusters = []
        for cluster_id in sorted(grouped):
            members = sorted(grouped[cluster_id], key=lambda item: item.node_id)
            representative = members[0].canonical
            member_ids = {member.node_id for member in members}
            verifiable = any(member.claim.verifiable for member in members)
            certainty_values = sorted({member.claim.certainty for member in members})
            asserting_sources = self._member_source_ids(
                members,
                source_identities,
            )
            definite_sources = {
                member.article_record.source_node_id
                for member in members
                if member.claim.verifiable
                and member.claim.certainty != "unconfirmed"
                and member.claim.polarity != "unknown"
                and member.article_record.duplicate_of_index is None
                and any(
                    source_identities.get(
                        member.article_record.source_node_id,
                        ("", ""),
                    )
                )
            }
            support_sources = self._relation_source_ids(
                member_ids,
                edges,
                claim_index,
                source_identities,
                "supports",
            )
            contradict_sources = self._relation_source_ids(
                member_ids,
                edges,
                claim_index,
                source_identities,
                "contradicts",
            )
            update_sources = self._relation_source_ids(
                member_ids,
                edges,
                claim_index,
                source_identities,
                "updates",
            )
            independent_conflict = any(
                edge.edge_type == "contradicts"
                and edge.attributes.get("independent_sources", False)
                and (
                    edge.source_node_id in member_ids
                    or edge.target_node_id in member_ids
                )
                for edge in edges
            )
            independent_update = any(
                edge.edge_type == "updates"
                and edge.attributes.get("independent_sources", False)
                and (
                    edge.source_node_id in member_ids
                    or edge.target_node_id in member_ids
                )
                for edge in edges
            )
            independent_support = any(
                edge.edge_type == "supports"
                and edge.attributes.get("independent_sources", False)
                and (
                    edge.source_node_id in member_ids
                    or edge.target_node_id in member_ids
                )
                for edge in edges
            )
            if not verifiable:
                status = "not_verifiable"
            elif independent_conflict:
                status = "conflicting"
            elif independent_update:
                status = "evolving"
            elif independent_support and len(definite_sources) >= 2:
                status = "supported"
            else:
                status = "unresolved"
            clusters.append(
                EvidenceClaimCluster(
                    cluster_id=cluster_id,
                    claim_type=representative.claim_type,
                    canonical_slots=representative.canonical_slots,
                    polarity=representative.polarity,
                    certainty=(
                        certainty_values[0]
                        if len(certainty_values) == 1
                        else "mixed"
                    ),
                    certainty_values=certainty_values,
                    verifiable=verifiable,
                    claim_node_ids=[member.node_id for member in members],
                    article_node_ids=self._stable_unique(
                        [member.article_record.node_id for member in members]
                    ),
                    independent_source_count=len(asserting_sources),
                    asserting_independent_source_count=len(asserting_sources),
                    supporting_independent_source_count=len(support_sources),
                    contradicting_independent_source_count=len(contradict_sources),
                    updating_independent_source_count=len(update_sources),
                    status=status,
                )
            )
        return clusters

    @staticmethod
    def _member_source_ids(
        members: list[ClaimRecord],
        source_identities: dict[str, tuple[str, str]],
    ) -> set[str]:
        return {
            member.article_record.source_node_id
            for member in members
            if member.article_record.duplicate_of_index is None
            and any(
                source_identities.get(member.article_record.source_node_id, ("", ""))
            )
        }

    @staticmethod
    def _relation_source_ids(
        member_ids: set[str],
        edges: list[EvidenceGraphEdge],
        claim_index: dict[str, ClaimRecord],
        source_identities: dict[str, tuple[str, str]],
        edge_type: str,
    ) -> set[str]:
        source_ids = set()
        for edge in edges:
            if edge.edge_type != edge_type or not (
                edge.source_node_id in member_ids
                or edge.target_node_id in member_ids
            ) or not edge.attributes.get("independent_sources", False):
                continue
            for node_id in (edge.source_node_id, edge.target_node_id):
                claim = claim_index[node_id]
                source_id = claim.article_record.source_node_id
                if (
                    claim.article_record.duplicate_of_index is None
                    and any(source_identities.get(source_id, ("", "")))
                ):
                    source_ids.add(source_id)
        return source_ids

    def _timeline(
        self,
        claims: list[ClaimRecord],
        edges: list[EvidenceGraphEdge],
    ) -> list[EvidenceTimelineEntry]:
        update_edges_by_claim: dict[str, list[str]] = {}
        for edge in edges:
            if edge.edge_type != "updates":
                continue
            update_edges_by_claim.setdefault(edge.source_node_id, []).append(edge.edge_id)
            update_edges_by_claim.setdefault(edge.target_node_id, []).append(edge.edge_id)
        entries = []
        sortable = []
        for claim in claims:
            if claim.article_record.duplicate_of_index is not None:
                continue
            resolved = self.evolution_analyzer.resolve_time(
                claim.claim,
                claim.article_record.article.publish_time,
            )
            if not resolved:
                continue
            timeline_id = f"timeline:{self._digest(claim.node_id + resolved.display)}"
            entry = EvidenceTimelineEntry(
                timeline_id=timeline_id,
                time=resolved.display,
                time_source=resolved.source,
                time_precision=resolved.precision,
                year_inferred=resolved.year_inferred,
                normalized_time=resolved.normalized_time,
                article_node_id=claim.article_record.node_id,
                claim_node_id=claim.node_id,
                claim_type=claim.claim.claim_type,
                summary=claim.claim.target_quote,
                related_edge_ids=sorted(update_edges_by_claim.get(claim.node_id, [])),
            )
            sortable.append((resolved.sort_key, claim.article_record.node_id, claim.node_id, entry))
        sortable.sort(key=lambda item: item[:3])
        entries.extend(item[3] for item in sortable)
        return entries

    def _metrics(
        self,
        articles: list[ArticleRecord],
        source_nodes: list[EvidenceGraphNode],
        source_identities: dict[str, tuple[str, str]],
        claims: list[ClaimRecord],
        clusters: list[EvidenceClaimCluster],
        logical_relation_edges: list[EvidenceGraphEdge],
        base_edges: list[EvidenceGraphEdge],
        displayed_relation_edges: list[EvidenceGraphEdge],
        omitted_by_type: dict[str, int],
    ) -> EvidenceGraphMetrics:
        relation_edges = logical_relation_edges
        support_count = sum(edge.edge_type == "supports" for edge in relation_edges)
        contradiction_count = sum(
            edge.edge_type == "contradicts" for edge in relation_edges
        )
        update_count = sum(edge.edge_type == "updates" for edge in relation_edges)
        duplicate_count = sum(
            article.duplicate_of_index is not None for article in articles
        )
        independent_sources = {
            article.source_node_id
            for article in articles
            if article.duplicate_of_index is None
            and any(source_identities.get(article.source_node_id, ("", "")))
        }
        verifiable_clusters = [cluster for cluster in clusters if cluster.verifiable]
        unresolved_count = sum(
            cluster.status == "unresolved" for cluster in verifiable_clusters
        )
        conflicting_count = sum(
            cluster.status == "conflicting" for cluster in verifiable_clusters
        )
        not_verifiable_count = sum(
            cluster.status == "not_verifiable" for cluster in clusters
        )
        omitted_count = sum(omitted_by_type.values())
        return EvidenceGraphMetrics(
            article_count=len(articles),
            source_count=len(source_nodes),
            independent_source_count=len(independent_sources),
            claim_count=len(claims),
            claim_cluster_count=len(clusters),
            support_edge_count=support_count,
            contradiction_edge_count=contradiction_count,
            update_edge_count=update_count,
            duplicate_article_count=duplicate_count,
            conflict_ratio=self._ratio(
                conflicting_count,
                len(verifiable_clusters),
            ),
            reprint_ratio=self._ratio(duplicate_count, len(articles)),
            unresolved_claim_ratio=self._ratio(
                unresolved_count,
                len(verifiable_clusters),
            ),
            conflicting_cluster_count=conflicting_count,
            verifiable_cluster_count=len(verifiable_clusters),
            contradiction_edge_ratio=self._ratio(
                contradiction_count,
                len(relation_edges),
            ),
            not_verifiable_cluster_count=not_verifiable_count,
            logical_edge_count=len(base_edges) + len(logical_relation_edges),
            returned_edge_count=len(base_edges) + len(displayed_relation_edges),
            omitted_relation_edge_count=omitted_count,
            omitted_edge_count_by_type=omitted_by_type,
        )

    def _event_node(self, event: EventContext) -> EvidenceGraphNode:
        event_key = str(event.event_id) if event.event_id is not None else "unknown"
        return EvidenceGraphNode(
            node_id=f"event:{self._digest(event_key)}",
            node_type="event",
            label=event.title.strip() or f"事件 {event_key}",
            attributes={
                "event_id": event.event_id,
                "title": event.title,
                "update_time": event.update_time,
            },
        )

    def _edge(
        self,
        edge_type: str,
        source: str,
        target: str,
        *,
        quote: str | None = None,
        reason_code: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> EvidenceGraphEdge:
        payload = json.dumps(
            {
                "type": edge_type,
                "source": source,
                "target": target,
                "quote": quote or "",
                "reason": reason_code or "",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return EvidenceGraphEdge(
            edge_id=f"edge:{edge_type}:{self._digest(payload)}",
            edge_type=edge_type,
            source_node_id=source,
            target_node_id=target,
            quote=quote,
            reason_code=reason_code,
            attributes=attributes or {},
        )

    @staticmethod
    def _stable_edges(edges: list[EvidenceGraphEdge]) -> list[EvidenceGraphEdge]:
        result = []
        seen = set()
        for edge in sorted(edges, key=lambda item: item.edge_id):
            if edge.edge_id not in seen:
                seen.add(edge.edge_id)
                result.append(edge)
        return result

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _short_label(value: str) -> str:
        normalized = " ".join(value.split())
        return normalized if len(normalized) <= 80 else normalized[:77] + "..."

    @staticmethod
    def _stable_unique(values: list[str]) -> list[str]:
        result = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result


@lru_cache
def get_evidence_graph_service() -> EvidenceGraphService:
    return EvidenceGraphService(
        max_articles=settings.evidence_graph_max_articles,
        max_claims_per_article=settings.evidence_graph_max_claims_per_article,
        max_edges=settings.evidence_graph_max_edges,
        article_max_chars=settings.evidence_graph_article_max_chars,
    )
