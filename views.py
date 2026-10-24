"""
views.py
========
Page renderers for the DataPilot AI shell. Each ``page_*`` function renders one
navigation page. Data logic is delegated to the existing modules (loader, profiler,
cleaner, validator, ETL, SQL, visualization); this file only arranges and presents it.
"""

from __future__ import annotations

import html
import re
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

import ui_theme as ui
from data_cleaner import clean_dataset
from data_profiler import profile_dataset
from data_validator import validate_dataset
from etl_pipeline import load_to_duckdb
from sql_analytics import SQLValidationError, execute_sql_query
from sql_samples import build_sample_queries, is_valid_table_name
from universal_loader import SUPPORTED_FORMATS, load_uploaded_file
from visualization import format_number, render_data_quality, render_visualization

FORMAT_LABEL = ", ".join(sorted(e.lstrip(".").upper() for e in SUPPORTED_FORMATS))
MAX_UPLOAD_MB = 200  # keep in sync with .streamlit/config.toml [server] maxUploadSize

_FRIENDLY_LOAD_ERRORS = (
    (("openpyxl", "excel"), "The Excel file could not be read. Check that it is a valid .xlsx workbook."),
    (("parquet", "arrow"), "The Parquet file could not be read. It may be corrupt or use an unsupported schema."),
    (("json", "expecting", "decode"), "The JSON file could not be converted to a table. Use a list of records or an object that contains one."),
    (("tokenizing", "parsererror", "codec", "utf"), "The CSV file could not be parsed. Check the delimiter and that the file is UTF-8 text."),
    (("no columns", "empty"), "The file is empty."),
)


# --------------------------------------------------------------------------- #
# State helpers
# --------------------------------------------------------------------------- #
DATASET_STATE = ("dataset", "cleaned_df", "cleaned_for", "audit_log", "source_filename", "duckdb_load_result",
                 "sql_query_result", "sql_query_error", "sql_meta", "sql_editor_sig")


def reset_dataset_state() -> None:
    for k in DATASET_STATE:
        st.session_state.pop(k, None)


def friendly_load_error(exc: Exception) -> str:
    text = str(exc).lower()
    for needles, message in _FRIENDLY_LOAD_ERRORS:
        if any(n in text for n in needles):
            return message
    return "The file could not be read. Please check that it is a valid, non-empty file in a supported format."


def ingest_upload(uploaded_file) -> None:
    """Load the uploaded file once per distinct upload and store it in session state."""
    if uploaded_file is None:
        if st.session_state.get("source_file_key") is not None:
            reset_dataset_state()
            st.session_state.pop("upload_error", None)
            st.session_state.pop("source_file_key", None)
        return

    # file_id is unique per upload, so re-uploading a different file with the same
    # name and size is still treated as a new dataset.
    file_key = f"{getattr(uploaded_file, 'file_id', '')}:{uploaded_file.name}:{uploaded_file.size}"
    if st.session_state.get("source_file_key") == file_key:
        return  # already processed (loaded or failed) - do not re-read on every rerun

    reset_dataset_state()
    st.session_state["source_file_key"] = file_key
    st.session_state.pop("upload_error", None)
    try:
        with st.spinner(f"Reading {uploaded_file.name}…"):
            df = load_uploaded_file(uploaded_file)
        if df is None or df.empty or len(df.columns) == 0:
            raise ValueError("The uploaded file contains no usable data.")
    except ValueError as exc:
        msg = str(exc)
        st.session_state["upload_error"] = (
            msg if msg.startswith(("Unsupported file format", "The uploaded file", "The JSON structure"))
            else friendly_load_error(exc))
        return
    except Exception as exc:  # noqa: BLE001 - surface a safe message, never a traceback
        st.session_state["upload_error"] = friendly_load_error(exc)
        return

    st.session_state["dataset"] = {
        "name": uploaded_file.name,
        "size": uploaded_file.size,
        "df": df,
        "key": file_key,
        "uploaded_at": time.strftime("%H:%M"),
    }


