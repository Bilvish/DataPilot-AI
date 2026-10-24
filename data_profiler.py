
import pandas as pd


def profile_dataset(df: pd.DataFrame) -> dict:
    """Generate a basic data-quality profile for a DataFrame."""

    total_rows, total_columns = df.shape

    missing_values = df.isna().sum()
    duplicate_rows = int(df.duplicated().sum())

    column_details = []

    for column in df.columns:
        series = df[column]

        column_details.append({
            "Column": str(column),
            "Data Type": str(series.dtype),
            "Non-Null Values": int(series.notna().sum()),
            "Missing Values": int(series.isna().sum()),
            "Missing (%)": round(
                series.isna().mean() * 100, 2
            ),
            "Unique Values": int(series.nunique()),
        })

    profile = {
        "total_rows": total_rows,
        "total_columns": total_columns,
        "duplicate_rows": duplicate_rows,
        "total_missing_values": int(missing_values.sum()),
        "columns_with_missing_values": int(
            (missing_values > 0).sum()
        ),
        "column_details": column_details,
    }

    return profile
