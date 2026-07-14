from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.verification import VerificationRequest, VerificationResponse
from app.services.verification_service import (
    TargetArticleNotFoundError,
    VerificationService,
    get_verification_service,
)


router = APIRouter(prefix="/ai", tags=["verification"])


@router.post(
    "/verify",
    response_model=VerificationResponse,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "待核验文章不在当前事件数据中"
        }
    },
)
def verify_article(
    request: VerificationRequest,
    service: VerificationService = Depends(get_verification_service),
) -> VerificationResponse:
    try:
        return service.verify(
            request.event,
            request.target_news_id,
            request.max_claims,
        )
    except TargetArticleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="待核验文章不在当前事件数据中",
        ) from exc
