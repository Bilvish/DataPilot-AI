

import streamlit as st
import pandas as pd
from sql_analytics import execute_sql_query

from visualization import render_visualization
from universal_loader import load_uploaded_file
from data_profiler import profile_dataset
from data_cleaner import clean_dataset
from data_validator import validate_dataset
from etl_pipeline import load_to_duckdb


st.set_page_config(
    page_title="InsightFlow AI",
    page_icon="📊",
    layout="wide",
)

st.title("InsightFlow AI")
st.caption("Data Preparation Workspace")

# STEP 1: Upload data
st.header("1. Upload Data")

uploaded_file = st.file_uploader(
    "Upload your dataset",
    type=["csv", "xlsx", "json", "parquet"],
)

if uploaded_file is not None:
    try:
        df = load_uploaded_file(uploaded_file)

        if df.empty or len(df.columns) == 0:
            st.error("The uploaded file contains no usable data.")
            st.stop()

        # Clear old results if the user selects a different file.
        current_file_key = f"{uploaded_file.name}:{uploaded_file.size}"
        previous_file_key = st.session_state.get("source_file_key")

        if previous_file_key != current_file_key:
            for key in (
                "cleaned_df",
                "audit_log",
                "source_filename",
                "source_file_key",
                "duckdb_load_result",
            ):
                st.session_state.pop(key, None)

            st.session_state["source_file_key"] = current_file_key

        st.success("File uploaded successfully!")

        # STEP 2: Preview data
        st.header("2. Data Preview")

        col1, col2 = st.columns(2)
        col1.metric("Rows", f"{len(df):,}")
        col2.metric("Columns", f"{len(df.columns):,}")

        st.dataframe(
            df.head(10),
            use_container_width=True,
        )

        # STEP 3: Profile data quality
        st.header("3. Data Quality Profile")

        profile = profile_dataset(df)

        a, b, c, d = st.columns(4)
        a.metric("Total Rows", f"{profile['total_rows']:,}")
        b.metric("Total Columns", f"{profile['total_columns']:,}")
        c.metric("Missing Values", f"{profile['total_missing_values']:,}")
        d.metric("Duplicate Rows", f"{profile['duplicate_rows']:,}")

        st.subheader("Column Details")
        st.dataframe(
            pd.DataFrame(profile["column_details"]),
            use_container_width=True,
        )

        # STEP 4: Clean data
        st.header("4. Clean Dataset")

        trim_text = st.checkbox(
            "Trim whitespace from text columns",
            value=True,
        )

        remove_duplicates = st.checkbox(
            "Remove duplicate rows",
            value=True,
        )

        missing_strategy = st.selectbox(
            "How should missing values be handled?",
            options=["keep", "drop_rows", "fill"],
            format_func=lambda value: {
                "keep": "Keep missing values",
                "drop_rows": "Remove rows containing missing values",
                "fill": (
                    "Fill numeric values with median "
                    "and text with mode"
                ),
            }[value],
        )

        if st.button("Clean Dataset", type="primary"):
            try:
                cleaned_df, audit_log = clean_dataset(
                    df,
                    trim_text=trim_text,
                    remove_duplicates=remove_duplicates,
                    missing_strategy=missing_strategy,
                )

                st.session_state["cleaned_df"] = cleaned_df
                st.session_state["audit_log"] = audit_log
                st.session_state["source_filename"] = uploaded_file.name

                # Clear previous database-load summary after cleaning.
                st.session_state.pop("duckdb_load_result", None)

                st.success("Dataset cleaned successfully!")

            except Exception as error:
                st.error(f"Cleaning failed: {error}")

        # STEP 5: Validate results
        cleaned_df = st.session_state.get("cleaned_df")
        audit_log = st.session_state.get("audit_log")
        source_filename = st.session_state.get("source_filename")

        if (
            cleaned_df is not None
            and source_filename == uploaded_file.name
        ):
            st.subheader("Cleaned Data Preview")

            st.dataframe(
                cleaned_df.head(10),
                use_container_width=True,
            )

            before_rows = len(df)
            after_rows = len(cleaned_df)

            m1, m2, m3 = st.columns(3)
            m1.metric("Rows Before Cleaning", f"{before_rows:,}")
            m2.metric("Rows After Cleaning", f"{after_rows:,}")
            m3.metric(
                "Rows Removed",
                f"{max(before_rows - after_rows, 0):,}",
            )

            st.header("5. Validate Results")

            validation_results = validate_dataset(cleaned_df)
            validation_df = pd.DataFrame(validation_results)

            st.dataframe(
                validation_df,
                use_container_width=True,
            )
      
            csv_data = cleaned_df.to_csv(
                index=False
            ).encode("utf-8")

            st.download_button(
                "Download Cleaned CSV",
                data=csv_data,
                file_name="cleaned_data.csv",
                mime="text/csv",
                key="download_cleaned_csv",
            )

            audit_df = pd.DataFrame(audit_log)

            audit_csv = audit_df.to_csv(
                index=False
            ).encode("utf-8")

            st.download_button(
                "Download Cleaning Audit Log",
                data=audit_csv,
                file_name="cleaning_audit_log.csv",
                mime="text/csv",
                key="download_audit_csv",
            )
                        # STEP 6: Professional Visualization Dashboard
            st.header("6. Data Visualization Dashboard")
            render_visualization(cleaned_df)

        

            # STEP 7: Load cleaned data into DuckDB
            st.header("7. Load to DuckDB")

            st.caption(
                "Save the cleaned dataset in a local DuckDB database "
                "for SQL analytics. Loading an existing table with "
                "the same name replaces its contents."
            )

            table_name = st.text_input(
                "Database table name",
                value="cleaned_data",
                help=(
                    "Use letters, numbers, and underscores. "
                    "Start with a letter or underscore."
                ),
                key="duckdb_table_name",
            )

            if st.button(
                "Load cleaned data into DuckDB",
                key="load_duckdb_button",
            ):
                try:
                    result = load_to_duckdb(
                        cleaned_df,
                        table_name=table_name.strip(),
                    )

                    st.session_state["duckdb_load_result"] = result

                    st.success(
                        "Cleaned dataset loaded into DuckDB successfully!"
                    )

                except Exception as error:
                    st.error(f"DuckDB load failed: {error}")

            # Show database load summary
            load_result = st.session_state.get("duckdb_load_result")

            if load_result:
                st.subheader("DuckDB Load Summary")

                db1, db2, db3 = st.columns(3)

                db1.metric(
                    "Rows Loaded",
                    f"{load_result['rows_loaded']:,}",
                )

                db2.metric(
                    "Columns Loaded",
                    f"{load_result['columns_loaded']:,}",
                )

                db3.metric(
                    "Database Table",
                    load_result["table_name"],
                )

                st.caption(
                    f"Database file: {load_result['database_path']}"
                )

                if "schema" in load_result:
                    with st.expander("View loaded table schema"):
                        st.dataframe(
                            load_result["schema"],
                            use_container_width=True,
                        )
                        
            # STEP 8: SQL Analytics Workspace
            st.divider()
            st.header("8. SQL Analytics Workspace")

            st.caption(
                "Run read-only SQL queries against the table loaded into DuckDB. "
                "Choose a sample query, edit it if needed, and run it."
            )

            active_load_result = st.session_state.get("duckdb_load_result")
            active_table = (
                active_load_result.get("table_name", "cleaned_data")
                if active_load_result
                else (table_name.strip() or "cleaned_data")
            )

            def quote_identifier(value):
                """Safely quote a DuckDB table or column identifier."""
                return '"' + str(value).replace('"', '""') + '"'

            quoted_table = quote_identifier(active_table)
            column_names = list(cleaned_df.columns)
            quoted_columns = [quote_identifier(column) for column in column_names]
            numeric_columns = list(
                cleaned_df.select_dtypes(include="number").columns
            )
            text_columns = list(
                cleaned_df.select_dtypes(include=["object", "string", "category"]).columns
            )

            sample_queries = {
                "1. Preview first 5 rows": (
                    f"SELECT * FROM {quoted_table} LIMIT 5"
                ),
                "2. Preview first 10 rows": (
                    f"SELECT * FROM {quoted_table} LIMIT 10"
                ),
                "3. Preview first 20 rows": (
                    f"SELECT * FROM {quoted_table} LIMIT 20"
                ),
                "4. Count total rows": (
                    f"SELECT COUNT(*) AS total_rows FROM {quoted_table}"
                ),
                "5. Inspect table schema": (
                    f"DESCRIBE {quoted_table}"
                ),
                "6. Show missing values by column": (
                    "SELECT "
                    + ", ".join(
                        f"COUNT(*) FILTER (WHERE {column_sql} IS NULL) "
                        f"AS {quote_identifier(str(column) + '_missing')}"
                        for column, column_sql in zip(column_names, quoted_columns)
                    )
                    + f" FROM {quoted_table}"
                ),
                "7. Show summary statistics": (
                    f"SUMMARIZE {quoted_table}"
                ),
                "8. Count unique values per column": (
                    "SELECT "
                    + ", ".join(
                        f"COUNT(DISTINCT {column_sql}) "
                        f"AS {quote_identifier(str(column) + '_unique')}"
                        for column, column_sql in zip(column_names, quoted_columns)
                    )
                    + f" FROM {quoted_table}"
                ),
                "9. Find duplicate rows": (
                    "SELECT "
                    + ", ".join(quoted_columns)
                    + f", COUNT(*) AS occurrences FROM {quoted_table} "
                    + "GROUP BY "
                    + ", ".join(quoted_columns)
                    + " HAVING COUNT(*) > 1"
                ),
            }

            if numeric_columns:
                first_numeric_sql = quote_identifier(numeric_columns[0])
                sample_queries["10. Sort by first numeric column (highest first)"] = (
                    f"SELECT * FROM {quoted_table} "
                    f"ORDER BY {first_numeric_sql} DESC LIMIT 10"
                )
            else:
                sample_queries["10. Preview 10 rows (fallback)"] = (
                    f"SELECT * FROM {quoted_table} LIMIT 10"
                )

            if text_columns:
                first_text_sql = quote_identifier(text_columns[0])
                sample_queries["11. Count values in first text column"] = (
                    f"SELECT {first_text_sql}, COUNT(*) AS row_count "
                    f"FROM {quoted_table} GROUP BY {first_text_sql} "
                    f"ORDER BY row_count DESC LIMIT 20"
                )

            # Synchronize the SQL editor whenever the dropdown selection changes.
            if "sql_sample_query" not in st.session_state:
                st.session_state["sql_sample_query"] = next(iter(sample_queries))
            elif st.session_state["sql_sample_query"] not in sample_queries:
                st.session_state["sql_sample_query"] = next(iter(sample_queries))

            if "sql_query_editor" not in st.session_state:
                st.session_state["sql_query_editor"] = sample_queries[
                    st.session_state["sql_sample_query"]
                ]

            def update_sql_editor_from_sample():
                st.session_state["sql_query_editor"] = sample_queries[
                    st.session_state["sql_sample_query"]
                ]

            st.selectbox(
                "Choose a sample query",
                options=list(sample_queries.keys()),
                key="sql_sample_query",
                on_change=update_sql_editor_from_sample,
            )

            sql_query = st.text_area(
                "SQL Query (you can edit this)",
                height=180,
                key="sql_query_editor",
            )

            if not active_load_result:
                st.info(
                    "Load the cleaned dataset into DuckDB above before running SQL queries."
                )

            if st.button(
                "Run SQL Query",
                type="primary",
                disabled=not bool(active_load_result),
                key="run_sql_query_button",
            ):
                try:
                    query_result = execute_sql_query(sql_query)
                    st.session_state["sql_query_result"] = query_result
                    st.session_state["sql_query_error"] = None
                except Exception as error:
                    st.session_state["sql_query_error"] = str(error)
                    st.session_state.pop("sql_query_result", None)

            query_error = st.session_state.get("sql_query_error")
            if query_error:
                st.error(f"Query failed: {query_error}")

            query_result = st.session_state.get("sql_query_result")
            if query_result is not None:
                st.subheader("Query Results")
                st.metric("Result Rows", f"{len(query_result):,}")
                st.dataframe(query_result, use_container_width=True)

                st.download_button(
                    "Download Query Results as CSV",
                    data=query_result.to_csv(index=False).encode("utf-8"),
                    file_name="sql_query_results.csv",
                    mime="text/csv",
                    key="download_sql_results",
                )


    except Exception as error:
        st.error(f"Something went wrong: {error}")
