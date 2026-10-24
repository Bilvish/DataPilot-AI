"""TEST STAND-IN for the project's real data_profiler.py (not shipped to the user)."""
import pandas as pd


def profile_dataset(df):
    details = [{"column": str(c), "dtype": str(df[c].dtype), "missing": int(df[c].isna().sum()),
                "unique": int(df[c].astype(str).nunique())} for c in df.columns]
    return {"total_rows": len(df), "total_columns": len(df.columns),
            "total_missing_values": int(df.isna().sum().sum()),
            "duplicate_rows": int(df.astype(str).duplicated().sum()), "column_details": details}
