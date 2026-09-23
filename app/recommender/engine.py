"""Подбор подрядчиков: валидация, фильтрация, ранжирование и карточки."""

import math
from collections.abc import Iterable
from datetime import date as CalendarDate
from typing import Literal, TypedDict

from app.data.models import Contractor
from app.recommender.explanations import explain_contractor
from app.recommender.filters import filter_contractors
from app.recommender.scoring import rank_contractors


CALENDAR_START = CalendarDate(2026, 9, 23)
CALENDAR_END = CalendarDate(2026, 12, 31)

RecommendationStatus = Literal[
    "found",
    "category_not_found",
    "no_match",
]


class RecommendationCard(TypedDict):
    id: str
    name: str
    category: str
    city: str
    price: int | float
    score: float
    explanation: str


class RecommendationResponse(TypedDict):
    status: RecommendationStatus
    count: int
    results: list[RecommendationCard]
    rejection_summary: dict[str, int]


def _validate_text(value: str, field: str) -> None:
    """Проверить строку, не изменяя её содержимое."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}: требуется непустая строка")


def _validate_number(
    value: int | float,
    field: str,
    *,
    allow_zero: bool,
) -> None:
    """Не принимать boolean, строки, бесконечность и NaN."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field}: требуется число")

    try:
        finite = math.isfinite(value)
    except OverflowError as exc:
        raise ValueError(f"{field}: слишком большое число") from exc

    if not finite:
        raise ValueError(f"{field}: число должно быть конечным")

    if value < 0 or (value == 0 and not allow_zero):
        condition = "неотрицательным" if allow_zero else "положительным"
        raise ValueError(f"{field}: число должно быть {condition}")


def _validate_request(
    city: str,
    date: str,
    event_type: str,
    category: str,
    budget: int | float,
    language: str | None,
    duration: int | float | None,
) -> None:
    _validate_text(city, "city")
    _validate_text(date, "date")
    _validate_text(event_type, "event_type")
    _validate_text(category, "category")

    try:
        parsed_date = CalendarDate.fromisoformat(date)
    except ValueError as exc:
        raise ValueError(
            "date: требуется корректная дата в формате YYYY-MM-DD"
        ) from exc

    if parsed_date.isoformat() != date:
        raise ValueError("date: требуется формат YYYY-MM-DD")

    if not CALENDAR_START <= parsed_date <= CALENDAR_END:
        raise ValueError(
            "date: календарь доступен только "
            "с 2026-09-23 по 2026-12-31 включительно"
        )

    _validate_number(budget, "budget", allow_zero=True)

    if language is not None:
        _validate_text(language, "language")

    if duration is not None:
        _validate_number(duration, "duration", allow_zero=False)


def recommend(
    contractors: Iterable[Contractor],
    city: str,
    date: str,
    event_type: str,
    category: str,
    budget: int | float,
    language: str | None = None,
    duration: int | float | None = None,
) -> RecommendationResponse:
    """Вернуть до трёх подрядчиков из нормализованного каталога.

    Каталог предварительно загружается через load_contractors.
    date передаётся строкой YYYY-MM-DD.
    Некорректные параметры запроса вызывают ValueError.

    Значения города, категории, формата и языка сравниваются точно:
    функция не меняет регистр, пробелы или условия запроса.

    price содержит числовую стартовую цену в тенге.
    В explanation цена обозначается как «от».

    Файлы не читаются, исходные записи не изменяются.
    Результат состоит только из JSON-совместимых типов.
    """
    _validate_request(
        city=city,
        date=date,
        event_type=event_type,
        category=category,
        budget=budget,
        language=language,
        duration=duration,
    )

    filtered = filter_contractors(
        contractors=contractors,
        city=city,
        date=date,
        event_type=event_type,
        category=category,
        budget=budget,
        language=language,
        duration=duration,
    )

    status: RecommendationStatus
    if filtered["city_category_count"] == 0:
        status = "category_not_found"
    elif not filtered["candidates"]:
        status = "no_match"
    else:
        status = "found"

    ranked = rank_contractors(
        contractors=filtered["candidates"],
        budget=budget,
    )

    results: list[RecommendationCard] = []

    for item in ranked[:3]:
        contractor = item["contractor"]

        results.append(
            {
                "id": contractor["id"],
                "name": contractor["anon_name"],
                "category": category,
                "city": contractor["city"],
                "price": contractor["price_from_kzt"],
                "score": item["score"],
                "explanation": explain_contractor(
                    contractor=contractor,
                    city=city,
                    date=date,
                    event_type=event_type,
                    category=category,
                    budget=budget,
                    language=language,
                    duration=duration,
                ),
            }
        )

    return {
        "status": status,
        "count": len(results),
        "results": results,
        "rejection_summary": filtered["rejection_summary"],
    }