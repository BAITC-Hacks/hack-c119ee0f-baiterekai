"""Детерминированные объяснения на основе каталога и запроса."""

import re
from collections.abc import Mapping

from app.data.models import Contractor


_EVENT_STEMS: dict[str, tuple[str, ...]] = {
    "свадьба": ("свадьб", "свадеб"),
    "той": ("той", "тоя"),
    "корпоратив": ("корпоратив",),
    "конференция": ("конференц",),
    "юбилей": ("юбиле",),
    "день рождения": ("день рождения", "дня рождения"),
}

_FACT_MARKERS = (
    "опыт",
    "репертуар",
    "вместимость",
    "вмещ",
    "состав",
    "специализ",
    "оформлен",
    "съем",
    "съём",
    "снима",
    "производ",
    "церемон",
    "провод",
    "веду",
)

_PROMOTIONAL_PATTERN = re.compile(
    r"\b(?:лучш|идеальн|профессионал|отличн|гарант|"
    r"премиальн|востребован|незабываем|великолеп|"
    r"безупреч|качествен|уникальн|роскош)\w*",
    re.IGNORECASE,
)

_REJECTION_LABELS = (
    ("busy", "заняты на выбранную дату"),
    ("budget", "стартовая цена выше бюджета"),
    ("event_format", "не указан нужный формат"),
    ("language", "не указан запрошенный язык"),
    ("duration", "максимальная длительность меньше запрошенной"),
)


def _format_number(value: int | float) -> str:
    """Отформатировать число без округления."""
    text = format(value, ",")
    if text.endswith(".0"):
        text = text[:-2]
    return text.replace(",", " ").replace(".", ",")


def _description_fact(
    description: str,
    event_type: str,
    category: str,
) -> str | None:
    """Выбрать короткую цитату с признаками услуги.

    Это поиск по словам, а не семантический анализ.
    Текст не перефразируется. Фрагменты с заданными рекламными
    словами пропускаются. Если подходящего фрагмента нет,
    возвращается None.
    """
    event_stems = _EVENT_STEMS.get(
        event_type.casefold(),
        (event_type.casefold(),),
    )
    category_stems = tuple(
        word[:5]
        for word in re.findall(r"\w+", category.casefold())
        if len(word) >= 4
    )

    best_fragment: str | None = None
    best_priority = -1

    fragments = re.split(r"(?<=[.!?])\s+|[\r\n•]+", description)
    fragments.extend(
        match.group(0)
        for match in re.finditer(
            r"\bопыт\w*\s+(?:[а-яё-]+\s+){0,5}\d+\s+(?:лет|год(?:а|ов)?)\b",
            description,
            flags=re.IGNORECASE,
        )
    )

    for sentence in fragments:
        fragment = sentence.strip().rstrip(".!?")

        if not 20 <= len(fragment) <= 240:
            continue
        if _PROMOTIONAL_PATTERN.search(fragment):
            continue

        lowered = fragment.casefold()
        mentions_event = any(
            stem in lowered for stem in event_stems
        )
        mentions_category = any(
            stem in lowered for stem in category_stems
        )
        has_service_detail = any(
            marker in lowered
            for marker in _FACT_MARKERS
            if marker not in ("веду", "провод")
        ) or re.search(
            r"\b(?:веду|ведёт|ведет|ведут|провожу|проводим|проводит|"
            r"проводят|проводил[аи]?|сценари\w*|репертуар\w*)\b",
            lowered,
        ) is not None

        if not (
            mentions_event
            or mentions_category
            or has_service_detail
        ):
            continue

        priority = (
            2 * int(mentions_event)
            + int(mentions_category)
            + 2 * int(has_service_detail)
        )

        if priority > best_priority:
            best_fragment = fragment
            best_priority = priority

    return best_fragment


def matched_factors(
    contractor: Contractor,
    language: str | None = None,
    duration: int | float | None = None,
) -> list[str]:
    """Вернуть факторы для подрядчика, уже прошедшего все фильтры."""
    factors = [
        "city",
        "category",
        "date",
        "budget",
        "event_format",
    ]

    if language is not None:
        factors.append("language")

    if duration is not None and contractor["max_hours"] is not None:
        factors.append("duration")

    return factors


def explain_contractor(
    contractor: Contractor,
    city: str,
    date: str,
    event_type: str,
    category: str,
    budget: int | float,
    language: str | None = None,
    duration: int | float | None = None,
) -> str:
    """Объяснить соответствие подрядчика проверенному запросу.

    Вызывать только после прохождения всех фильтров.
    Дата должна находиться внутри известного окна календаря.
    Функция не проверяет запрос повторно и не меняет запись.
    """
    details = [
        f"Город — {city}",
        f"категория — «{category}»",
        f"формат — «{event_type}»",
        f"по календарю свободен на {date}",
        (
            f"цена от {_format_number(contractor['price_from_kzt'])} ₸ "
            f"при бюджете {_format_number(budget)} ₸"
        ),
    ]

    if language is not None:
        details.append(
            f"указан запрошенный язык — {language}"
        )

    if duration is not None:
        max_hours = contractor["max_hours"]

        if max_hours is None:
            details.append(
                "услуга не привязана к длительности присутствия"
            )
        else:
            details.append(
                f"запрошено {_format_number(duration)} ч, "
                f"доступная длительность — до "
                f"{_format_number(max_hours)} ч"
            )

    details.append(
        "соответствие бюджету рассчитано по стартовой цене, "
        "итоговую стоимость нужно уточнить"
    )
    explanation = "; ".join(details) + "."

    fact = _description_fact(
        contractor["description"],
        event_type,
        category,
    )

    if fact is not None:
        explanation += f" Из описания профиля: «{fact}»."

    return explanation


def explain_selection(
    city: str,
    category: str,
    city_category_count: int,
    passed_count: int,
    rejection_summary: Mapping[str, int],
) -> str:
    """Объяснить итог отбора с предполагаемым показом до трёх карточек.

    passed_count — число всех прошедших фильтры до ограничения TOP-3.
    Статистика условий относится только к выбранным городу и категории.
    """
    if city_category_count == 0:
        return (
            f"В каталоге города «{city}» "
            f"нет подрядчиков категории «{category}»."
        )

    reasons = [
        f"{label} — {rejection_summary[key]}"
        for key, label in _REJECTION_LABELS
        if rejection_summary[key] > 0
    ]

    if passed_count == 0:
        explanation = (
            f"По городу и категории найдено: {city_category_count}; "
            "всем условиям не соответствует ни один подрядчик."
        )
    elif passed_count < 3:
        explanation = (
            f"Найдено и показано: {passed_count}; "
            f"в каталоге по городу и категории — "
            f"{city_category_count}."
        )

        if not reasons:
            explanation += (
                " Все они подходят, но в этой выборке "
                "каталога меньше трёх подрядчиков."
            )
        else:
            explanation += (
                " Показано меньше трёх, поскольку остальные "
                "кандидаты исключены по условиям."
            )
    else:
        explanation = (
            f"Всем условиям соответствуют: {passed_count}; "
            "показаны первые 3 по ранжированию."
        )

    if reasons:
        explanation += (
            " Исключения по первой непройденной проверке: "
            + "; ".join(reasons)
            + ". Каждый исключённый профиль учтён один раз."
        )

    return explanation