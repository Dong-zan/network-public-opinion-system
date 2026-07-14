from fastapi import APIRouter, Depends, HTTPException, status

from app.llm.base import LLMProviderError
from app.schemas.qa import AskRequest, AskResponse
from app.services.qa_service import QAService, get_qa_service


router = APIRouter(prefix="/ai", tags=["qa"])


@router.post("/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    service: QAService = Depends(get_qa_service),
) -> AskResponse:
    try:
        result = service.answer(request.event, request.question)
    except LLMProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 问答服务暂时不可用",
        ) from exc
    return AskResponse(answer=result.answer)
