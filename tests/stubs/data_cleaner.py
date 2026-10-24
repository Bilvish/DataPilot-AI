"""TEST STAND-IN for the project's real data_cleaner.py (not shipped to the user)."""
import pandas as pd


def clean_dataset(df, trim_text=True, remove_duplicates=True, missing_strategy="keep"):
    out, log = df.copy(), []
    if trim_text:
        for c in out.select_dtypes(include=["object", "string"]).columns:
            out[c] = out[c].str.strip()
        log.append({"step": "trim_text", "detail": "trimmed"})
    if remove_duplicates:
        n = len(out); out = out.drop_duplicates()
        log.append({"step": "remove_duplicates", "detail": f"removed {n - len(out)}"})
    if missing_strategy == "drop_rows":
        n = len(out); out = out.dropna()
        log.append({"step": "drop_rows", "detail": f"removed {n - len(out)}"})
    elif missing_strategy == "fill":
        for c in out.columns:
            if pd.api.types.is_numeric_dtype(out[c]):
                out[c] = out[c].fillna(out[c].median())
            elif out[c].notna().any():
                out[c] = out[c].fillna(out[c].mode().iloc[0])
        log.append({"step": "fill", "detail": "filled"})
    return out.reset_index(drop=True), log
