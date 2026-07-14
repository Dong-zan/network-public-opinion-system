import hashlib
import json
from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.news_identity import normalized_news_id
from app.schemas.evidence_graph import (
    EvidenceClaimCluster,
    EvidenceGraphEdge,
    EvidenceGraphMetrics,
    EvidenceGraphNode,
    EvidenceGraphResponse,
    EvidenceTimelineEntry,
)
from app.schemas.evidence_graph_llm import EvidenceGraphLLMOutput
from app.schemas.event import Article, EventContext
from app.services.claim_extractor import AtomicClaim, ClaimExtractor
from app.services.evidence_retriever import EvidenceRetriever
from app.services.event_evolution_analyzer import EventEvolutionAnalyzer
from app.services.source_clusterer import SourceClusterer, SourceDescriptor


class EvidenceGraphLLMValidationError(ValueError):
    """Raised when an LLM graph has no safe, useful graph content."""


@dataclass(frozen=True)
class _GraphContext:
    article_node_ids: dict[int, str]
    source_node_ids: dict[int, str]
    source_assignments: list[int]
    duplicate_map: dict[int, int]
    node_article_indices: dict[str, int]


class EvidenceGraphLLMValidator:
    _uninformative_phrases = (
        "该节点来自输入材料",
        "该节点来源于输入材料",
        "该报道提供相关证据",
        "该报道提供相关信息",
        "当前信息存在一定关联",
        "当前材料存在关联",
        "还需要进一步核实",
        "需要进一步核实",
    )
    _node_order = {"event": 0, "article": 1, "source": 2, "claim": 3, "evidence": 4}
    _edge_order = {
        "contains": 0,
        "published_by": 1,
        "asserts": 2,
        "supports": 3,
        "contradicts": 4,
        "same_fact": 5,
        "adds_detail": 6,
        "updates": 7,
        "quotes": 8,
        "reposts": 9,
        "duplicates": 10,
    }
    _semantic_relations = {
        "supports",
        "contradicts",
        "same_fact",
        "adds_detail",
        "updates",
    }

    def __init__(
        self,
        *,
        max_nodes: int,
        max_edges: int,
        retriever: EvidenceRetriever | None = None,
        source_clusterer: SourceClusterer | None = None,
        extractor: ClaimExtractor | None = None,
        evolution_analyzer: EventEvolutionAnalyzer | None = None,
    ) -> None:
        self.max_nodes = max(max_nodes, 1)
        self.max_edges = max(max_edges, 1)
        self.retriever = retriever or EvidenceRetriever()
        self.source_clusterer = source_clusterer or SourceClusterer()
        self.extractor = extractor or ClaimExtractor()
        self.evolution_analyzer = evolution_analyzer or EventEvolutionAnalyzer()

    def finalize(
        self,
        event: EventContext,
        articles: list[Article],
        output: EvidenceGraphLLMOutput,
        *,
        articles_truncated: bool,
        content_truncated: bool,
    ) -> EvidenceGraphResponse:
        if self._is_uninformative(output.summary):
            raise EvidenceGraphLLMValidationError(
                "LLM graph summary contains only uninformative wording"
            )
        base_nodes, context = self._base_nodes(event, articles)
        nodes_by_id = {node.node_id: node for node in base_nodes}
        model_id_map: dict[str, str] = {}
        seen_model_ids = set()
        semantic_keys: dict[tuple[str, int, str, str], str] = {}

        for node in output.nodes:
            if node.id in seen_model_ids:
                continue
            seen_model_ids.add(node.id)
            if self._is_uninformative(node.description):
                continue
            article_index = self._resolve_article_index(
                articles,
                node.news_id,
                node.source,
                node.quote,
                node.label,
                node.type,
            )
            if node.type in {"article", "claim", "evidence"} and article_index is None:
                continue
            if node.type == "source" and article_index is None:
                continue

            if node.type == "article":
                canonical_id = context.article_node_ids[article_index]
                existing = nodes_by_id[canonical_id]
                nodes_by_id[canonical_id] = existing.model_copy(
                    update={"label": node.label, "description": node.description}
                )
            elif node.type == "source":
                canonical_id = context.source_node_ids[article_index]
                existing = nodes_by_id[canonical_id]
                nodes_by_id[canonical_id] = existing.model_copy(
                    update={"label": node.label, "description": node.description}
                )
            else:
                article = articles[article_index]
                quote = node.quote
                if not quote and self._quote_in_article(node.label, article):
                    quote = node.label
                if not quote:
                    continue
                key = (
                    node.type,
                    article_index,
                    self._normalize(quote),
                    self._normalize(node.label),
                )
                canonical_id = semantic_keys.get(key)
                if canonical_id is None:
                    canonical_id = f"{node.type}:{self._digest(json.dumps(key, ensure_ascii=False))}"
                    semantic_keys[key] = canonical_id
                    nodes_by_id[canonical_id] = EvidenceGraphNode(
                        node_id=canonical_id,
                        node_type=node.type,
                        label=node.label,
                        description=node.description,
                        attributes={
                            "news_id": article.news_id,
                            "source": article.source,
                            "quote": quote,
                            "verifiable": True,
                            "extraction_method": "llm",
                        },
                    )
                    context.node_article_indices[canonical_id] = article_index
            model_id_map[node.id] = canonical_id

        retained_nodes = self._limit_nodes(list(nodes_by_id.values()))
        retained_ids = {node.node_id for node in retained_nodes}
        base_edges = self._base_edges(event, articles, context, retained_ids)
        model_edges = self._validated_model_edges(
            output,
            articles,
            context,
            model_id_map,
            retained_ids,
        )
        if not model_edges:
            raise EvidenceGraphLLMValidationError(
                "LLM graph has no valid model-generated edges"
            )
        key_findings = [
            item for item in output.key_findings if not self._is_uninformative(item)
        ]
        if not key_findings:
            raise EvidenceGraphLLMValidationError(
                "LLM graph has no concrete key findings"
            )

        all_edges = self._stable_edges([*base_edges, *model_edges])
        omitted_edges = all_edges[self.max_edges :]
        edges = all_edges[: self.max_edges]
        connected_ids = {
            node_id
            for edge in edges
            for node_id in (edge.source_node_id, edge.target_node_id)
        }
        nodes = [node for node in retained_nodes if node.node_id in connected_ids]
        node_ids = {node.node_id for node in nodes}
        edges = [
            edge
            for edge in edges
            if edge.source_node_id in node_ids and edge.target_node_id in node_ids
        ]
        if not nodes or not edges:
            raise EvidenceGraphLLMValidationError("LLM graph is empty after validation")

        clusters = self._claim_clusters(nodes, edges, articles, context)
        timeline = self._timeline(nodes, edges, articles, context)
        omitted_by_type = self._counts_by_edge_type(omitted_edges)
        metrics = self._metrics(
            nodes,
            edges,
            clusters,
            articles,
            context,
            len(omitted_edges),
            omitted_by_type,
        )
        limitations = list(output.limitations)
        risk_flags = ["llm_evidence_graph_generated"]
        if articles_truncated:
            limitations.append("输入文章数量超过配置上限，图谱仅分析确定性截取的文章。")
            risk_flags.append("evidence_graph_input_truncated")
        if content_truncated:
            limitations.append("部分文章正文超过模型输入上限，图谱仅分析截取范围内的正文。")
            risk_flags.append("evidence_graph_input_truncated")
        if len(nodes_by_id) > self.max_nodes:
            limitations.append("模型生成节点超过配置上限，已按稳定顺序截断。")
            risk_flags.append("evidence_graph_input_truncated")
        if omitted_edges:
            limitations.append("图谱关系超过配置上限，已按稳定顺序截断。")
            risk_flags.append("evidence_graph_relation_edges_truncated")
        if context.duplicate_map:
            limitations.append("转载或高度重复文章保留在图中，但不增加独立来源数量。")
            risk_flags.append("duplicate_reprints_present")
        if metrics.contradiction_edge_count:
            risk_flags.append("conflicting_claims_present")
        if metrics.update_edge_count:
            risk_flags.append("evolving_information")
        if any(ClaimExtractor.contains_instruction(article.content) for article in articles):
            risk_flags.append("untrusted_instruction_ignored")
        limitations.append("图谱结构指标仅描述当前输入材料，不代表事实真实性概率。")

        return EvidenceGraphResponse(
            event_id=event.event_id,
            summary=output.summary,
            nodes=nodes,
            edges=edges,
            claim_clusters=clusters,
            timeline=timeline,
            metrics=metrics,
            key_findings=self._stable_unique(key_findings),
            risk_flags=self._stable_unique(risk_flags),
            limitations=self._stable_unique(limitations),
            analysis_method="llm",
            fallback_used=False,
        )

    def _base_nodes(
        self,
        event: EventContext,
        articles: list[Article],
    ) -> tuple[list[EvidenceGraphNode], _GraphContext]:
        descriptors = [
            SourceDescriptor(source=article.source, url=article.url)
            for article in articles
        ]
        assignments = self.source_clusterer.cluster_indices(descriptors)
        duplicate_map = self._duplicate_map(articles)
        groups: dict[int, list[int]] = {}
        for index, assignment in enumerate(assignments):
            groups.setdefault(assignment, []).append(index)

        nodes = []
        event_id = f"event:{self._digest(str(event.event_id or 'unknown'))}"
        nodes.append(
            EvidenceGraphNode(
                node_id=event_id,
                node_type="event",
                label=event.title.strip() or f"事件 {event.event_id or 'unknown'}",
                attributes={
                    "event_id": event.event_id,
                    "title": event.title,
                    "update_time": event.update_time,
                },
            )
        )

        source_id_by_assignment = {}
        source_node_ids = {}
        for assignment, indices in sorted(groups.items(), key=lambda item: min(item[1])):
            identities = [self.source_clusterer.identity(descriptors[index]) for index in indices]
            identity_payload = identities if any(any(item) for item in identities) else [("unknown", min(indices))]
            node_id = f"source:{self._digest(json.dumps(identity_payload, ensure_ascii=False, sort_keys=True))}"
            source_id_by_assignment[assignment] = node_id
            names = self._stable_unique([articles[index].source for index in indices])
            hosts = self._stable_unique(
                [urlparse(articles[index].url).hostname or "" for index in indices]
            )
            nodes.append(
                EvidenceGraphNode(
                    node_id=node_id,
                    node_type="source",
                    label=names[0] if names else next(iter(hosts), "未知来源"),
                    attributes={
                        "source_names": names,
                        "hosts": hosts,
                        "article_count": len(indices),
                    },
                )
            )
            for index in indices:
                source_node_ids[index] = node_id

        article_node_ids = {}
        node_article_indices = {}
        for index, article in enumerate(articles):
            identity = {
                "news_id": normalized_news_id(article.news_id),
                "url": self.retriever._normalized_url(article.url),
                "title": self._normalize(article.title),
                "source": self._normalize(article.source),
                "index": index if normalized_news_id(article.news_id) is None else None,
            }
            node_id = f"article:{self._digest(json.dumps(identity, ensure_ascii=False, sort_keys=True))}"
            article_node_ids[index] = node_id
            node_article_indices[node_id] = index
            nodes.append(
                EvidenceGraphNode(
                    node_id=node_id,
                    node_type="article",
                    label=article.title.strip() or f"文章 {article.news_id or index + 1}",
                    attributes={
                        "news_id": article.news_id,
                        "source": article.source,
                        "url": article.url,
                        "publish_time": article.publish_time,
                        "platform": article.platform,
                        "duplicate_of": (
                            article_node_ids.get(duplicate_map.get(index, -1))
                            if index in duplicate_map
                            else None
                        ),
                    },
                )
            )
        return nodes, _GraphContext(
            article_node_ids=article_node_ids,
            source_node_ids=source_node_ids,
            source_assignments=assignments,
            duplicate_map=duplicate_map,
            node_article_indices=node_article_indices,
        )

    def _base_edges(
        self,
        event: EventContext,
        articles: list[Article],
        context: _GraphContext,
        retained_ids: set[str],
    ) -> list[EvidenceGraphEdge]:
        event_id = f"event:{self._digest(str(event.event_id or 'unknown'))}"
        edges = []
        for index, article_node_id in context.article_node_ids.items():
            source_node_id = context.source_node_ids[index]
            if event_id in retained_ids and article_node_id in retained_ids:
                edges.append(self._edge("contains", event_id, article_node_id))
            if article_node_id in retained_ids and source_node_id in retained_ids:
                edges.append(self._edge("published_by", article_node_id, source_node_id))
            duplicate_index = context.duplicate_map.get(index)
            if duplicate_index is not None:
                duplicate_node_id = context.article_node_ids[duplicate_index]
                if article_node_id in retained_ids and duplicate_node_id in retained_ids:
                    edges.append(
                        self._edge(
                            "duplicates",
                            article_node_id,
                            duplicate_node_id,
                            reason_code="validated_duplicate",
                        )
                    )
        for node_id, article_index in context.node_article_indices.items():
            if not node_id.startswith(("claim:", "evidence:")):
                continue
            article_node_id = context.article_node_ids[article_index]
            if node_id in retained_ids and article_node_id in retained_ids:
                edges.append(self._edge("asserts", article_node_id, node_id))
        return edges

    def _validated_model_edges(
        self,
        output: EvidenceGraphLLMOutput,
        articles: list[Article],
        context: _GraphContext,
        model_id_map: dict[str, str],
        retained_ids: set[str],
    ) -> list[EvidenceGraphEdge]:
        edges = []
        seen_ids = set()
        seen_semantics = set()
        for edge in output.edges:
            if edge.id in seen_ids:
                continue
            seen_ids.add(edge.id)
            if self._is_uninformative(edge.explanation):
                continue
            source_id = model_id_map.get(edge.source)
            target_id = model_id_map.get(edge.target)
            if (
                not source_id
                or not target_id
                or source_id == target_id
                or source_id not in retained_ids
                or target_id not in retained_ids
            ):
                continue
            source_index = context.node_article_indices.get(source_id)
            target_index = context.node_article_indices.get(target_id)
            if (
                edge.relation in self._semantic_relations
                and source_index is not None
                and source_index == target_index
            ):
                continue

            quote_index = self._resolve_edge_quote_article(
                edge.news_id,
                edge.quote,
                articles,
                source_index,
                target_index,
            )
            if edge.news_id is not None and quote_index is None:
                continue
            if edge.quote and quote_index is None:
                continue
            if edge.relation in {"quotes", "reposts"} and not self._has_explicit_reference(
                articles,
                source_index,
                target_index,
            ):
                continue
            semantic_key = (
                edge.relation,
                source_id,
                target_id,
                self._normalize(edge.quote or ""),
            )
            if semantic_key in seen_semantics:
                continue
            seen_semantics.add(semantic_key)
            attributes = {
                "confidence": edge.confidence,
                "news_id": (
                    articles[quote_index].news_id if quote_index is not None else edge.news_id
                ),
                "analysis_method": "llm",
            }
            if source_index is not None and target_index is not None:
                known = self._source_known(articles[source_index]) and self._source_known(
                    articles[target_index]
                )
                attributes["source_independence_known"] = known
                attributes["independent_sources"] = (
                    known
                    and context.source_assignments[source_index]
                    != context.source_assignments[target_index]
                    and source_index not in context.duplicate_map
                    and target_index not in context.duplicate_map
                )
            edges.append(
                self._edge(
                    edge.relation,
                    source_id,
                    target_id,
                    label=edge.label,
                    explanation=edge.explanation,
                    quote=edge.quote,
                    reason_code="llm_semantic_relation",
                    attributes=attributes,
                )
            )
        return edges

    def _claim_clusters(
        self,
        nodes: list[EvidenceGraphNode],
        edges: list[EvidenceGraphEdge],
        articles: list[Article],
        context: _GraphContext,
    ) -> list[EvidenceClaimCluster]:
        claim_ids = {
            node.node_id for node in nodes if node.node_type in {"claim", "evidence"}
        }
        parents = {node_id: node_id for node_id in claim_ids}

        def find(node_id: str) -> str:
            while parents[node_id] != node_id:
                parents[node_id] = parents[parents[node_id]]
                node_id = parents[node_id]
            return node_id

        def union(left: str, right: str) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parents[max(left_root, right_root)] = min(left_root, right_root)

        for edge in edges:
            if (
                edge.edge_type in self._semantic_relations
                and edge.source_node_id in claim_ids
                and edge.target_node_id in claim_ids
            ):
                union(edge.source_node_id, edge.target_node_id)
        groups: dict[str, list[str]] = {}
        for node_id in sorted(claim_ids):
            groups.setdefault(find(node_id), []).append(node_id)

        clusters = []
        for members in groups.values():
            member_set = set(members)
            related = [
                edge
                for edge in edges
                if edge.source_node_id in member_set and edge.target_node_id in member_set
            ]
            article_indices = {
                context.node_article_indices[node_id]
                for node_id in members
                if node_id in context.node_article_indices
            }
            source_groups = {
                context.source_assignments[index]
                for index in article_indices
                if index not in context.duplicate_map and self._source_known(articles[index])
            }
            supporting_groups = self._relation_source_groups(
                related, {"supports", "same_fact"}, context
            )
            contradicting_groups = self._relation_source_groups(
                related, {"contradicts"}, context
            )
            updating_groups = self._relation_source_groups(
                related, {"updates", "adds_detail"}, context
            )
            if any(
                edge.edge_type == "contradicts"
                and edge.attributes.get("independent_sources", False)
                for edge in related
            ):
                status = "conflicting"
            elif any(edge.edge_type in {"updates", "adds_detail"} for edge in related):
                status = "evolving"
            elif len(supporting_groups) >= 2:
                status = "supported"
            else:
                status = "unresolved"
            article_node_ids = sorted(
                {
                    context.article_node_ids[index]
                    for index in article_indices
                    if context.article_node_ids[index] in {node.node_id for node in nodes}
                }
            )
            cluster_payload = json.dumps(sorted(members), ensure_ascii=False)
            clusters.append(
                EvidenceClaimCluster(
                    cluster_id=f"cluster:{self._digest(cluster_payload)}",
                    claim_type="semantic_claim",
                    canonical_slots={},
                    polarity="mixed" if status == "conflicting" else "asserted",
                    certainty="model_extracted",
                    certainty_values=["model_extracted"],
                    verifiable=True,
                    claim_node_ids=sorted(members),
                    article_node_ids=article_node_ids,
                    independent_source_count=len(source_groups),
                    asserting_independent_source_count=len(source_groups),
                    supporting_independent_source_count=len(supporting_groups),
                    contradicting_independent_source_count=len(contradicting_groups),
                    updating_independent_source_count=len(updating_groups),
                    status=status,
                )
            )
        return sorted(clusters, key=lambda item: item.cluster_id)

    def _timeline(
        self,
        nodes: list[EvidenceGraphNode],
        edges: list[EvidenceGraphEdge],
        articles: list[Article],
        context: _GraphContext,
    ) -> list[EvidenceTimelineEntry]:
        sortable = []
        for node in nodes:
            if node.node_type not in {"claim", "evidence"}:
                continue
            article_index = context.node_article_indices.get(node.node_id)
            if article_index is None or article_index in context.duplicate_map:
                continue
            article = articles[article_index]
            quote = str(node.attributes.get("quote") or "").strip()
            if not quote:
                continue
            extracted = self.extractor.extract(
                article.model_copy(update={"content": quote}),
                max_claims=5,
            )
            claim = extracted[0] if extracted else AtomicClaim(
                text=quote,
                target_quote=quote,
                claim_type="semantic_claim",
                certainty="asserted",
                polarity="affirmative",
                modality_reason=None,
                slots={},
                verifiable=True,
            )
            resolved = self.evolution_analyzer.resolve_time(claim, article.publish_time)
            if not resolved:
                continue
            related_ids = sorted(
                edge.edge_id
                for edge in edges
                if edge.edge_type in {"updates", "adds_detail"}
                and node.node_id in {edge.source_node_id, edge.target_node_id}
            )
            entry = EvidenceTimelineEntry(
                timeline_id=f"timeline:{self._digest(node.node_id + resolved.display)}",
                time=resolved.display,
                time_source=resolved.source,
                time_precision=resolved.precision,
                year_inferred=resolved.year_inferred,
                normalized_time=resolved.normalized_time,
                article_node_id=context.article_node_ids[article_index],
                claim_node_id=node.node_id,
                claim_type=claim.claim_type,
                summary=quote,
                related_edge_ids=related_ids,
            )
            sortable.append((resolved.sort_key, node.node_id, entry))
        sortable.sort(key=lambda item: item[:2])
        return [item[2] for item in sortable]

    def _metrics(
        self,
        nodes: list[EvidenceGraphNode],
        edges: list[EvidenceGraphEdge],
        clusters: list[EvidenceClaimCluster],
        articles: list[Article],
        context: _GraphContext,
        omitted_count: int,
        omitted_by_type: dict[str, int],
    ) -> EvidenceGraphMetrics:
        semantic_edges = [
            edge for edge in edges if edge.edge_type in self._semantic_relations
        ]
        support_count = sum(edge.edge_type == "supports" for edge in semantic_edges)
        contradiction_count = sum(
            edge.edge_type == "contradicts" for edge in semantic_edges
        )
        update_count = sum(edge.edge_type == "updates" for edge in semantic_edges)
        known_sources = {
            context.source_assignments[index]
            for index, article in enumerate(articles)
            if index not in context.duplicate_map and self._source_known(article)
        }
        verifiable = [cluster for cluster in clusters if cluster.verifiable]
        conflicting = sum(cluster.status == "conflicting" for cluster in verifiable)
        unresolved = sum(cluster.status == "unresolved" for cluster in verifiable)
        return EvidenceGraphMetrics(
            article_count=len(articles),
            source_count=len(set(context.source_assignments)),
            independent_source_count=len(known_sources),
            claim_count=sum(
                node.node_type in {"claim", "evidence"} for node in nodes
            ),
            claim_cluster_count=len(clusters),
            support_edge_count=support_count,
            contradiction_edge_count=contradiction_count,
            update_edge_count=update_count,
            duplicate_article_count=len(context.duplicate_map),
            conflict_ratio=self._ratio(conflicting, len(verifiable)),
            reprint_ratio=self._ratio(len(context.duplicate_map), len(articles)),
            unresolved_claim_ratio=self._ratio(unresolved, len(verifiable)),
            conflicting_cluster_count=conflicting,
            verifiable_cluster_count=len(verifiable),
            contradiction_edge_ratio=self._ratio(
                contradiction_count, len(semantic_edges)
            ),
            not_verifiable_cluster_count=0,
            logical_edge_count=len(edges) + omitted_count,
            returned_edge_count=len(edges),
            omitted_relation_edge_count=omitted_count,
            omitted_edge_count_by_type=omitted_by_type,
        )

    def _resolve_article_index(
        self,
        articles: list[Article],
        news_id: int | str | None,
        source: str | None,
        quote: str | None,
        label: str,
        node_type: str,
    ) -> int | None:
        if news_id is not None:
            key = normalized_news_id(news_id)
            match = next(
                (
                    index
                    for index, article in enumerate(articles)
                    if normalized_news_id(article.news_id) == key
                ),
                None,
            )
            if match is None:
                return None
            article = articles[match]
            if source and self._normalize(source) != self._normalize(article.source):
                return None
            if quote and not self._quote_in_article(quote, article):
                return None
            return match
        if quote:
            matches = [
                index
                for index, article in enumerate(articles)
                if self._quote_in_article(quote, article)
                and (not source or self._normalize(source) == self._normalize(article.source))
            ]
            if len(matches) == 1:
                return matches[0]
        if node_type == "article":
            matches = [
                index
                for index, article in enumerate(articles)
                if self._normalize(label) == self._normalize(article.title)
            ]
            if len(matches) == 1:
                return matches[0]
        if source:
            matches = [
                index
                for index, article in enumerate(articles)
                if self._normalize(source) == self._normalize(article.source)
            ]
            if len(matches) == 1 or (node_type == "source" and matches):
                return matches[0]
        return None

    def _resolve_edge_quote_article(
        self,
        news_id: int | str | None,
        quote: str | None,
        articles: list[Article],
        source_index: int | None,
        target_index: int | None,
    ) -> int | None:
        if news_id is not None:
            index = self._resolve_article_index(
                articles, news_id, None, quote, "", "evidence"
            )
            return index
        if not quote:
            return source_index if source_index is not None else target_index
        candidates = self._stable_unique_ints(
            [
                index
                for index in (source_index, target_index)
                if index is not None
            ]
            + list(range(len(articles)))
        )
        return next(
            (
                index
                for index in candidates
                if self._quote_in_article(quote, articles[index])
            ),
            None,
        )

    def _has_explicit_reference(
        self,
        articles: list[Article],
        source_index: int | None,
        target_index: int | None,
    ) -> bool:
        if source_index is None or target_index is None or source_index == target_index:
            return False
        source = articles[source_index]
        target = articles[target_index]
        target_news_id = normalized_news_id(target.news_id)
        quoted_ids = {
            normalized_news_id(value)
            for value in source.quoted_news_ids
            if normalized_news_id(value) is not None
        }
        normalized_target_url = self.retriever._normalized_url(target.url)
        reference_urls = {
            self.retriever._normalized_url(value)
            for value in source.reference_urls
            if self.retriever._normalized_url(value)
        }
        return bool(
            (target_news_id is not None and target_news_id in quoted_ids)
            or (normalized_target_url and normalized_target_url in reference_urls)
        )

    def _duplicate_map(self, articles: list[Article]) -> dict[int, int]:
        representatives = []
        duplicates = {}
        for index, article in enumerate(articles):
            for representative in representatives:
                if self.retriever.graph_duplicate_decision(
                    article, articles[representative]
                ).is_duplicate:
                    duplicates[index] = representative
                    break
            else:
                representatives.append(index)
        return duplicates

    def _limit_nodes(self, nodes: list[EvidenceGraphNode]) -> list[EvidenceGraphNode]:
        return sorted(
            nodes,
            key=lambda node: (self._node_order[node.node_type], node.node_id),
        )[: self.max_nodes]

    def _stable_edges(self, edges: list[EvidenceGraphEdge]) -> list[EvidenceGraphEdge]:
        result = []
        seen = set()
        for edge in sorted(
            edges,
            key=lambda item: (
                0 if item.attributes.get("analysis_method") == "llm" else 1,
                self._edge_order[item.edge_type],
                item.source_node_id,
                item.target_node_id,
                item.edge_id,
            ),
        ):
            identity = (
                edge.edge_type,
                edge.source_node_id,
                edge.target_node_id,
                edge.quote or "",
            )
            if identity not in seen:
                seen.add(identity)
                result.append(edge)
        return result

    def _edge(
        self,
        edge_type: str,
        source: str,
        target: str,
        *,
        label: str | None = None,
        explanation: str | None = None,
        quote: str | None = None,
        reason_code: str | None = None,
        attributes: dict | None = None,
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
            label=label,
            explanation=explanation,
            quote=quote,
            reason_code=reason_code,
            attributes=attributes or {},
        )

    def _relation_source_groups(
        self,
        edges: list[EvidenceGraphEdge],
        edge_types: set[str],
        context: _GraphContext,
    ) -> set[int]:
        groups = set()
        for edge in edges:
            if edge.edge_type not in edge_types:
                continue
            for node_id in (edge.source_node_id, edge.target_node_id):
                index = context.node_article_indices.get(node_id)
                if index is not None and index not in context.duplicate_map:
                    groups.add(context.source_assignments[index])
        return groups

    @staticmethod
    def _quote_in_article(quote: str, article: Article) -> bool:
        normalized = quote.strip()
        return bool(
            normalized
            and (normalized in article.content or normalized in article.title)
        )

    @staticmethod
    def _source_known(article: Article) -> bool:
        return bool(article.source.strip() or (urlparse(article.url).hostname or ""))

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split()).strip().lower()

    @classmethod
    def _is_uninformative(cls, value: str) -> bool:
        normalized = value.strip().rstrip("。！？；;,.， ")
        return any(normalized == phrase for phrase in cls._uninformative_phrases)

    @staticmethod
    def _stable_unique(values: list[str]) -> list[str]:
        result = []
        for value in values:
            normalized = value.strip()
            if normalized and normalized not in result:
                result.append(normalized)
        return result

    @staticmethod
    def _stable_unique_ints(values: list[int]) -> list[int]:
        result = []
        for value in values:
            if value not in result:
                result.append(value)
        return result

    @staticmethod
    def _counts_by_edge_type(edges: list[EvidenceGraphEdge]) -> dict[str, int]:
        result = {}
        for edge in edges:
            result[edge.edge_type] = result.get(edge.edge_type, 0) + 1
        return result

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