def current_dataset() -> Optional[dict]:
    return st.session_state.get("dataset")


def cleaned_for_current() -> Optional[pd.DataFrame]:
    ds = current_dataset()
    cleaned = st.session_state.get("cleaned_df")
    if ds is not None and cleaned is not None and st.session_state.get("cleaned_for") == ds["key"]:
        return cleaned
    return None


def dataset_status() -> tuple[str, str]:
    ds = current_dataset()
    if ds is None:
        return ("No dataset", "neutral")
    if st.session_state.get("duckdb_load_result") and cleaned_for_current() is not None:
        return ("Loaded in DuckDB", "success")
    if cleaned_for_current() is not None:
        return ("Cleaned", "success")
    return ("Uploaded · not cleaned", "warning")


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.0f} {unit}" if unit == "B" else f"{size:,.1f} {unit}"
        size /= 1024
    return f"{n} B"


def file_stem(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(name).stem).strip("._") or "dataset"


def header(title: str, subtitle: str) -> None:
    ds = current_dataset()
    ui.page_header(title, subtitle, dataset_name=ds["name"] if ds else None, status=dataset_status())


def need_dataset(action: str) -> bool:
    """Show the empty state and return True when no dataset is loaded."""
    if current_dataset() is None:
        ui.empty_state("No dataset loaded", f"Upload a file from the sidebar to {action}.")
        return True
    return False


# --------------------------------------------------------------------------- #
# Business KPI detection (explicit column-name matches only)
# --------------------------------------------------------------------------- #
_BUSINESS_FIELDS = {
    "sales": ("sales", "revenue", "total_sales", "total_revenue"),
    "profit": ("profit",),
    "quantity": ("quantity", "qty", "units"),
    "discount": ("discount",),
    "orders": ("orderid", "order_id", "orders"),
}


def _norm(name) -> str:
    return re.sub(r"[\s\-]+", "_", str(name).strip().lower())


def detect_business_fields(df: pd.DataFrame) -> dict[str, str]:
    """Map business roles to columns by exact (normalised) name. Numeric roles need numeric columns."""
    found: dict[str, str] = {}
    for col in df.columns:
        n = _norm(col)
        for role, names in _BUSINESS_FIELDS.items():
            if role in found or n not in names:
                continue
            if role == "orders" or pd.api.types.is_numeric_dtype(df[col]):
                found[role] = col
    return found


def business_kpis(df: pd.DataFrame) -> list[tuple[str, str, str]]:
    f = detect_business_fields(df)
    out: list[tuple[str, str, str]] = []
    if "sales" in f:
        out.append(("Total " + str(f["sales"]), format_number(df[f["sales"]].sum()), f"Sum of '{f['sales']}' · column name match"))
    if "profit" in f:
        out.append(("Total " + str(f["profit"]), format_number(df[f["profit"]].sum()), f"Sum of '{f['profit']}' · column name match"))
    if "sales" in f and "profit" in f:
        s, p = df[f["sales"]].sum(), df[f["profit"]].sum()
        if s:
            out.append(("Profit / sales", f"{100 * p / s:.1f}%", f"Derived: sum of '{f['profit']}' ÷ sum of '{f['sales']}'"))
    if "quantity" in f:
        out.append(("Total " + str(f["quantity"]), format_number(df[f["quantity"]].sum()), f"Sum of '{f['quantity']}'"))
    if "orders" in f:
        out.append(("Distinct " + str(f["orders"]), f"{df[f['orders']].nunique(dropna=True):,}", f"Unique values in '{f['orders']}'"))
    if "discount" in f:
        out.append(("Average " + str(f["discount"]), format_number(df[f["discount"]].mean()), f"Mean of '{f['discount']}' (not rescaled)"))
    return out[:6]


