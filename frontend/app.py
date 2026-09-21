import os
from urllib.parse import urlencode

import pandas as pd
import requests
import streamlit as st

# Deliberately calls the FastAPI backend, not Supabase directly -- keeps this
# a pure frontend swappable for React later with zero backend changes.
API_BASE_URL = os.environ.get("API_BASE_URL", "https://project-inception.onrender.com")
KNOWN_SOURCES = ["cisa_kev", "urlhaus", "threatfox", "otx"]
INDICATOR_TYPES = ["ip", "domain", "url", "hash", "cve"]

st.set_page_config(page_title="Project Inception — Threat Intel Dashboard", layout="wide")
st.title("Project Inception — Threat Intel Dashboard")


def api_get(path: str, params: dict | None = None, timeout: int = 60):
    resp = requests.get(f"{API_BASE_URL}{path}", params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


with st.spinner("Connecting to API (a cold free-tier instance can take up to a minute to wake up)..."):
    try:
        api_get("/health", timeout=90)
        api_up = True
    except Exception as exc:
        api_up = False
        st.error(f"API is unreachable: {exc}")

if api_up:
    # --- Ingestion health widget (FR12) ---
    st.subheader("Ingestion Health")
    try:
        health = api_get("/api/sources")
        health_df = pd.DataFrame(health)
        st.dataframe(health_df, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error(f"Could not load source health: {exc}")

    # --- Filters (FR10) ---
    st.sidebar.header("Filters")
    indicator_type = st.sidebar.selectbox("Type", [""] + INDICATOR_TYPES)
    source = st.sidebar.selectbox("Source", [""] + KNOWN_SOURCES)
    q = st.sidebar.text_input("Search value")
    date_from = st.sidebar.date_input("From", value=None)
    date_to = st.sidebar.date_input("To", value=None)
    limit = st.sidebar.slider("Rows per page", 10, 200, 50)
    offset = st.sidebar.number_input("Offset", min_value=0, value=0, step=limit)

    filter_params: dict = {}
    if indicator_type:
        filter_params["type"] = indicator_type
    if source:
        filter_params["source"] = source
    if q:
        filter_params["q"] = q
    if date_from:
        filter_params["date_from"] = date_from.isoformat()
    if date_to:
        filter_params["date_to"] = date_to.isoformat()

    # --- Indicator table (FR10) ---
    st.subheader("Indicators")
    df = pd.DataFrame()
    try:
        data = api_get("/api/indicators", params={**filter_params, "limit": limit, "offset": offset})
        st.caption(f"{data['total']} total matching indicators")
        df = pd.DataFrame(data["items"])
        if not df.empty:
            df["sources"] = df["sources"].apply(lambda s: ", ".join(s))
            event = st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
            )
        else:
            st.info("No indicators match these filters.")
            event = None
    except Exception as exc:
        st.error(f"Could not load indicators: {exc}")
        event = None

    # --- Detail view (FR13) ---
    if event is not None and event.selection and event.selection.rows:
        selected_id = df.iloc[event.selection.rows[0]]["id"]
        st.subheader("Indicator Detail")
        try:
            detail = api_get(f"/api/indicators/{selected_id}")
            st.json(detail)
        except Exception as exc:
            st.error(f"Could not load detail: {exc}")

    # --- Export (FR14) ---
    st.subheader("Export current filtered set")
    export_col1, export_col2 = st.columns(2)
    with export_col1:
        csv_url = f"{API_BASE_URL}/api/indicators/export?" + urlencode({**filter_params, "format": "csv"})
        st.link_button("Download CSV", csv_url)
    with export_col2:
        json_url = f"{API_BASE_URL}/api/indicators/export?" + urlencode({**filter_params, "format": "json"})
        st.link_button("Download JSON", json_url)

    # --- Volume chart (FR11) ---
    st.subheader("Ingestion Volume")
    chart_source = st.selectbox("Source", KNOWN_SOURCES, key="volume_source")
    try:
        volume = api_get(f"/api/sources/{chart_source}/volume", params={"days": 30})
        volume_df = pd.DataFrame(volume)
        if not volume_df.empty:
            volume_df = volume_df.set_index("date")
            st.bar_chart(volume_df["record_count"])
        else:
            st.info(f"No ingestion runs recorded yet for '{chart_source}' in the last 30 days.")
    except Exception as exc:
        st.error(f"Could not load volume data: {exc}")
