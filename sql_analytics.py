"""
sql_analytics.py
================
Read-only SQL execution against the local InsightFlow DuckDB database.

Security model (defence in depth)
---------------------------------
1. **Parser-based validation.** The query is parsed by DuckDB itself
   (``extract_statements``). Exactly one statement is accepted, and its type must be
   SELECT (this covers WITH, FROM-first, VALUES, DESCRIBE, SHOW and SUMMARIZE, which
   DuckDB parses as SELECT) or EXPLAIN. INSERT, UPDATE, DELETE, CREATE, DROP, ALTER,
   COPY, ATTACH, EXPORT, PRAGMA, SET, CALL, LOAD/INSTALL and the rest are rejected
   by type, not by keyword matching, so comments, casing and string literals cannot
   fool it.
2. **Read-only connection.** The database file is opened with ``read_only=True``.
3. **No file or network access.** ``enable_external_access`` is switched off, so
   table functions such as ``read_csv('/etc/passwd')`` or ``read_parquet('http://...')``
   fail, and extensions cannot be loaded.
4. **Locked configuration.** ``lock_configuration`` is switched on so a query cannot
   re-enable anything.
5. **Resource limits.** Results are capped at ``MAX_RESULT_ROWS`` rows and each query
   is interrupted after ``QUERY_TIMEOUT_SECONDS``.

Limits: this protects the local database file and filesystem. It is not a
multi-tenant sandbox, and it does not hide any table that exists in the database.
"""

from __future__ import annotations

import threading
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa

DATABASE_PATH = Path("insightflow.duckdb")
MAX_RESULT_ROWS = 100_000
QUERY_TIMEOUT_SECONDS = 30

_ALLOWED_STATEMENT_TYPES = {"SELECT", "EXPLAIN"}


class SQLValidationError(ValueError):
    """Raised when a query is rejected before it is executed."""


def validate_sql(sql: str) -> str:
    """Return the query to run, or raise SQLValidationError.

    Uses DuckDB's own parser. No connection to any database file is needed.
    """
    if sql is None or not str(sql).strip():
        raise SQLValidationError("Please enter a SQL query.")

    query = str(sql).strip()
    # Remove trailing semicolons only (a single terminator is harmless).
    while query.endswith(";"):
        query = query[:-1].rstrip()
    if not query:
        raise SQLValidationError("Please enter a SQL query.")

    probe = duckdb.connect(":memory:")
    try:
        try:
            statements = probe.extract_statements(query)
        except duckdb.Error as exc:
            raise SQLValidationError(f"SQL syntax error: {_first_line(exc)}") from None
    finally:
        probe.close()

    if len(statements) == 0:
        raise SQLValidationError("Please enter a SQL query.")
    if len(statements) > 1:
        raise SQLValidationError("Please execute one SQL statement at a time.")

    kind = statements[0].type.name
    if kind not in _ALLOWED_STATEMENT_TYPES:
        raise SQLValidationError(
            f"{kind} statements are not allowed. This workspace is read-only: "
            "use SELECT, WITH, DESCRIBE, SHOW, SUMMARIZE or EXPLAIN."
        )
    return query


def _first_line(exc: Exception) -> str:
    return str(exc).strip().splitlines()[0] if str(exc).strip() else "invalid query"


def execute_sql_query(
    sql: str,
    database_path: str | Path = DATABASE_PATH,
    max_rows: int = MAX_RESULT_ROWS,
    timeout_seconds: float = QUERY_TIMEOUT_SECONDS,
) -> pd.DataFrame:
    """Execute one read-only analytical SQL query and return a DataFrame.

    ``df.attrs["truncated"]`` is True when the result was cut at ``max_rows``.
    """
    query = validate_sql(sql)

    db_path = Path(database_path)
    if not db_path.exists():
        raise FileNotFoundError(
            f"Database file '{db_path.name}' was not found. "
            "Load cleaned data into DuckDB first."
        )

    connection = duckdb.connect(str(db_path), read_only=True)
    timer = None
    try:
        connection.execute("SET enable_external_access = false")
        connection.execute("SET lock_configuration = true")

        timer = threading.Timer(timeout_seconds, connection.interrupt)
        timer.daemon = True
        timer.start()

        try:
            reader = connection.sql(query).to_arrow_reader(10_000)
            batches, total, truncated = [], 0, False
            for batch in reader:
                batches.append(batch)
                total += batch.num_rows
                if total > max_rows:
                    truncated = True
                    break
            table = (
                pa.Table.from_batches(batches, schema=reader.schema)
                if batches
                else reader.schema.empty_table()
            )
        except duckdb.InterruptException:
            raise TimeoutError(
                f"The query was stopped after {timeout_seconds:g} seconds."
            ) from None

        result = table.to_pandas()
        if truncated:
            result = result.iloc[:max_rows].copy()
        result.attrs["truncated"] = truncated
        return result
    finally:
        if timer is not None:
            timer.cancel()
        connection.close()
