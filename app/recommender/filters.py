"""Последовательная фильтрация нормализованного каталога подрядчиков."""

from collections.abc import Iterable
from typing import TypedDict

from app.data.models import Contractor


class FilterResult(TypedDict):
    candidates: list[Contractor]
    city_category_count: int
    rejection_summary: dict[str, int]


def normalize_text(value: str) -> str:
    """Получить ключ сравнения без изменения исходного значения."""
    return " ".join(value.split()).casefold()


def filter_contractors(
    contractors: Iterable[Contractor],
    city: str,
    date: str,
    event_type: str,
    category: str,
    budget: int | float,
    language: str | None = None,
    duration: int | float | None = None,
) -> FilterResult:
    """Отфильтровать каталог по уже проверенным параметрам запроса.

    date передаётся строкой YYYY-MM-DD.
    Каждый исключённый профиль учитывается по первой причине отказа.
    Порядок прошедших кандидатов сохраняется; исходные записи не меняются.
    """
    city_key = normalize_text(city)
    category_key = normalize_text(category)
    event_key = normalize_text(event_type)
    language_key = normalize_text(language) if language is not None else None
    candidates: list[Contractor] = []
    city_category_count = 0
    rejection_summary: dict[str, int] = {
        "city": 0,
        "category": 0,
        "busy": 0,
        "budget": 0,
        "event_format": 0,
        "language": 0,
        "duration": 0,
    }

    for contractor in contractors:
        if normalize_text(contractor["city"]) != city_key:
            rejection_summary["city"] += 1
            continue

        if not any(normalize_text(value) == category_key for value in contractor["categories"]):
            rejection_summary["category"] += 1
            continue

        city_category_count += 1

        if date in contractor["busy_dates"]:
            rejection_summary["busy"] += 1
            continue

        if contractor["price_from_kzt"] > budget:
            rejection_summary["budget"] += 1
            continue

        if not any(normalize_text(value) == event_key for value in contractor["event_formats"]):
            rejection_summary["event_format"] += 1
            continue

        if language_key is not None and not any(
            normalize_text(value) == language_key for value in contractor["languages"]
        ):
            rejection_summary["language"] += 1
            continue

        max_hours = contractor["max_hours"]
        if (
            duration is not None
            and max_hours is not None
            and duration > max_hours
        ):
            rejection_summary["duration"] += 1
            continue

        candidates.append(contractor)

    return {
        "candidates": candidates,
        "city_category_count": city_category_count,
        "rejection_summary": rejection_summary,
    }
