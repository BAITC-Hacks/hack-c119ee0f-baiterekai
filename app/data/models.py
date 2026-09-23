"""Normalized catalogue records, represented by ordinary Python dictionaries."""

from typing import TypedDict


class Contractor(TypedDict):
    id: str
    anon_name: str
    categories: list[str]
    city: str
    price_from_kzt: int | float
    event_formats: list[str]
    languages: list[str]
    max_hours: int | float | None
    busy_dates: list[str]
    description: str
    synthetic: bool
    city_imputed: bool
    price_imputed: bool
