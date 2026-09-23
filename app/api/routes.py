from fastapi import APIRouter, HTTPException, Request

from app.recommender.engine import recommend as recommend_contractors
from app.schemas.recommendation import (
    RecommendationRequest,
    RecommendationResponse,
)

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/recommend", response_model=RecommendationResponse)
def recommend(
    request: RecommendationRequest,
    http_request: Request,
) -> RecommendationResponse:
    try:
        result = recommend_contractors(
            contractors=http_request.app.state.contractors,
            city=request.city,
            date=request.date.isoformat(),
            event_type=request.event_type,
            category=request.category,
            budget=request.budget,
            language=request.language,
            duration=request.duration,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return RecommendationResponse(**result)