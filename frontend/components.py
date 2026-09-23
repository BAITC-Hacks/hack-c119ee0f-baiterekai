"""Streamlit presentation helpers for the live demo."""

from typing import Any, Dict

import streamlit as st


def render_request_summary(payload: Dict[str, Any]) -> None:
    st.subheader("Параметры запроса")
    summary = [
        f"Город: {payload.get('city', '—')}",
        f"Дата: {payload.get('date', '—')}",
        f"Мероприятие: {payload.get('event_type', '—')}",
        f"Категория: {payload.get('category', '—')}",
        f"Бюджет: {payload.get('budget', '—')}",
    ]
    if payload.get("language"):
        summary.append(f"Язык: {payload['language']}")
    if payload.get("duration"):
        summary.append(f"Длительность: {payload['duration']} ч.")
    st.caption(" · ".join(summary))


def render_response(response: Dict[str, Any]) -> None:
    status = response.get("status")
    if status == "found":
        _render_found(response)
    elif status == "category_not_found":
        st.warning("В выбранном городе нет подрядчиков этой категории.")
    elif status == "no_match":
        st.info("Подходящих подрядчиков не найдено.")
        _render_rejection_details(response)
    else:
        st.error("Backend вернул неожиданный результат.")


def _render_found(response: Dict[str, Any]) -> None:
    contractors = response.get("results", [])
    if not isinstance(contractors, list):
        st.error("Backend вернул неожиданный список рекомендаций.")
        return

    count = response.get("count", response.get("total", len(contractors)))
    st.success(f"Найдено подрядчиков: {count}")
    for contractor in contractors[:3]:
        if not isinstance(contractor, dict):
            continue
        name = contractor.get("name", "Без названия")
        price = contractor.get("price")
        price_label = (
            f"от {price:,} ₸".replace(",", " ")
            if isinstance(price, (int, float))
            else None
        )
        with st.container(border=True):
            title_col, badge_col = st.columns([4, 1])
            title_col.subheader(name)
            if contractor.get("synthetic") is True:
                badge_col.markdown("`SYNTHETIC`")
            st.write(
                " · ".join(
                    str(value)
                    for value in (
                        contractor.get("category"),
                        contractor.get("city"),
                        price_label,
                    )
                    if value not in (None, "")
                )
            )
            if contractor.get("explanation"):
                st.caption(contractor["explanation"])


def _render_rejection_details(response: Dict[str, Any]) -> None:
    details = response.get("rejection_summary", response.get("rejection_stats"))
    if details:
        st.caption("Почему подходящие варианты не найдены")
        if isinstance(details, dict):
            st.json(details, expanded=False)
        else:
            st.write(details)
