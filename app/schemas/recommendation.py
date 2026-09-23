from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class RecommendationRequest(BaseModel):
    city: str = Field(..., min_length=1)
    date: date
    event_type: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    budget: int = Field(..., gt=0)

    duration: int | None = Field(default=None, gt=0)
    language: str | None = Field(default=None, min_length=1)


class ContractorResult(BaseModel):
    id: str
    name: str
    category: str
    city: str
    price: int
    score: float
    explanation: str


class RecommendationResponse(BaseModel):
    status: Literal["found", "category_not_found", "no_match"]
    count: int
    results: list[ContractorResult] = Field(default_factory=list)
    rejection_summary: dict[str, int] = Field(default_factory=dict)