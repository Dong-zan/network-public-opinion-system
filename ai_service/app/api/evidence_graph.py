from fastapi import APIRouter, Depends

from app.schemas.evidence_graph import EvidenceGraphRequest, EvidenceGraphResponse
from app.services.evidence_graph_generation_service import (
    EvidenceGraphGenerationService,
    get_evidence_graph_generation_service,
)


router = APIRouter(prefix="/ai", tags=["evidence-graph"])


@router.post("/evidence-graph", response_model=EvidenceGraphResponse)
def build_evidence_graph(
    request: EvidenceGraphRequest,
    service: EvidenceGraphGenerationService = Depends(
        get_evidence_graph_generation_service
    ),
) -> EvidenceGraphResponse:
    return service.build(request.event)
