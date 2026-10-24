
from pathlib import Path

import duckdb
import pandas as pd


DATABASE_PATH = Path("insightflow.duckdb")


def load_to_duckdb(
    df: pd.DataFrame,
    table_name: str = "cleaned_data",
    database_path: str | Path = DATABASE_PATH,
) -> dict:
    """
    Load a DataFrame into DuckDB.

    Creates or replaces the specified table and returns
    a summary of the load operation.
    """

    if not table_name.isidentifier():
        raise ValueError(
            "Invalid table name. Use letters, numbers, and underscores, "
            "starting with a letter or underscore."
        )

    if df.empty:
        raise ValueError("Cannot load an empty dataset.")

    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(str(database_path))

    try:
        connection.register("input_dataframe", df)

        connection.execute(
            f'CREATE OR REPLACE TABLE "{table_name}" AS '
            "SELECT * FROM input_dataframe"
        )

        row_count = connection.execute(
            f'SELECT COUNT(*) FROM "{table_name}"'
        ).fetchone()[0]

        column_info = connection.execute(
            f"DESCRIBE SELECT * FROM \"{table_name}\""
        ).fetchdf()

        return {
            "database_path": str(database_path.resolve()),
            "table_name": table_name,
            "rows_loaded": int(row_count),
            "columns_loaded": len(column_info),
            "schema": column_info,
        }

    finally:
        connection.close()


def query_duckdb(
    sql: str,
    database_path: str | Path = DATABASE_PATH,
) -> pd.DataFrame:
    """Execute a read-only analytical SQL query."""

    if not sql.strip().lower().startswith("select"):
        raise ValueError("Only SELECT queries are allowed.")

    connection = duckdb.connect(str(database_path), read_only=True)

    try:
        return connection.execute(sql).fetchdf()
    finally:
        connection.close()
