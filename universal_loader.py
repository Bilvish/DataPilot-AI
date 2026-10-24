
import json
from pathlib import Path

import pandas as pd


SUPPORTED_FORMATS = {".csv", ".xlsx", ".json", ".parquet"}


def load_uploaded_file(uploaded_file):
    """Load a supported tabular file into a Pandas DataFrame."""

    extension = Path(uploaded_file.name).suffix.lower()

    if extension not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported file format: {extension}")

    if extension == ".csv":
        return pd.read_csv(uploaded_file)

    if extension == ".xlsx":
        return pd.read_excel(uploaded_file, engine="openpyxl")

    if extension == ".parquet":
        return pd.read_parquet(uploaded_file, engine="pyarrow")

    if extension == ".json":
        try:
            return pd.read_json(uploaded_file)

        except (ValueError, TypeError):
            uploaded_file.seek(0)
            data = json.load(uploaded_file)

            if isinstance(data, list):
                return pd.json_normalize(data)

            if isinstance(data, dict):
                for value in data.values():
                    if (
                        isinstance(value, list)
                        and all(isinstance(row, dict) for row in value)
                    ):
                        return pd.json_normalize(value)

                return pd.json_normalize(data)

            raise ValueError(
                "The JSON structure cannot be converted to a table."
            )
