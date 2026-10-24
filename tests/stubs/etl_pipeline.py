"""TEST STAND-IN for the project's real etl_pipeline.py (not shipped to the user)."""
import re
from pathlib import Path

import duckdb
import pandas as pd

DB = Path("datapilot.duckdb")


def load_to_duckdb(df, table_name="cleaned_data"):
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", table_name or ""):
        raise ValueError("Invalid table name")
    con = duckdb.connect(str(DB))
    try:
        con.register("incoming", df)
        con.execute(f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM incoming')
        schema = con.execute(f'DESCRIBE "{table_name}"').fetchdf()
    finally:
        con.close()
    return {"table_name": table_name, "rows_loaded": len(df), "columns_loaded": len(df.columns),
            "database_path": str(DB.resolve()), "schema": schema}
