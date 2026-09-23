"""Small HTTP client for the recommendation backend."""

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib import error, request


API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT_SECONDS = 15


class BackendUnavailableError(Exception):
    """The backend could not be reached."""


class BackendTimeoutError(Exception):
    """The backend did not answer before the timeout."""


class APIResponseError(Exception):
    """The backend returned an unusable response."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class RecommendationResponse:
    status: str
    data: Dict[str, Any]


def build_recommendation_payload(
    city: str,
    event_date: str,
    event_type: str,
    contractor_category: str,
    budget: int,
    language: Optional[str] = None,
    duration: Optional[int] = None,
) -> Dict[str, Any]:
    """Build the backend request without adding recommendation logic."""
    payload: Dict[str, Any] = {
        "city": city.strip(),
        "date": event_date,
        "event_type": event_type.strip(),
        "category": contractor_category.strip(),
        "budget": budget,
    }
    if language and language.strip():
        payload["language"] = language.strip()
    if duration is not None and duration > 0:
        payload["duration"] = duration
    return payload


def recommend(payload: Dict[str, Any]) -> RecommendationResponse:
    """POST a recommendation request and validate its top-level response shape."""
    body = json.dumps(payload).encode("utf-8")
    http_request = request.Request(
        f"{API_URL}/recommend",
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status_code = response.status
            raw_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        if exc.code in (400, 422):
            raise APIResponseError(_error_detail(raw_body, "Некорректный запрос."), exc.code) from None
        if exc.code >= 500:
            raise APIResponseError("Сервис рекомендаций временно недоступен.", exc.code) from None
        raise APIResponseError("Backend вернул ошибку.", exc.code) from None
    except error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise BackendTimeoutError("Backend не ответил вовремя.") from None
        raise BackendUnavailableError("Не удалось подключиться к backend.") from None
    except TimeoutError:
        raise BackendTimeoutError("Backend не ответил вовремя.") from None
    except OSError:
        raise BackendUnavailableError("Не удалось подключиться к backend.") from None

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        raise APIResponseError("Backend вернул некорректный JSON.", status_code) from None

    if not isinstance(parsed, dict) or not isinstance(parsed.get("status"), str):
        raise APIResponseError("Backend вернул неожиданный формат ответа.", status_code)
    if parsed["status"] not in {"found", "category_not_found", "no_match"}:
        raise APIResponseError("Backend вернул неизвестный статус.", status_code)
    if parsed["status"] == "found":
        recommendations = parsed.get("results")
        if not isinstance(recommendations, list):
            raise APIResponseError("Backend вернул неожиданный список рекомендаций.", status_code)
    return RecommendationResponse(status=parsed["status"], data=parsed)


def _error_detail(raw_body: str, fallback: str) -> str:
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        return fallback
    if isinstance(parsed, dict):
        detail = parsed.get("detail") or parsed.get("message") or parsed.get("error")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if isinstance(detail, list):
            messages = []
            for item in detail:
                if not isinstance(item, dict):
                    continue
                message = item.get("msg")
                if not isinstance(message, str) or not message.strip():
                    continue
                location = item.get("loc", [])
                field = ".".join(
                    str(part) for part in location if part != "body"
                ) if isinstance(location, (list, tuple)) else ""
                messages.append(f"{field}: {message}" if field else message)
            if messages:
                return "; ".join(messages)
    return fallback
