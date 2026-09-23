"""Детерминированное ранжирование прошедших фильтры подрядчиков."""

from collections.abc import Iterable
from typing import TypedDict

from app.data.models import Contractor


class ScoredContractor(TypedDict):
    contractor: Contractor
    score: float


def score_contractor(
    contractor: Contractor,
    budget: int | float,
) -> float:
    """Вернуть долю бюджета, остающуюся после стартовой цены.

    Формула: (budget - price_from_kzt) / budget.

    Предусловия:
    - бюджет проверен и неотрицателен;
    - подрядчик прошёл фильтры;
    - стартовая цена не превышает бюджет.

    При нулевом бюджете прошедшая фильтры цена также равна нулю:
    возвращаем 1.0, избегая деления на ноль.

    Оценка не характеризует качество услуг и не гарантирует
    итоговую стоимость мероприятия.
    """
    if budget == 0:
        return 1.0

    return (budget - contractor["price_from_kzt"]) / budget


def rank_contractors(
    contractors: Iterable[Contractor],
    budget: int | float,
) -> list[ScoredContractor]:
    """Оценить и отсортировать всех прошедших фильтры подрядчиков.

    Сначала идут большие score, при равенстве — меньшие строковые id.
    Оценки перед сортировкой не округляются.
    Исходные записи не изменяются; ограничение TOP-3 здесь не применяется.
    """
    scored: list[ScoredContractor] = [
        {
            "contractor": contractor,
            "score": score_contractor(contractor, budget),
        }
        for contractor in contractors
    ]

    return sorted(
        scored,
        key=lambda item: (
            -item["score"],
            item["contractor"]["id"],
        ),
    )