# --------------------------------------------------------------------------- #
# Shared blocks
# --------------------------------------------------------------------------- #
def render_validation(cleaned: pd.DataFrame) -> None:
    try:
        results = pd.DataFrame(validate_dataset(cleaned))
    except Exception as exc:  # noqa: BLE001
        st.error(f"Validation could not run: {type(exc).__name__}. The cleaned data was not validated.")
        return
    if results.empty:
        st.info("The validator returned no checks.")
        return
    status_col = next((c for c in results.columns if str(c).lower() in ("status", "result", "passed", "outcome")), None)
    if status_col is not None:
        vals = results[status_col].astype(str).str.lower()
        bad = vals.isin(["fail", "failed", "false", "error"]).sum()
        warn = vals.isin(["warn", "warning"]).sum()
        if bad:
            st.error(f"{bad} validation check(s) failed.")
        elif warn:
            st.warning(f"{warn} validation check(s) raised warnings.")
        else:
            st.success("All validation checks passed.")
    ui.table(results)


def render_original_profile(df: pd.DataFrame) -> dict:
    profile = profile_dataset(df)
    ui.metric_row([
        ("Rows", f"{profile['total_rows']:,}", "Original file"),
        ("Columns", f"{profile['total_columns']:,}", None),
        ("Missing values", f"{profile['total_missing_values']:,}", "Empty cells"),
        ("Duplicate rows", f"{profile['duplicate_rows']:,}", "Fully identical rows"),
    ])
    return profile


# --------------------------------------------------------------------------- #
# Page: Overview
# --------------------------------------------------------------------------- #
def page_overview() -> None:
    ds = current_dataset()
    header("Overview", "Your dataset at a glance and the next step in the workflow.")

    err = st.session_state.get("upload_error")
    if err:
        st.error(err)

    if ds is None:
        ui.empty_state(
            "Welcome to DataPilot AI",
            f"Upload a dataset from the sidebar to begin. Supported formats: {FORMAT_LABEL}. "
            f"Maximum file size: {MAX_UPLOAD_MB} MB.",
        )
        ui.section("How it works")
        ui.steps([
            ("Upload", "Drag a file into the sidebar uploader.", False),
            ("Prepare", "Profile, clean and validate the data.", False),
            ("Analyse", "Explore interactive charts and quality checks.", False),
            ("Query", "Load into DuckDB and run read-only SQL.", False),
        ])
        return

    df = ds["df"]
    cleaned = cleaned_for_current()
    loaded = bool(st.session_state.get("duckdb_load_result")) and cleaned is not None

    ui.section("Dataset", "Metadata of the uploaded file.")
    ui.metric_row([
        ("File", ds["name"], f"{human_size(ds['size'])} · uploaded {ds['uploaded_at']}"),
        ("Rows", f"{len(df):,}", "Original data"),
        ("Columns", f"{len(df.columns):,}", f"{len(df.select_dtypes(include='number').columns)} numeric"),
    ])

    profile = profile_dataset(df)
    total_cells = max(profile["total_rows"] * profile["total_columns"], 1)
    missing = profile["total_missing_values"]
    ui.section("Data health", "Calculated on the original upload.")
    ui.metric_row([
        ("Missing values", f"{missing:,}", f"{100 * missing / total_cells:.1f}% of cells"),
        ("Completeness", f"{100 * (1 - missing / total_cells):.1f}%", "Share of non-empty cells"),
        ("Duplicate rows", f"{profile['duplicate_rows']:,}",
         f"{100 * profile['duplicate_rows'] / max(profile['total_rows'], 1):.1f}% of rows"),
        ("Numeric columns", f"{len(df.select_dtypes(include='number').columns):,}", None),
    ])

    kpis = business_kpis(df)
    if kpis:
        ui.section("Business metrics", "Shown only for columns whose names clearly match (e.g. Sales, Profit). Calculated on the original data.")
        ui.metric_row(kpis[:4])
        if len(kpis) > 4:
            ui.metric_row(kpis[4:])

    ui.section("Workflow")
    ui.steps([
        ("Upload", f"{ds['name']} loaded.", True),
        ("Prepare", "Cleaned and validated." if cleaned is not None else "Open Data Preparation to clean the data.", cleaned is not None),
        ("Analyse", "Open Visual Analytics for charts.", False),
        ("Query", "Loaded into DuckDB." if loaded else "Open SQL Workspace to load and query.", loaded),
    ])

    ui.section("Preview", "First 10 rows of the original data.")
    ui.table(df.head(10))


