"""Load the supplied UTF-8, comma-separated catalogue with pipe-separated lists."""

import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import math
from os import PathLike

from .models import Contractor


def _error(record: int, field: str, message: str) -> ValueError:
    return ValueError(f"Record {record}, field '{field}': {message}")


def _text(value: str, record: int, field: str) -> str:
    value = value.strip()
    if not value:
        raise _error(record, field, "must not be empty")
    return value


def _items(value: str, record: int, field: str) -> list[str]:
    if not value.strip():
        return []
    items = [item.strip() for item in value.split("|")]
    if any(not item for item in items):
        raise _error(record, field, "empty item in pipe-separated list")
    return items


def _boolean(value: str, record: int, field: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in ("true", "false"):
        raise _error(record, field, "expected true or false")
    return normalized == "true"


def _number(value: str, record: int, field: str) -> int | float:
    try:
        number = Decimal(value.strip())
    except InvalidOperation as exc:
        raise _error(record, field, "expected a finite number") from exc
    if not number.is_finite() or not math.isfinite(float(number)):
        raise _error(record, field, "expected a finite number")
    if number < 0 or (field == "max_hours" and number == 0):
        raise _error(record, field, "must be positive" if field == "max_hours" else "must be nonnegative")
    # Keep integer prices exact, including values above float's integer precision.
    return int(number) if number == number.to_integral_value() else float(number)


def _dates(value: str, record: int) -> list[str]:
    dates = _items(value, record, "busy_dates")
    for value in dates:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise _error(record, "busy_dates", f"invalid YYYY-MM-DD date: {value!r}") from exc
        if parsed.isoformat() != value:
            raise _error(record, "busy_dates", f"expected YYYY-MM-DD: {value!r}")
    return dates


def _normalize(row: dict[str, str], record: int) -> Contractor:
    hours = row["max_hours"].strip()
    return Contractor(
        id=_text(row["id"], record, "id"),
        anon_name=_text(row["anon_name"], record, "anon_name"),
        categories=_items(row["categories"], record, "categories"),
        city=_text(row["city"], record, "city"),
        price_from_kzt=_number(row["price_from_kzt"], record, "price_from_kzt"),
        event_formats=_items(row["event_formats"], record, "event_formats"),
        languages=_items(row["languages"], record, "languages"),
        max_hours=None if hours.lower() in ("", "null") else _number(hours, record, "max_hours"),
        busy_dates=_dates(row["busy_dates"], record),
        description=row["description"],
        synthetic=_boolean(row["synthetic"], record, "synthetic"),
        city_imputed=_boolean(row["city_imputed"], record, "city_imputed"),
        price_imputed=_boolean(row["price_imputed"], record, "price_imputed"),
    )


def load_contractors(path: str | PathLike[str]) -> list[Contractor]:
    """Read and validate the supplied CSV; no I/O happens at module import.

    Lists use ``|``; booleans accept case-insensitive true/false. Empty or
    literal null max_hours becomes None. Prices must be present, finite and
    nonnegative; non-null hours must be positive. Descriptions are preserved
    verbatim, including whitespace and embedded newlines.

    ValueError identifies the 1-based data-record number and field; record 0
    means the header. Multiline quoted cells count as one record. Structural
    errors use <row> or <csv>. File access/encoding errors propagate normally.
    Dates are validated as calendar dates, without filtering calendar windows.
    The first invalid record aborts loading; partial catalogues are not returned.
    """
    contractors: list[Contractor] = []
    seen: dict[str, int] = {}
    record = 0
    with open(path, encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter=",", strict=True)
        try:
            header = next(reader, None)
            if not header:
                raise _error(0, "<csv>", "missing header")
            for field in header:
                if header.count(field) > 1:
                    raise _error(0, field, "duplicate column")
                if field not in Contractor.__annotations__:
                    raise _error(0, field, "unexpected column")
            for field in Contractor.__annotations__:
                if field not in header:
                    raise _error(0, field, "missing column")
            record = 1
            while True:
                cells = next(reader, None)
                if cells is None:
                    break
                if not cells or len(cells) > len(header):
                    raise _error(record, "<row>", "wrong number of cells")
                if len(cells) < len(header):
                    raise _error(record, header[len(cells)], "missing cell")
                contractor = _normalize(dict(zip(header, cells)), record)
                identifier = contractor["id"]
                if identifier in seen:
                    raise _error(record, "id", f"duplicate {identifier!r}; first seen in record {seen[identifier]}")
                seen[identifier] = record
                contractors.append(contractor)
                record += 1
        except csv.Error as exc:
            raise _error(record, "<csv>", str(exc)) from exc
    return contractors
