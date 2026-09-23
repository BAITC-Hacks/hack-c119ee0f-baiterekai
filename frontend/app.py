"""Streamlit entry point for the contractor recommendation demo."""

from datetime import date

import streamlit as st

from api_client import (
    APIResponseError,
    BackendTimeoutError,
    BackendUnavailableError,
    build_recommendation_payload,
    recommend,
)
from components import render_request_summary, render_response


CALENDAR_START = date(2026, 9, 23)
CALENDAR_END = date(2026, 12, 31)


st.set_page_config(page_title="BaiterekAI", page_icon="🤝", layout="centered")

st.title("BaiterekAI")
st.caption("Подбор подрядчиков для вашего мероприятия")

with st.form("recommendation_form"):
    city = st.text_input("Город", placeholder="Например, Алматы")
    event_date = st.date_input(
        "Дата мероприятия",
        value=min(max(date.today(), CALENDAR_START), CALENDAR_END),
        min_value=CALENDAR_START,
        max_value=CALENDAR_END,
    )
    event_type = st.text_input("Тип мероприятия", placeholder="Например, свадьба")
    contractor_category = st.text_input("Категория подрядчика", placeholder="Например, Фотограф")
    budget = st.number_input("Бюджет", min_value=0, value=None, step=1000, placeholder="0")
    language = st.text_input("Язык (необязательно)")
    duration = st.number_input("Длительность в часах (необязательно)", min_value=0, value=None, step=1, placeholder="0")
    submitted = st.form_submit_button("Найти подрядчиков", type="primary")

if submitted:
    missing = []
    if not city.strip():
        missing.append("город")
    if not event_type.strip():
        missing.append("тип мероприятия")
    if not contractor_category.strip():
        missing.append("категория подрядчика")
    if budget <= 0:
        missing.append("бюджет")

    if missing:
        st.warning("Заполните обязательные поля: " + ", ".join(missing) + ".")
    else:
        payload = build_recommendation_payload(
            city=city,
            event_date=event_date.isoformat(),
            event_type=event_type,
            contractor_category=contractor_category,
            budget=budget,
            language=language,
            duration=duration,
        )
        render_request_summary(payload)
        with st.spinner("Ищем подходящих подрядчиков..."):
            try:
                backend_response = recommend(payload)
            except BackendTimeoutError:
                st.error("Backend не ответил вовремя. Попробуйте ещё раз.")
            except BackendUnavailableError:
                st.error("Backend недоступен. Проверьте, что сервис запущен.")
            except APIResponseError as exc:
                st.error(str(exc))
            else:
                render_response(backend_response.data)
