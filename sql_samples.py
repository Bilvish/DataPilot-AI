"""Sample read-only queries for the SQL workspace (same queries as before, now testable)."""

from __future__ import annotations

import re

import pandas as pd

_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_valid_table_name(name: str) -> bool:
    return bool(name) and bool(_TABLE_RE.match(name))


def quote_identifier(value) -> str:
    """Safely quote a DuckDB table or column identifier."""
    return '"' + str(value).replace('"', '""') + '"'


def build_sample_queries(table: str, df: pd.DataFrame) -> dict[str, str]:
    t = quote_identifier(table)
    names = list(df.columns)
    cols = [quote_identifier(c) for c in names]
    numeric = list(df.select_dtypes(include="number").columns)
    text = list(df.select_dtypes(include=["object", "string", "category"]).columns)

    q = {
        "1. Preview first 5 rows": f"SELECT * FROM {t} LIMIT 5",
        "2. Preview first 10 rows": f"SELECT * FROM {t} LIMIT 10",
        "3. Preview first 20 rows": f"SELECT * FROM {t} LIMIT 20",
        "4. Count total rows": f"SELECT COUNT(*) AS total_rows FROM {t}",
        "5. Inspect table schema": f"DESCRIBE {t}",
        "6. Show missing values by column": (
            "SELECT " + ", ".join(
                f"COUNT(*) FILTER (WHERE {c} IS NULL) AS {quote_identifier(str(n) + '_missing')}"
                for n, c in zip(names, cols)) + f" FROM {t}"),
        "7. Show summary statistics": f"SUMMARIZE {t}",
        "8. Count unique values per column": (
            "SELECT " + ", ".join(
                f"COUNT(DISTINCT {c}) AS {quote_identifier(str(n) + '_unique')}"
                for n, c in zip(names, cols)) + f" FROM {t}"),
        "9. Find duplicate rows": (
            "SELECT " + ", ".join(cols) + f", COUNT(*) AS occurrences FROM {t} GROUP BY "
            + ", ".join(cols) + " HAVING COUNT(*) > 1"),
    }
    if numeric:
        q["10. Sort by first numeric column (highest first)"] = (
            f"SELECT * FROM {t} ORDER BY {quote_identifier(numeric[0])} DESC LIMIT 10")
    else:
        q["10. Preview 10 rows (fallback)"] = f"SELECT * FROM {t} LIMIT 10"
    if text:
        c = quote_identifier(text[0])
        q["11. Count values in first text column"] = (
            f"SELECT {c}, COUNT(*) AS row_count FROM {t} GROUP BY {c} ORDER BY row_count DESC LIMIT 20")
    return q
