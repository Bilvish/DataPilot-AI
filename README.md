# InsightFlow AI

A local data-preparation and analytics workspace built with Streamlit, pandas, DuckDB and Plotly.
Upload a dataset, profile and clean it, explore it with interactive charts, load it into DuckDB and query it with read-only SQL.

## Features

- **Overview** – dataset metadata, data-health KPIs, business KPIs (only when column names clearly match Sales, Profit, Quantity, Discount or OrderID), workflow progress.
- **Data Preparation** – original profile, cleaning options with an impact warning, before/after summary, validation, audit log, CSV downloads. The upload is never modified; cleaning produces a separate copy.
- **Visual Analytics** – executive overview, trends, category/segment comparison, relationships and correlation, distributions, data quality. Column roles are detected automatically; sums and shares are only shown where they are valid.
- **SQL Workspace** – load the cleaned data into DuckDB, run read-only queries from a monospace editor with sample queries, download results as CSV.
- **Data Quality** – missing values, duplicates, column types, distinct counts, warnings and validation results.

"Completeness" (Overview) = 100 × (1 − missing cells ÷ total cells). No composite "quality score" is shown.

## Supported inputs

CSV, XLSX, JSON, Parquet. Upload limit: 200 MB (`.streamlit/config.toml`). Very large files are limited by available memory because they are loaded into pandas.

## Run (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run universal_app.py
```

## Tests

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

`tests/stubs/` contains stand-ins for `data_profiler`, `data_cleaner`, `data_validator` and `etl_pipeline`, used **only if those modules are not found in the project root**. When your real modules are present they are used instead.

## Architecture

| File | Role |
|---|---|
| `universal_app.py` | App shell: logo, navigation, sidebar uploader, page routing |
| `views.py` | One function per page; presentation only |
| `ui_theme.py` | Stylesheet and reusable UI helpers |
| `visualization.py` | Analytics dashboard (Plotly) |
| `sql_analytics.py` | Validated, read-only SQL execution |
| `sql_samples.py` | Sample queries |
| `universal_loader.py`, `data_profiler.py`, `data_cleaner.py`, `data_validator.py`, `etl_pipeline.py` | Existing data logic (unchanged by the redesign) |
| `.streamlit/config.toml` | Theme and upload limit |

Flow: upload → `load_uploaded_file` → profile → clean → validate → (charts) → `load_to_duckdb` → `execute_sql_query`.

## SQL security notes

- The query is parsed by DuckDB; exactly one statement is accepted and it must be a SELECT-type (SELECT, WITH, DESCRIBE, SHOW, SUMMARIZE) or EXPLAIN statement. INSERT/UPDATE/DELETE/CREATE/DROP/ALTER/COPY/ATTACH/EXPORT/PRAGMA/SET/CALL/INSTALL/LOAD are rejected by statement type.
- The database is opened read-only, external file and network access is disabled (`read_csv('/etc/passwd')` fails), and the configuration is locked.
- Results are capped at 100,000 rows and queries stop after 30 seconds.
- Covered by `tests/test_sql_analytics.py`. This protects the local database file and filesystem; it is not a multi-user sandbox, and every table in `insightflow.duckdb` is queryable.

## Known limitations

- No screenshots are included; none were captured.
- Datasets are held in memory; the SQL editor is a plain text area (no syntax highlighting or autocomplete).
- Single-user, local app: no accounts or authentication.

## Future improvements

Syntax-highlighted SQL editor, saved queries, chart export as images, background loading for very large files.
