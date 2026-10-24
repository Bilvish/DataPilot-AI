"""
universal_app.py
================
InsightFlow AI - application shell (sidebar, navigation, upload, page routing).

Run with:  streamlit run universal_app.py
"""

import html
from pathlib import Path

import streamlit as st

import ui_theme as ui
import views

ASSETS = Path(__file__).parent / "assets"

st.set_page_config(
    page_title="InsightFlow AI",
    page_icon=str(ASSETS / "icon.svg"),
    layout="wide",
    initial_sidebar_state="expanded",
)

ui.inject_css()
st.logo(str(ASSETS / "logo.svg"), icon_image=str(ASSETS / "icon.svg"), size="large")

pages = [
    st.Page(views.page_overview, title="Overview", icon=":material/dashboard:", url_path="overview", default=True),
    st.Page(views.page_preparation, title="Data Preparation", icon=":material/cleaning_services:", url_path="data-preparation"),
    st.Page(views.page_analytics, title="Visual Analytics", icon=":material/bar_chart:", url_path="visual-analytics"),
    st.Page(views.page_sql, title="SQL Workspace", icon=":material/terminal:", url_path="sql-workspace"),
    st.Page(views.page_quality, title="Data Quality", icon=":material/verified:", url_path="data-quality"),
]
navigation = st.navigation(pages, position="sidebar")

with st.sidebar:
    st.markdown("**Dataset**")
    uploaded_file = st.file_uploader(
        "Upload a dataset",
        type=[e.lstrip(".") for e in sorted(views.SUPPORTED_FORMATS)],
        key="dataset_uploader",
        help=f"{views.FORMAT_LABEL} · up to {views.MAX_UPLOAD_MB} MB",
        label_visibility="collapsed",
    )
    st.caption(f"{views.FORMAT_LABEL} · up to {views.MAX_UPLOAD_MB} MB")
    views.ingest_upload(uploaded_file)

    ds = views.current_dataset()
    if ds is not None:
        label, kind = views.dataset_status()
        st.markdown(
            f'<div class="if-side-card"><b title="{html.escape(ds["name"])}">{html.escape(ds["name"])}</b>'
            f'<span>{len(ds["df"]):,} rows · {len(ds["df"].columns):,} columns · {views.human_size(ds["size"])}</span><br>'
            f"{ui.status_chip(label, kind)}</div>",
            unsafe_allow_html=True,
        )
    st.markdown('<div class="if-footer">InsightFlow AI · local workspace<br>Streamlit · pandas · DuckDB · Plotly</div>',
                unsafe_allow_html=True)

navigation.run()
