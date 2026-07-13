from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.news_identity import normalized_news_id
from app.schemas.event import EventContext


GraphNodeType = Literal["event", "article", "source", "claim"]
GraphEdgeType = Literal[
    "contains",
    "published_by",
    "asserts",
    "supports",
    "contradicts",
    "updates",
    "duplicates",
]
ClaimClusterStatus = Literal[
    "supported",
    "conflicting",
    "evolving",
    "unresolved",
    "not_verifiable",
]
TimelineTimeSource = Literal["reference_time", "event_time", "publish_time"]
TimelineTimePrecision = Literal[
    "full_datetime",
    "full_date",
    "month_day_time",
    "month_day",
    "time_only",
    "publish_datetime",
]


class EvidenceGraphRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: EventContext

    @model_validator(mode="after")
    def validate_unique_news_ids(self):
        seen = set()
        for article in self.event.articles:
            key = normalized_news_id(article.news_id)
            if key is None:
                continue
            if key in seen:
                raise ValueError("证据图事件中的非空news_id必须唯一")
            seen.add(key)
        return self


class EvidenceGraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    node_type: GraphNodeType
    label: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class EvidenceGraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str
    edge_type: GraphEdgeType
    source_node_id: str
    target_node_id: str
    quote: str | None = None
    reason_code: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class EvidenceClaimCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cluster_id: str
    claim_type: str
    canonical_slots: dict[str, Any] = Field(default_factory=dict)
    polarity: str
    certainty: str
    certainty_values: list[str] = Field(default_factory=list)
    verifiable: bool = True
    claim_node_ids: list[str] = Field(default_factory=list)
    article_node_ids: list[str] = Field(default_factory=list)
    independent_source_count: int = Field(ge=0)
    asserting_independent_source_count: int = Field(default=0, ge=0)
    supporting_independent_source_count: int = Field(default=0, ge=0)
    contradicting_independent_source_count: int = Field(default=0, ge=0)
    updating_independent_source_count: int = Field(default=0, ge=0)
    status: ClaimClusterStatus


class EvidenceTimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeline_id: str
    time: str
    time_source: TimelineTimeSource
    time_precision: TimelineTimePrecision
    year_inferred: bool = False
    normalized_time: str | None = None
    article_node_id: str
    claim_node_id: str
    claim_type: str
    summary: str
    related_edge_ids: list[str] = Field(default_factory=list)


class EvidenceGraphMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    article_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    independent_source_count: int = Field(ge=0)
    claim_count: int = Field(ge=0)
    claim_cluster_count: int = Field(ge=0)
    support_edge_count: int = Field(ge=0)
    contradiction_edge_count: int = Field(ge=0)
    update_edge_count: int = Field(ge=0)
    duplicate_article_count: int = Field(ge=0)
    conflict_ratio: float = Field(ge=0, le=1)
    reprint_ratio: float = Field(ge=0, le=1)
    unresolved_claim_ratio: float = Field(ge=0, le=1)
    conflicting_cluster_count: int = Field(default=0, ge=0)
    verifiable_cluster_count: int = Field(default=0, ge=0)
    contradiction_edge_ratio: float = Field(default=0, ge=0, le=1)
    not_verifiable_cluster_count: int = Field(default=0, ge=0)
    logical_edge_count: int = Field(default=0, ge=0)
    returned_edge_count: int = Field(default=0, ge=0)
    omitted_relation_edge_count: int = Field(default=0, ge=0)
    omitted_edge_count_by_type: dict[str, int] = Field(default_factory=dict)


class EvidenceGraphResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: int | str | None = None
    nodes: list[EvidenceGraphNode] = Field(default_factory=list)
    edges: list[EvidenceGraphEdge] = Field(default_factory=list)
    claim_clusters: list[EvidenceClaimCluster] = Field(default_factory=list)
    timeline: list[EvidenceTimelineEntry] = Field(default_factory=list)
    metrics: EvidenceGraphMetrics
    risk_flags: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
