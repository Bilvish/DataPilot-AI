
import pandas as pd


def validate_dataset(df: pd.DataFrame) -> list[dict]:
    """Check basic data quality without modifying the dataset."""

    results = []

    def add_check(check, status, details):
        results.append({
            "Check": check,
            "Status": status,
            "Details": details,
        })

    # Check 1: Dataset dimensions
    add_check(
        "Dataset dimensions",
        "PASS" if not df.empty and len(df.columns) > 0 else "FAIL",
        f"{len(df)} rows and {len(df.columns)} columns",
    )

    # Check 2: Duplicate column names
    duplicate_columns = df.columns[df.columns.duplicated()].tolist()

    add_check(
        "Duplicate column names",
        "FAIL" if duplicate_columns else "PASS",
        str(duplicate_columns) if duplicate_columns else "All column names are unique",
    )

    # Check 3: Fully empty rows
    empty_rows = int(df.isna().all(axis=1).sum())

    add_check(
        "Fully empty rows",
        "WARN" if empty_rows else "PASS",
        f"{empty_rows} fully empty rows",
    )

    # Check 4: Fully empty columns
    empty_columns = df.columns[df.isna().all()].tolist()

    add_check(
        "Fully empty columns",
        "WARN" if empty_columns else "PASS",
        str(empty_columns) if empty_columns else "No fully empty columns",
    )

    # Check 5: Duplicate rows
    duplicate_rows = int(df.duplicated().sum())

    add_check(
        "Duplicate rows",
        "WARN" if duplicate_rows else "PASS",
        f"{duplicate_rows} duplicate rows",
    )

    # Check 6: Missing values
    missing_values = int(df.isna().sum().sum())

    add_check(
        "Missing values",
        "WARN" if missing_values else "PASS",
        f"{missing_values} missing cells",
    )

    # Check 7: Negative numeric values
    numeric_columns = df.select_dtypes(include="number").columns

    negative_columns = {
        str(column): int((df[column] < 0).sum())
        for column in numeric_columns
        if (df[column] < 0).any()
    }

    add_check(
        "Negative numeric values",
        "WARN" if negative_columns else "PASS",
        str(negative_columns) if negative_columns else "No negative numeric values",
    )

    return results
