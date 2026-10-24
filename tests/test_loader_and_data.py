import io
import json

import numpy as np
import pandas as pd
import pytest

from universal_loader import load_uploaded_file


class Upload(io.BytesIO):
    def __init__(self, name, data):
        super().__init__(data)
        self.name = name


DF = pd.DataFrame({"OrderID": [1, 2, 3], "Product": ["A", "B", "A"], "Sales": [10.5, 20.0, 5.25],
                   "OrderDate": ["2025-01-01", "2025-02-01", "2025-03-01"]})


def _bytes(fmt):
    buf = io.BytesIO()
    if fmt == "csv":
        return DF.to_csv(index=False).encode()
    if fmt == "xlsx":
        DF.to_excel(buf, index=False); return buf.getvalue()
    if fmt == "parquet":
        DF.to_parquet(buf); return buf.getvalue()
    if fmt == "json":
        return DF.to_json(orient="records").encode()


@pytest.mark.parametrize("fmt", ["csv", "xlsx", "json", "parquet"])
def test_every_supported_format_loads(fmt):
    out = load_uploaded_file(Upload(f"data.{fmt}", _bytes(fmt)))
    assert list(out.columns) == list(DF.columns) and len(out) == 3
    assert out["Sales"].sum() == pytest.approx(35.75)


def test_nested_json_object():
    payload = json.dumps({"meta": 1, "rows": [{"a": 1}, {"a": 2}]}).encode()
    assert len(load_uploaded_file(Upload("x.json", payload))) == 2


def test_unsupported_extension():
    with pytest.raises(ValueError, match="Unsupported"):
        load_uploaded_file(Upload("x.txt", b"hello"))


@pytest.mark.parametrize("name,data", [("a.csv", b""), ("b.xlsx", b"not a workbook"),
                                       ("c.parquet", b"junk"), ("d.json", b"{broken")])
def test_malformed_or_empty_files_raise(name, data):
    with pytest.raises(Exception):
        out = load_uploaded_file(Upload(name, data))
        if out is None or out.empty:
            raise ValueError("empty")
