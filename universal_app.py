

import streamlit as st
import pandas as pd

from universal_loader import load_uploaded_file
from data_profiler import profile_dataset
from data_cleaner import clean_dataset
from data_validator import validate_dataset


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="InsightFlow AI",
    page_icon="🔎",
    layout="wide",
)

st.title("InsightFlow AI")
st.caption(
    "Upload, profile, clean, validate, and export your data."
)

# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

with st.sidebar:
    st.header("InsightFlow AI")
    st.caption("Data preparation workspace")

    st.markdown("### Workflow")
    st.markdown(
        """
        1. Upload data
        2. Profile data quality
        3. Clean the dataset
        4. Validate the results
        5. Download cleaned data
        """
    )

    st.divider()
    st.caption("Supported: CSV, XLSX, JSON, Parquet")


# --------------------------------------------------
# FILE UPLOAD
# --------------------------------------------------

uploaded_file = st.file_uploader(
    "Upload your dataset",
    type=["csv", "xlsx", "json", "parquet"],
    help="Upload a tabular file to begin analysis.",
)

if uploaded_file is None:
    st.info("Upload a dataset to begin.")
    st.stop()


# Reset stored results when the uploaded file changes.
file_key = (
    uploaded_file.name,
    uploaded_file.size,
)

if st.session_state.get("current_file_key") != file_key:
    st.session_state["current_file_key"] = file_key
    st.session_state.pop("cleaned_df", None)
    st.session_state.pop("cleaning_audit", None)
    st.session_state.pop("cleaning_source", None)


# --------------------------------------------------
# LOAD DATA
# --------------------------------------------------

try:
    df = load_uploaded_file(uploaded_file)

    if not isinstance(df, pd.DataFrame):
        st.error("The uploaded file did not produce a table.")
        st.stop()

    if len(df.columns) == 0:
        st.error("The uploaded dataset has no columns.")
        st.stop()

except Exception as error:
    st.error(f"Unable to load the uploaded file: {error}")
    st.stop()


st.success(f"Loaded: {uploaded_file.name}")

# --------------------------------------------------
# OVERVIEW METRICS
# --------------------------------------------------

profile = profile_dataset(df)

metric1, metric2, metric3, metric4 = st.columns(4)

metric1.metric("Total Rows", f"{len(df):,}")
metric2.metric("Total Columns", f"{len(df.columns):,}")
metric3.metric(
    "Missing Values",
    f"{profile['total_missing_values']:,}",
)
metric4.metric(
    "Duplicate Rows",
    f"{profile['duplicate_rows']:,}",
)

st.divider()


# --------------------------------------------------
# DATA PREVIEW
# --------------------------------------------------

st.subheader("Dataset Preview")

preview_rows = st.slider(
    "Rows to preview",
    min_value=5,
    max_value=100,
    value=10,
    step=5,
)

st.dataframe(
    df.head(preview_rows),
    use_container_width=True,
    hide_index=True,
)

with st.expander("View complete dataset"):
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )


# --------------------------------------------------
# DATA QUALITY PROFILE
# --------------------------------------------------

st.divider()
st.subheader("Data Quality Profile")

profile_tab, stats_tab, schema_tab = st.tabs(
    ["Column Quality", "Statistics", "Schema"]
)

with profile_tab:
    column_details = pd.DataFrame(
        profile["column_details"]
    )

    st.dataframe(
        column_details,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "Missing percentage is calculated separately for each column."
    )

with stats_tab:
    st.write("Numeric column statistics")

    numeric_df = df.select_dtypes(include="number")

    if numeric_df.empty:
        st.info("No numeric columns found.")
    else:
        st.dataframe(
            numeric_df.describe().T,
            use_container_width=True,
        )

    st.write("Text and category summaries")

    text_columns = df.select_dtypes(
        include=["object", "string", "category"]
    ).columns

    if len(text_columns) == 0:
        st.info("No text or category columns found.")
    else:
        text_summary = pd.DataFrame([
            {
                "Column": str(column),
                "Unique Values": int(df[column].nunique()),
                "Most Frequent Value": (
                    str(df[column].mode(dropna=True).iloc[0])
                    if not df[column].mode(dropna=True).empty
                    else "No non-missing values"
                ),
            }
            for column in text_columns
        ])

        st.dataframe(
            text_summary,
            use_container_width=True,
            hide_index=True,
        )

