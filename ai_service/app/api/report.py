from fastapi import APIRouter, Depends, HTTPException, status

from app.llm.base import LLMProviderError
from app.schemas.report import ReportRequest, ReportResponse
from app.services.report_service import ReportService, get_report_service


router = APIRouter(prefix="/ai", tags=["report"])


@router.post("/report", response_model=ReportResponse)
def generate_report(
    request: ReportRequest,
    service: ReportService = Depends(get_report_service),
) -> ReportResponse:
    try:
        return service.generate(request.event)
    except LLMProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 报告服务暂时不可用",
        ) from exc
