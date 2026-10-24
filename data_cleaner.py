
import pandas as pd


def clean_dataset(
    df: pd.DataFrame,
    trim_text: bool = True,
    remove_duplicates: bool = False,
    missing_strategy: str = "keep",
):
    """Clean a DataFrame and return it with an audit log."""

    cleaned_df = df.copy(deep=True)
    audit_log = []

    # 1. Trim whitespace from text columns
    if trim_text:
        text_columns = cleaned_df.select_dtypes(
            include=["object", "string"]
        ).columns

        total_trimmed = 0

        for column in text_columns:
            original = cleaned_df[column]

            trimmed = original.map(
                lambda value: value.strip()
                if isinstance(value, str)
                else value
            )

            changed = (
                original.notna()
                & trimmed.ne(original).fillna(False)
            )

            total_trimmed += int(changed.sum())
            cleaned_df[column] = trimmed

        audit_log.append({
            "Operation": "Trim text whitespace",
            "Affected Records/Values": total_trimmed,
            "Status": "Completed",
        })

    # 2. Remove duplicate rows when selected
    if remove_duplicates:
        duplicates_before = int(cleaned_df.duplicated().sum())
        cleaned_df = cleaned_df.drop_duplicates().copy()

        audit_log.append({
            "Operation": "Remove duplicate rows",
            "Affected Records/Values": duplicates_before,
            "Status": "Completed",
        })

    # 3. Handle missing values
    missing_before = int(cleaned_df.isna().sum().sum())

    if missing_strategy == "drop_rows":
        rows_before = len(cleaned_df)
        cleaned_df = cleaned_df.dropna().copy()

        audit_log.append({
            "Operation": "Drop rows containing missing values",
            "Affected Records/Values": rows_before - len(cleaned_df),
            "Status": "Completed",
        })

    elif missing_strategy == "fill":
        filled_values = 0

        for column in cleaned_df.columns:
            series = cleaned_df[column]
            missing_count = int(series.isna().sum())

            if missing_count == 0:
                continue

            if pd.api.types.is_numeric_dtype(series):
                if series.notna().any():
                    cleaned_df[column] = series.fillna(series.median())
                    filled_values += missing_count

            elif (
                pd.api.types.is_object_dtype(series)
                or isinstance(series.dtype, pd.StringDtype)
                or isinstance(series.dtype, pd.CategoricalDtype)
            ):
                mode_values = series.mode(dropna=True)

                if not mode_values.empty:
                    cleaned_df[column] = series.fillna(mode_values.iloc[0])
                    filled_values += missing_count

        audit_log.append({
            "Operation": "Fill missing values",
            "Affected Records/Values": filled_values,
            "Status": "Completed",
        })

    elif missing_strategy != "keep":
        raise ValueError(
            "Choose 'keep', 'fill', or 'drop_rows' for missing_strategy."
        )

    missing_after = int(cleaned_df.isna().sum().sum())

    audit_log.append({
        "Operation": "Missing-value summary",
        "Affected Records/Values": missing_before - missing_after,
        "Status": f"{missing_after} missing values remain",
    })

    return cleaned_df, audit_log