with schema_tab:
    schema_df = pd.DataFrame({
        "Column": [str(column) for column in df.columns],
        "Data Type": [str(dtype) for dtype in df.dtypes],
        "Non-Null Values": [
            int(df[column].notna().sum())
            for column in df.columns
        ],
        "Missing Values": [
            int(df[column].isna().sum())
            for column in df.columns
        ],
    })

    st.dataframe(
        schema_df,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download Schema CSV",
        data=schema_df.to_csv(index=False).encode("utf-8"),
        file_name="insightflow_schema.csv",
        mime="text/csv",
    )


# --------------------------------------------------
# DATA CLEANING
# --------------------------------------------------

st.divider()
st.subheader("Data Cleaning & Validation")

st.write(
    "Choose operations below. The original loaded DataFrame "
    "is preserved; cleaning works on a separate copy."
)

with st.form("cleaning_form"):
    trim_text = st.checkbox(
        "Trim leading and trailing whitespace",
        value=True,
    )

    remove_duplicates = st.checkbox(
        "Remove duplicate rows",
        value=False,
    )

    missing_option = st.selectbox(
        "Missing-value handling",
        options=[
            "Keep missing values",
            "Fill numeric values with median and text with mode",
            "Drop rows containing missing values",
        ],
    )

    run_cleaning = st.form_submit_button(
        "Run cleaning",
        type="primary",
    )


strategy_map = {
    "Keep missing values": "keep",
    "Fill numeric values with median and text with mode": "fill",
    "Drop rows containing missing values": "drop_rows",
}

if run_cleaning:
    try:
        cleaned_df, audit_log = clean_dataset(
            df,
            trim_text=trim_text,
            remove_duplicates=remove_duplicates,
            missing_strategy=strategy_map[missing_option],
        )

        st.session_state["cleaned_df"] = cleaned_df
        st.session_state["cleaning_audit"] = audit_log
        st.session_state["cleaning_source"] = file_key

        st.success("Cleaning completed.")

    except Exception as error:
        st.error(f"Cleaning failed: {error}")


# --------------------------------------------------
# CLEANED RESULTS
# --------------------------------------------------

has_cleaned_data = (
    "cleaned_df" in st.session_state
    and st.session_state.get("cleaning_source") == file_key
)

if has_cleaned_data:
    cleaned_df = st.session_state["cleaned_df"]
    audit_log = st.session_state["cleaning_audit"]

    st.divider()
    st.subheader("Cleaning Results")

    before_col, after_col, removed_col = st.columns(3)

    before_col.metric("Rows Before", f"{len(df):,}")
    after_col.metric("Rows After", f"{len(cleaned_df):,}")
    removed_col.metric(
        "Rows Removed",
        f"{len(df) - len(cleaned_df):,}",
    )

    # Audit log
    st.subheader("Cleaning Audit Log")

    audit_df = pd.DataFrame(audit_log)

    st.dataframe(
        audit_df,
        use_container_width=True,
        hide_index=True,
    )

    # Cleaned data preview
    st.subheader("Cleaned Dataset Preview")

    st.dataframe(
        cleaned_df.head(100),
        use_container_width=True,
        hide_index=True,
    )

    # Validation report
    st.subheader("Validation Report")

    try:
        validation_results = validate_dataset(cleaned_df)
        validation_df = pd.DataFrame(validation_results)

        st.dataframe(
            validation_df,
            use_container_width=True,
            hide_index=True,
        )

        failed_checks = (
            int((validation_df["Status"] == "FAIL").sum())
            if "Status" in validation_df.columns
            else 0
        )

        warning_checks = (
            int((validation_df["Status"] == "WARN").sum())
            if "Status" in validation_df.columns
            else 0
        )

        result1, result2 = st.columns(2)
        result1.metric("Failed Checks", failed_checks)
        result2.metric("Warnings", warning_checks)

    except Exception as error:
        st.error(f"Validation failed: {error}")

    # Downloads
    st.subheader("Download Results")

    download1, download2 = st.columns(2)

    with download1:
        st.download_button(
            "Download Cleaned CSV",
            data=cleaned_df.to_csv(index=False).encode("utf-8"),
            file_name="insightflow_cleaned.csv",
            mime="text/csv",
        )

    with download2:
        st.download_button(
            "Download Cleaning Audit CSV",
            data=audit_df.to_csv(index=False).encode("utf-8"),
            file_name="insightflow_cleaning_audit.csv",
            mime="text/csv",
        )

    st.caption(
        "Validation warnings identify issues for review. "
        "They do not automatically mean the dataset is unusable."
    )


# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.divider()
st.caption(
    "InsightFlow AI | Data ingestion, profiling, cleaning, and validation"
)