# --------------------------------------------------------------------------- #
# Page: Data Preparation
# --------------------------------------------------------------------------- #
MISSING_LABELS = {
    "keep": "Keep missing values",
    "drop_rows": "Remove rows containing missing values",
    "fill": "Fill numeric values with median and text with mode",
}


def page_preparation() -> None:
    header("Data Preparation", "Profile the original data, apply cleaning rules, and validate the result.")
    if need_dataset("prepare it"):
        return
    ds = current_dataset()
    df = ds["df"]

    ui.section("1 · Original data", "The uploaded file is never modified. Cleaning creates a separate copy.")
    profile = render_original_profile(df)
    with st.expander("Original data preview (first 10 rows)", expanded=True):
        ui.table(df.head(10))
    with st.expander("Column details"):
        ui.table(pd.DataFrame(profile["column_details"]))

    ui.section("2 · Cleaning options")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        trim_text = c1.checkbox("Trim whitespace from text columns", value=True, key="prep_trim")
        remove_duplicates = c2.checkbox("Remove duplicate rows", value=True, key="prep_dedupe")
        missing_strategy = st.selectbox(
            "How should missing values be handled?", options=list(MISSING_LABELS),
            format_func=MISSING_LABELS.get, key="prep_missing",
        )
        # Say what will happen before it happens.
        impacts = []
        if remove_duplicates and profile["duplicate_rows"]:
            impacts.append(f"{profile['duplicate_rows']:,} duplicate row(s) will be removed")
        if missing_strategy == "drop_rows":
            n_rows = int(df.isna().any(axis=1).sum())
            impacts.append(f"up to {n_rows:,} row(s) containing missing values will be removed")
        if missing_strategy == "fill":
            impacts.append("missing values will be replaced with medians (numeric) or modes (text)")
        if impacts:
            st.warning("Cleaned data will differ from the original: " + "; ".join(impacts) + ". The original upload is kept.")
        run = st.button("Clean dataset", type="primary", key="prep_run")

    if run:
        try:
            with st.spinner("Cleaning…"):
                cleaned_df, audit_log = clean_dataset(
                    df, trim_text=trim_text, remove_duplicates=remove_duplicates,
                    missing_strategy=missing_strategy,
                )
            st.session_state["cleaned_df"] = cleaned_df
            st.session_state["audit_log"] = audit_log
            st.session_state["cleaned_for"] = ds["key"]
            st.session_state["source_filename"] = ds["name"]
            for k in ("duckdb_load_result", "sql_query_result", "sql_query_error", "sql_meta", "sql_editor_sig"):
                st.session_state.pop(k, None)
            st.success("Dataset cleaned successfully.")
        except Exception as exc:  # noqa: BLE001
            st.session_state.pop("cleaned_df", None)
            st.error(f"Cleaning failed ({type(exc).__name__}): {exc}")

    cleaned = cleaned_for_current()
    if cleaned is None:
        st.info("Choose options above and click Clean dataset to see the cleaned data, validation results and downloads.")
        return

    ui.section("3 · Cleaning summary")
    before, after = len(df), len(cleaned)
    ui.metric_row([
        ("Rows before", f"{before:,}", None),
        ("Rows after", f"{after:,}", None),
        ("Rows removed", f"{max(before - after, 0):,}", f"{100 * max(before - after, 0) / max(before, 1):.1f}% of original"),
        ("Missing values after", f"{int(cleaned.isna().sum().sum()):,}", f"was {profile['total_missing_values']:,}"),
    ])
    with st.expander("Cleaned data preview (first 10 rows)", expanded=True):
        ui.table(cleaned.head(10))

    ui.section("4 · Validation")
    render_validation(cleaned)

    ui.section("5 · Audit log", "Every change made by the cleaning step.")
    audit_df = pd.DataFrame(st.session_state.get("audit_log") or [])
    if audit_df.empty:
        st.info("The cleaning step reported no changes.")
    else:
        ui.table(audit_df)

    ui.section("6 · Downloads")
    stem = file_stem(ds["name"])
    d1, d2 = st.columns(2)
    d1.download_button("Download cleaned CSV", cleaned.to_csv(index=False).encode("utf-8"),
                       file_name=f"{stem}_cleaned.csv", mime="text/csv", key="download_cleaned_csv", width="stretch")
    d2.download_button("Download cleaning audit log", audit_df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{stem}_cleaning_audit_log.csv", mime="text/csv", key="download_audit_csv", width="stretch")


# --------------------------------------------------------------------------- #
# Page: Visual Analytics
# --------------------------------------------------------------------------- #
def page_analytics() -> None:
    header("Visual Analytics", "Interactive charts built from your data. Every figure is calculated from the selected dataset.")
    if need_dataset("explore it"):
        return
    ds = current_dataset()
    cleaned = cleaned_for_current()
    source = "Cleaned data"
    if cleaned is None:
        st.info("The data has not been cleaned yet, so charts use the original upload. Clean it in Data Preparation for analysis on prepared data.")
        source = "Original data"
        frame = ds["df"]
    else:
        choice = st.radio("Dataset to analyse", ["Cleaned data", "Original data"], horizontal=True, key="viz_source")
        source = choice
        frame = cleaned if choice == "Cleaned data" else ds["df"]
    st.caption(f"Analysing: **{source}** · {len(frame):,} rows × {len(frame.columns):,} columns")
    render_visualization(frame)


# --------------------------------------------------------------------------- #
# Page: SQL Workspace
# --------------------------------------------------------------------------- #
def page_sql() -> None:
    header("SQL Workspace", "Load the cleaned dataset into DuckDB and run read-only queries.")
    if need_dataset("use SQL"):
        return
    ds = current_dataset()
    cleaned = cleaned_for_current()
    if cleaned is None:
        ui.empty_state("Clean the data first", "SQL runs on the cleaned dataset. Open Data Preparation and click Clean dataset.")
        return

    ui.section("1 · Load into DuckDB", "Saves the cleaned dataset in a local DuckDB file. Loading a table that already exists replaces its contents.")
    with st.container(border=True):
        c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
        table_name = c1.text_input("Database table name", value="cleaned_data", key="duckdb_table_name",
                                   help="Letters, numbers and underscores. Start with a letter or underscore.")
        load = c2.button("Load into DuckDB", type="primary", key="load_duckdb_button", width="stretch")
        name = table_name.strip()
        if load:
            if not is_valid_table_name(name):
                st.error("Table name must start with a letter or underscore and contain only letters, numbers and underscores.")
            else:
                try:
                    with st.spinner("Loading into DuckDB…"):
                        result = load_to_duckdb(cleaned, table_name=name)
                    st.session_state["duckdb_load_result"] = result
                    for k in ("sql_query_result", "sql_query_error", "sql_meta"):
                        st.session_state.pop(k, None)
                    st.success("Cleaned dataset loaded into DuckDB.")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"DuckDB load failed ({type(exc).__name__}): {exc}")

    load_result = st.session_state.get("duckdb_load_result")
    if load_result:
        ui.metric_row([
            ("Rows loaded", f"{load_result['rows_loaded']:,}", None),
            ("Columns loaded", f"{load_result['columns_loaded']:,}", None),
            ("Table", str(load_result["table_name"]), Path(str(load_result["database_path"])).name),
        ])
        if "schema" in load_result:
            with st.expander("View loaded table schema"):
                ui.table(load_result["schema"])

    ui.section("2 · Query", "Read-only: SELECT, WITH, DESCRIBE, SHOW, SUMMARIZE and EXPLAIN are accepted. Everything else is rejected.")
    active_table = load_result.get("table_name", name or "cleaned_data") if load_result else (name or "cleaned_data")
    samples = build_sample_queries(active_table, cleaned)

    # Reset the editor whenever the table or its columns change.
    sig = (active_table, tuple(map(str, cleaned.columns)))
    if st.session_state.get("sql_editor_sig") != sig:
        st.session_state["sql_editor_sig"] = sig
        st.session_state["sql_sample_query"] = next(iter(samples))
        st.session_state["sql_query_editor"] = samples[st.session_state["sql_sample_query"]]

    def _on_sample_change() -> None:
        st.session_state["sql_query_editor"] = samples[st.session_state["sql_sample_query"]]

    st.selectbox("Sample queries", list(samples), key="sql_sample_query", on_change=_on_sample_change)
    sql_query = st.text_area("SQL query", height=190, key="sql_query_editor",
                             help="Edit freely. Press Ctrl+Enter in the editor to apply, then click Run query.")

    if not load_result:
        st.info("Load the dataset into DuckDB above before running queries.")

    b1, b2, _ = st.columns([1, 1, 4])
    run = b1.button("Run query", type="primary", disabled=not load_result, key="run_sql_query_button", width="stretch")
    if b2.button("Reset", key="reset_sql_query_button", width="stretch"):
        st.session_state["sql_query_editor"] = samples[st.session_state["sql_sample_query"]]
        st.session_state.pop("sql_query_result", None)
        st.session_state.pop("sql_query_error", None)
        st.rerun()

    if run:
        start = time.perf_counter()
        try:
            with st.spinner("Running query…"):
                result = execute_sql_query(sql_query)
            st.session_state["sql_query_result"] = result
            st.session_state["sql_meta"] = {"seconds": time.perf_counter() - start}
            st.session_state["sql_query_error"] = None
        except SQLValidationError as exc:
            st.session_state["sql_query_error"] = ("Query rejected", str(exc))
            st.session_state.pop("sql_query_result", None)
        except Exception as exc:  # noqa: BLE001
            first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            st.session_state["sql_query_error"] = ("Query failed", first)
            st.session_state.pop("sql_query_result", None)

    err = st.session_state.get("sql_query_error")
    if err:
        st.error(f"**{err[0]}.** {err[1]}")

    result = st.session_state.get("sql_query_result")
    if result is not None:
        ui.section("Results")
        meta = st.session_state.get("sql_meta", {})
        ui.metric_row([
            ("Result rows", f"{len(result):,}", "Capped at 100,000" if result.attrs.get("truncated") else None),
            ("Columns", f"{len(result.columns):,}", None),
            ("Run time", f"{meta.get('seconds', 0):.2f} s", None),
        ])
        if result.attrs.get("truncated"):
            st.warning("The result was truncated at 100,000 rows. Add a LIMIT or filter to see specific rows.")
        if result.empty:
            st.info("The query ran successfully and returned no rows.")
        else:
            ui.table(result, height=360)
        st.download_button("Download results as CSV", result.to_csv(index=False).encode("utf-8"),
                           file_name="sql_query_results.csv", mime="text/csv", key="download_sql_results")


# --------------------------------------------------------------------------- #
# Page: Data Quality
# --------------------------------------------------------------------------- #
def page_quality() -> None:
    header("Data Quality", "Missing values, duplicates, column types and validation results.")
    if need_dataset("assess it"):
        return
    ds = current_dataset()
    cleaned = cleaned_for_current()
    options = ["Original data"] + (["Cleaned data"] if cleaned is not None else [])
    which = st.radio("Dataset to assess", options, horizontal=True, key="quality_source",
                     index=len(options) - 1)
    frame = cleaned if which == "Cleaned data" else ds["df"]
    render_data_quality(frame)

    ui.section("Validation results", "Checks run by the validator on the cleaned dataset.")
    if cleaned is None:
        st.info("Clean the data in Data Preparation to run validation.")
    else:
        render_validation(cleaned)
