from fastapi import APIRouter, Depends

from app.schemas.evidence_graph import EvidenceGraphRequest, EvidenceGraphResponse
from app.services.evidence_graph_service import (
    EvidenceGraphService,
    get_evidence_graph_service,
)


router = APIRouter(prefix="/ai", tags=["evidence-graph"])


@router.post("/evidence-graph", response_model=EvidenceGraphResponse)
def build_evidence_graph(
    request: EvidenceGraphRequest,
    service: EvidenceGraphService = Depends(get_evidence_graph_service),
) -> EvidenceGraphResponse:
    return service.build(request.event)
