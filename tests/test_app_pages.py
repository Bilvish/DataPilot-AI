"""Render every page through Streamlit's AppTest with real session state.

AppTest cannot upload files or switch st.navigation pages, so each page function is run
in its own script with a dataset injected into session state (the same dict the uploader
produces). Upload parsing itself is covered by test_loader_and_data.py.
"""
import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


def make_df(seed=0, n=200):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "OrderID": range(1, n + 1), "Product": rng.choice(["A", "B", "C"], n),
        "Country": rng.choice(["US", "UK"], n), "Sales": rng.normal(100, 20, n).round(2),
        "Profit": rng.normal(10, 5, n).round(2), "Quantity": rng.integers(1, 5, n),
        "OrderDate": pd.date_range("2025-01-01", periods=n).astype(str)})
    df.loc[3, "Sales"] = np.nan
    return pd.concat([df, df.iloc[:5]], ignore_index=True)  # 5 duplicate rows


def run_page(page, df, state=None, cwd=None):
    def script(page_name):
        import views
        getattr(views, page_name)()

    at = AppTest.from_function(script, args=(page,), default_timeout=90)
    at.session_state["dataset"] = {"name": "shop.csv", "size": 999, "df": df, "key": "k", "uploaded_at": "10:00"}
    for k, v in (state or {}).items():
        at.session_state[k] = v
    return at.run()


@pytest.fixture(autouse=True)
def _cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # isolates datapilot.duckdb


def no_errors(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_overview_empty_state():
    def script():
        import views
        views.page_overview()
    at = AppTest.from_function(script).run()
    assert not at.exception
    assert any("Welcome to DataPilot AI" in m.value for m in at.markdown)


def test_overview_with_data_shows_business_kpis():
    at = run_page("page_overview", make_df())
    no_errors(at)
    labels = [m.label for m in at.metric]
    assert "Total Sales" in labels and "Total Profit" in labels and "Profit / sales" in labels


def test_preparation_clean_flow_and_downloads():
    at = run_page("page_preparation", make_df())
    no_errors(at)
    at.button(key="prep_run").click().run()
    no_errors(at)
    assert at.session_state["cleaned_df"] is not None
    assert len(at.session_state["cleaned_df"]) == 200  # 5 duplicates removed
    rows_removed = [m for m in at.metric if m.label == "Rows removed"][0]
    assert rows_removed.value == "5"


def test_preparation_drop_rows_warns_before_running():
    at = run_page("page_preparation", make_df())
    at.selectbox(key="prep_missing").select("drop_rows").run()
    assert any("will be removed" in w.value for w in at.warning)


def test_analytics_runs_on_cleaned_and_original():
    df = make_df()
    at = run_page("page_analytics", df)
    no_errors(at)  # original data with info banner
    cleaned = df.drop_duplicates().reset_index(drop=True)
    at = run_page("page_analytics", df, {"cleaned_df": cleaned, "cleaned_for": "k"})
    no_errors(at)


def test_sql_page_requires_clean_then_runs_queries():
    df = make_df()
    at = run_page("page_sql", df)
    assert not at.exception
    cleaned = df.drop_duplicates().reset_index(drop=True)
    at = run_page("page_sql", df, {"cleaned_df": cleaned, "cleaned_for": "k"})
    no_errors(at)
    at.button(key="load_duckdb_button").click().run()
    no_errors(at)
    assert at.session_state["duckdb_load_result"]["rows_loaded"] == 200
    at.text_area(key="sql_query_editor").set_value("SELECT COUNT(*) AS n FROM cleaned_data").run()
    at.button(key="run_sql_query_button").click().run()
    no_errors(at)
    assert at.session_state["sql_query_result"]["n"][0] == 200
    at.text_area(key="sql_query_editor").set_value("DROP TABLE cleaned_data").run()
    at.button(key="run_sql_query_button").click().run()
    assert any("Query rejected" in e.value for e in at.error)
    assert at.session_state["sql_query_result"] is None if "sql_query_result" in at.session_state else True
    at.text_area(key="sql_query_editor").set_value("SELECT COUNT(*) AS n FROM cleaned_data").run()
    at.button(key="run_sql_query_button").click().run()
    assert at.session_state["sql_query_result"]["n"][0] == 200  # table survived


def test_sql_rejects_bad_table_name():
    df = make_df()
    cleaned = df.drop_duplicates().reset_index(drop=True)
    at = run_page("page_sql", df, {"cleaned_df": cleaned, "cleaned_for": "k"})
    at.text_input(key="duckdb_table_name").set_value("bad name; DROP").run()
    at.button(key="load_duckdb_button").click().run()
    assert any("Table name must start" in e.value for e in at.error)


def test_quality_page():
    at = run_page("page_quality", make_df())
    no_errors(at)


def test_switching_same_schema_different_contents():
    """Two datasets with identical schema and row count must not share stale widget state."""
    a, b = make_df(0), make_df(1)
    b["OrderDate"] = pd.date_range("2030-06-01", periods=len(b)).astype(str)  # disjoint date range
    at = run_page("page_analytics", a)
    no_errors(at)
    at.selectbox(key=[s.key for s in at.selectbox if s.label == "Date filter column"][0]).select_index(1).run()
    no_errors(at)
    at.session_state["dataset"] = {"name": "other.csv", "size": 1, "df": b, "key": "k2", "uploaded_at": "11:00"}
    at.run()
    no_errors(at)
