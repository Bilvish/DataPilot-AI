"""
visualization.py
================
DataPilot AI - business analytics dashboard (Streamlit + Plotly).

Public API
----------
    render_visualization(df: pd.DataFrame) -> None

Design notes
------------
* The input DataFrame is never mutated. All work happens on a prepared copy.
* Column roles (numeric / categorical / boolean / datetime / empty) are detected
  automatically; text columns are only converted to numbers or dates when the
  conversion clearly succeeds.
* Every widget key is namespaced with a dataset signature, so keys are unique and
  stale widget state cannot leak between datasets.
* Only pandas, numpy, plotly and streamlit are used (no statsmodels / scipy).
* This module must NOT import from universal_app.py (avoids circular imports).
"""

from __future__ import annotations

import hashlib
import html
import re
import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# --------------------------------------------------------------------------- #
# Design system
# --------------------------------------------------------------------------- #
PRIMARY = "#4F46E5"
ACCENT = "#E9A23B"
NEGATIVE = "#C0504D"
TEXT = "#0F172A"
GRID = "#E2E8F0"
PALETTE = [
    "#4F46E5", "#0E9F8E", "#E9A23B", "#8B5CF6",
    "#E07A5F", "#38BDF8", "#64748B", "#84A98C",
]
DIVERGING = [[0.0, "#B83A3A"], [0.5, "#FFFFFF"], [1.0, "#4F46E5"]]
FONT = "Inter, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
CHART_HEIGHT = 420

# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
KEY = "ifviz"
MISSING_LABEL = "(Missing)"
ROW_COUNT = "Row count"
NO_CHOICE = "(none)"
MAX_SCATTER_POINTS = 20_000
MAX_DIST_POINTS = 100_000
MAX_FILTER_OPTIONS = 200
MAX_TABLE_ROWS = 500
DETECTION_SAMPLE = 5_000
NUMERIC_PARSE_THRESHOLD = 0.90
DATE_PARSE_THRESHOLD = 0.80
MAX_PERIODS = 2_500

AGG_OPTIONS = ["sum", "mean", "median", "count"]
AGG_LABELS = {"sum": "Sum", "mean": "Average", "median": "Median", "count": "Count"}

GRANULARITY = {
    "Daily": ("D", 1),
    "Weekly": ("W", 7),
    "Monthly": ("M", 30),
    "Quarterly": ("Q", 91),
    "Yearly": ("Y", 365),
}


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class DatasetInfo:
    """Detected column roles and dataset-level quality statistics."""

    numeric: list[str] = field(default_factory=list)
    categorical: list[str] = field(default_factory=list)
    boolean: list[str] = field(default_factory=list)
    datetime: list[str] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)
    constant: list[str] = field(default_factory=list)
    id_like: list[str] = field(default_factory=list)
    parsed_from_text: list[str] = field(default_factory=list)
    invalid_values: dict[str, int] = field(default_factory=dict)
    distinct: dict[str, int] = field(default_factory=dict)
    dimensions: list[str] = field(default_factory=list)
    quality: pd.DataFrame = field(default_factory=pd.DataFrame)
    n_rows: int = 0
    n_cols: int = 0
    total_missing: int = 0
    duplicate_rows: int = 0

    @property
    def numeric_ordered(self) -> list[str]:
        """Numeric columns with identifier-like columns moved to the end."""
        return [c for c in self.numeric if c not in self.id_like] + [
            c for c in self.numeric if c in self.id_like
        ]


@dataclass
class Ctx:
    """Everything a dashboard section needs (selections + filtered data)."""

    sig: str
    info: DatasetInfo
    full: pd.DataFrame
    df: pd.DataFrame
    measure: Optional[str]
    agg: str
    dim: Optional[str]
    top_n: int
    filtered: bool
    agg_df: Optional[pd.DataFrame] = None

    def key(self, name: str) -> str:
        return f"{KEY}_{self.sig}_{name}"

    @property
    def metric_label(self) -> str:
        return metric_label(self.measure, self.agg)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def format_number(value, decimals: int = 2) -> str:
    """Format a number consistently (thousands separators, compact M/B/T)."""
    if value is None:
        return "â€”"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(v):
        return "â€”"
    a = abs(v)
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if a >= limit:
            return f"{v / limit:,.{decimals}f}{suffix}"
    if float(v).is_integer():
        return f"{v:,.0f}"
    return f"{v:,.{decimals}f}"


def metric_label(measure: Optional[str], agg: str) -> str:
    if measure is None or agg == "count":
        return "Record count"
    return f"{AGG_LABELS[agg]} of {measure}"


def _md(text) -> str:
    """Escape text for safe use inside Streamlit markdown."""
    return re.sub(r"([\\`*_{}\[\]<>#|$~])", r"\\\1", str(text))


def _ht(text) -> str:
    """Escape text for use inside a Plotly hovertemplate."""
    return html.escape(str(text)).replace("%{", "% {")


def _unique_names(columns) -> list[str]:
    used: set[str] = set()
    out: list[str] = []
    for c in columns:
        base = str(c)
        name, i = base, 1
        while name in used:
            i += 1
            name = f"{base} ({i})"
        used.add(name)
        out.append(name)
    return out


def _short_labels(labels, max_len: int = 42) -> list[str]:
    """Truncate long labels but keep them unique (Plotly merges equal labels)."""
    out: list[str] = []
    seen: set[str] = set()
    for lab in map(str, labels):
        s = lab if len(lab) <= max_len else lab[: max_len - 1] + "â€¦"
        base, i = s, 2
        while s in seen:
            s = f"{base} ({i})"
            i += 1
        seen.add(s)
        out.append(s)
    return out


def _sample(frame: pd.DataFrame, n: int) -> pd.DataFrame:
    return frame if len(frame) <= n else frame.sample(n, random_state=42)


# --------------------------------------------------------------------------- #
# Column detection and preparation
# --------------------------------------------------------------------------- #
def _clean_text(s: pd.Series) -> pd.Series:
    """Strip text; missing and blank values become NaN."""
    out = s.astype(str).str.strip()
    return out.where(s.notna() & out.ne(""))


def _try_numeric(cleaned: pd.Series) -> tuple[Optional[pd.Series], int]:
    """Return (numeric series, invalid count) if a text column is mostly numeric."""
    nn = cleaned.dropna()
    if nn.empty:
        return None, 0
    sample = nn.iloc[:DETECTION_SAMPLE]
    # Codes with leading zeros (ZIP codes, SKUs) are identifiers, not measures.
    if sample.str.match(r"^0\d+$").mean() > 0.5:
        return None, 0
    if pd.to_numeric(sample, errors="coerce").notna().mean() < NUMERIC_PARSE_THRESHOLD:
        return None, 0
    parsed = pd.to_numeric(cleaned, errors="coerce")
    invalid = int((cleaned.notna() & parsed.isna()).sum())
    return parsed.astype("float64"), invalid


def _try_datetime(cleaned: pd.Series) -> tuple[Optional[pd.Series], int]:
    """Return (datetime series, invalid count) if a text column is mostly dates."""
    nn = cleaned.dropna()
    if nn.empty:
        return None, 0
    sample = nn.iloc[:DETECTION_SAMPLE]
    if sample.str.len().median() < 6:
        return None, 0
    if sample.str.contains(r"\d").mean() < DATE_PARSE_THRESHOLD:
        return None, 0
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ps = pd.to_datetime(sample, errors="coerce", format="mixed")
            if ps.notna().mean() < DATE_PARSE_THRESHOLD:
                return None, 0
            parsed = pd.to_datetime(cleaned, errors="coerce", format="mixed")
    except (ValueError, TypeError, OverflowError):
        return None, 0
    if not pd.api.types.is_datetime64_any_dtype(parsed):
        return None, 0
    if getattr(parsed.dt, "tz", None) is not None:
        parsed = parsed.dt.tz_localize(None)
    invalid = int((cleaned.notna() & parsed.isna()).sum())
    return parsed, invalid


def _safe_duplicates(df: pd.DataFrame) -> int:
    try:
        return int(df.duplicated().sum())
    except TypeError:  # unhashable cells (lists / dicts from JSON)
        return int(df.astype(str).duplicated().sum())


def prepare_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, DatasetInfo]:
    """Build an analysis-ready copy of ``df`` plus column-role / quality metadata."""
    work = df.copy()
    work.columns = _unique_names(df.columns)
    work = work.reset_index(drop=True)

    info = DatasetInfo(n_rows=len(work), n_cols=work.shape[1])
    info.duplicate_rows = _safe_duplicates(df)
    rows: list[dict] = []

    def add_row(col, kind, stored, missing, notes):
        n = max(len(work), 1)
        rows.append(
            {
                "Column": col,
                "Detected type": kind,
                "Stored dtype": stored,
                "Missing": int(missing),
                "Missing %": round(100 * missing / n, 2),
                "Distinct values": 0,
                "Notes": "; ".join(notes) if notes else "",
            }
        )

    for i, col in enumerate(list(work.columns)):
        s = work[col]
        stored = str(df.dtypes.iloc[i])
        notes: list[str] = []

        if s.notna().sum() == 0:
            info.empty.append(col)
            add_row(col, "Empty", stored, len(work), ["Empty column"])
            continue

        if pd.api.types.is_bool_dtype(s):
            work[col] = s.map(lambda v: np.nan if pd.isna(v) else str(bool(v))).astype(object)
            info.boolean.append(col)
            add_row(col, "Boolean", stored, s.isna().sum(), notes)

        elif pd.api.types.is_datetime64_any_dtype(s):
            if getattr(s.dt, "tz", None) is not None:
                work[col] = s.dt.tz_localize(None)
            info.datetime.append(col)
            add_row(col, "Datetime", stored, s.isna().sum(), notes)

        elif pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_complex_dtype(s):
            x = pd.to_numeric(s, errors="coerce").astype("float64")
            x = x.replace([np.inf, -np.inf], np.nan)
            work[col] = x
            info.numeric.append(col)
            add_row(col, "Numeric", stored, s.isna().sum(), notes)

        else:
            cleaned = _clean_text(s)
            if cleaned.notna().sum() == 0:
                info.empty.append(col)
                add_row(col, "Empty", stored, len(work), ["Empty column (blank text only)"])
                continue
            num, bad_n = _try_numeric(cleaned)
            if num is not None:
                work[col] = num
                info.numeric.append(col)
                info.parsed_from_text.append(col)
                if bad_n:
                    info.invalid_values[col] = bad_n
                    notes.append(f"{bad_n:,} non-numeric entries ignored")
                notes.insert(0, "Numbers stored as text")
                add_row(col, "Numeric (from text)", stored, cleaned.isna().sum(), notes)
                continue
            dt, bad_d = _try_datetime(cleaned)
            if dt is not None:
                work[col] = dt
                info.datetime.append(col)
                info.parsed_from_text.append(col)
                if bad_d:
                    info.invalid_values[col] = bad_d
                    notes.append(f"{bad_d:,} values could not be parsed as dates")
                notes.insert(0, "Dates stored as text")
                add_row(col, "Datetime (from text)", stored, cleaned.isna().sum(), notes)
                continue
            work[col] = cleaned
            info.categorical.append(col)
            add_row(col, "Categorical", stored, cleaned.isna().sum(), notes)

    # Distinct counts, constant / identifier-like flags, notes.
    qrows = {r["Column"]: r for r in rows}
    for col in work.columns:
        if col in info.empty:
            continue
        nunique = int(work[col].nunique(dropna=True))
        info.distinct[col] = nunique
        q = qrows[col]
        q["Distinct values"] = nunique
        non_null = len(work) - q["Missing"]
        if nunique == 1:
            info.constant.append(col)
            q["Notes"] = "; ".join(filter(None, [q["Notes"], "Constant value"]))
        if col in info.numeric and non_null >= 20 and nunique == non_null:
            vals = work[col].dropna()
            if (vals % 1 == 0).all():
                info.id_like.append(col)
        if col in info.numeric and re.search(r"(^|[^a-z])id$", col.lower()):
            if col not in info.id_like:
                info.id_like.append(col)
        if col in info.categorical and nunique > 50 and non_null and nunique / non_null > 0.5:
            q["Notes"] = "; ".join(
                filter(None, [q["Notes"], "High cardinality (possible identifier)"])
            )
        if q["Missing %"] >= 30:
            q["Notes"] = "; ".join(filter(None, [q["Notes"], "High share of missing values"]))

    info.dimensions = sorted(
        info.categorical + info.boolean, key=lambda c: info.distinct.get(c, 0)
    )
    info.total_missing = int(sum(r["Missing"] for r in rows))
    info.quality = pd.DataFrame(rows)
    return work, info


@st.cache_data(show_spinner=False, max_entries=3)
def _prepare_cached(df: pd.DataFrame) -> tuple[pd.DataFrame, DatasetInfo]:
    return prepare_dataset(df)


def get_prepared(df: pd.DataFrame) -> tuple[pd.DataFrame, DatasetInfo]:
    """Cached preparation; falls back to uncached if the frame cannot be hashed."""
    try:
        return _prepare_cached(df)
    except Exception:  # e.g. unhashable cell values
        return prepare_dataset(df)


def groupable_dims(info: DatasetInfo, lo: int = 2, hi: int = 12) -> list[str]:
    """Dimensions with a small, sensible number of levels (for colour / split)."""
    return [c for c in info.dimensions if lo <= info.distinct.get(c, 0) <= hi]


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def _agg_series(gb, agg: str, col: str = "m") -> pd.Series:
    if agg == "count":
        return gb.size()
    target = gb[col]
    if agg == "sum":
        return target.sum(min_count=1)  # all-missing group -> NaN, not 0
    if agg == "mean":
        return target.mean()
    return target.median()


def aggregate_by(df: pd.DataFrame, dim: str, measure: Optional[str], agg: str) -> pd.DataFrame:
    """Group by ``dim``; returns columns category, value, records (sorted desc)."""
    tmp = pd.DataFrame({"category": df[dim].fillna(MISSING_LABEL).astype(str)})
    if measure is not None and agg != "count":
        tmp["m"] = df[measure]
    gb = tmp.groupby("category", sort=False)
    out = pd.DataFrame({"value": _agg_series(gb, agg), "records": gb.size()}).reset_index()
    out = out.dropna(subset=["value"])
    return out.sort_values("value", ascending=False, kind="mergesort").reset_index(drop=True)


def is_additive(agg_df: pd.DataFrame, agg: str) -> bool:
    """Shares of total only make sense for non-negative sums / counts."""
    return (
        agg in ("sum", "count")
        and not agg_df.empty
        and bool((agg_df["value"] >= 0).all())
        and agg_df["value"].sum() > 0
    )


def contribution_table(agg_df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Top-N categories plus an 'Other' bucket, with share and cumulative share."""
    total = agg_df["value"].sum()
    top = agg_df.head(n)[["category", "value"]].copy()
    rest = agg_df.iloc[n:]
    if not rest.empty:
        top = pd.concat(
            [
                top,
                pd.DataFrame(
                    {"category": [f"Other ({len(rest)} more)"], "value": [rest["value"].sum()]}
                ),
            ],
            ignore_index=True,
        )
    top["share"] = top["value"] / total
    top["cumulative"] = top["share"].cumsum()
    return top


def summary_table(df: pd.DataFrame, dim: str, measure: Optional[str]) -> pd.DataFrame:
    """Category-level summary: records, sum, mean, median and share."""
    keys = df[dim].fillna(MISSING_LABEL).astype(str)
    if measure is None:
        out = keys.groupby(keys).size().rename("Records").to_frame()
        out["Share of records (%)"] = (100 * out["Records"] / out["Records"].sum()).round(2)
        out = out.sort_values("Records", ascending=False)
    else:
        g = df[measure].groupby(keys)
        out = pd.DataFrame(
            {
                "Records": keys.groupby(keys).size(),
                "Valid values": g.count(),
                "Sum": g.sum(min_count=1),
                "Average": g.mean(),
                "Median": g.median(),
            }
        )
        total = out["Sum"].sum()
        if (out["Sum"].dropna() >= 0).all() and total > 0:
            out["Share of sum (%)"] = (100 * out["Sum"] / total).round(2)
        out = out.sort_values("Sum", ascending=False)
    out.index.name = dim
    return out.reset_index()


def build_time_series(
    df: pd.DataFrame,
    date_col: str,
    measure: Optional[str],
    agg: str,
    freq: str,
    split: Optional[str] = None,
    max_split: int = 6,
) -> Optional[pd.DataFrame]:
    """Aggregate by calendar period. Returns a wide frame indexed by PeriodIndex."""
    cols = {"d": df[date_col]}
    if measure is not None and agg != "count":
        cols["m"] = df[measure]
    if split:
        cols["g"] = df[split].fillna(MISSING_LABEL).astype(str)
    tmp = pd.DataFrame(cols).dropna(subset=["d"])
    if tmp.empty:
        return None
    tmp["p"] = tmp["d"].dt.to_period(freq)
    full = pd.period_range(tmp["p"].min(), tmp["p"].max(), freq=freq)
    additive = agg in ("sum", "count")
    if split:
        keep = tmp["g"].value_counts().head(max_split).index
        tmp = tmp[tmp["g"].isin(keep)]
        wide = _agg_series(tmp.groupby(["p", "g"]), agg).unstack("g").reindex(full)
    else:
        wide = pd.DataFrame({"Overall": _agg_series(tmp.groupby("p"), agg).reindex(full)})
    if additive:
        wide = wide.fillna(0)
    return wide


def describe_series(s: pd.Series) -> Optional[dict]:
    s = s.dropna()
    if s.empty:
        return None
    q1, med, q3 = s.quantile([0.25, 0.5, 0.75])
    iqr = q3 - q1
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return {
        "Count": int(len(s)),
        "Min": s.min(),
        "Q1": q1,
        "Median": med,
        "Mean": s.mean(),
        "Q3": q3,
        "Max": s.max(),
        "Std dev": s.std() if len(s) > 1 else np.nan,
        "IQR": iqr,
        "Outliers (1.5Ã—IQR rule)": int(((s < lo) | (s > hi)).sum()),
    }


def strength_label(r: float) -> str:
    a = abs(r)
    if a < 0.1:
        return "negligible"
    if a < 0.3:
        return "weak"
    if a < 0.5:
        return "moderate"
    if a < 0.7:
        return "strong"
    return "very strong"


# --------------------------------------------------------------------------- #
# Figure styling and display
# --------------------------------------------------------------------------- #
def style_figure(
    fig: go.Figure,
    title: str,
    *,
    height: int = CHART_HEIGHT,
    legend: bool = False,
    subtitle: Optional[str] = None,
) -> go.Figure:
    """Apply the shared dashboard theme to any Plotly figure."""
    text = f"<b>{html.escape(title)}</b>"
    if subtitle:
        text += f"<br><sup>{html.escape(subtitle)}</sup>"
    fig.update_layout(
        template="plotly_white",
        title=dict(text=text, x=0.0, xanchor="left", font=dict(size=16, color=TEXT)),
        font=dict(family=FONT, size=12, color=TEXT),
        height=height,
        margin=dict(l=10, r=20, t=75 if subtitle else 55, b=10),
        paper_bgcolor="white",
        plot_bgcolor="white",
        colorway=PALETTE,
        showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title_text=""),
        hoverlabel=dict(bgcolor="white", font_size=12, bordercolor=GRID),
    )
    fig.update_xaxes(showgrid=False, showline=True, linecolor=GRID, zeroline=False, automargin=True)
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False, automargin=True)
    return fig


def show_chart(fig: go.Figure, key: str) -> None:
    config = {"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]}
    try:
        st.plotly_chart(fig, width="stretch", theme=None, key=key, config=config)
    except TypeError:  # older Streamlit
        st.plotly_chart(fig, use_container_width=True, theme=None, key=key, config=config)


def show_table(data: pd.DataFrame, height: Optional[int] = None) -> None:
    kwargs = {"hide_index": True}
    if height:
        kwargs["height"] = height
    try:
        st.dataframe(data, width="stretch", **kwargs)
    except TypeError:
        st.dataframe(data, use_container_width=True, **kwargs)


def kpi_cards(items: list[tuple[str, str, str]]) -> None:
    """Render a row of bordered KPI cards: (label, value, caption)."""
    for col, (label, value, caption) in zip(st.columns(len(items)), items):
        with col:
            with st.container(border=True):
                st.metric(label, value)
                st.caption(caption or "\u00a0")


def show_observations(items: list[str]) -> None:
    if items:
        st.markdown("**Key observations** (calculated from the data shown)")
        st.markdown("\n".join(f"- {i}" for i in items))


# --------------------------------------------------------------------------- #
# Chart builders
# --------------------------------------------------------------------------- #
def ranked_bar_figure(table: pd.DataFrame, title: str, value_label: str) -> go.Figure:
    labels = _short_labels(table["category"])
    fig = go.Figure(
        go.Bar(
            x=table["value"],
            y=labels,
            orientation="h",
            marker=dict(color=PRIMARY),
            text=[format_number(v) for v in table["value"]],
            textposition="outside",
            cliponaxis=False,
            customdata=[[str(c), int(r)] for c, r in zip(table["category"], table["records"])],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>" + _ht(value_label)
                + ": %{x:,.2f}<br>Records: %{customdata[1]:,}<extra></extra>"
            ),
        )
    )
    style_figure(fig, title, height=max(320, 36 * len(labels) + 130))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=True, gridcolor=GRID, title=value_label)
    return fig


def pareto_figure(table: pd.DataFrame, title: str, value_label: str) -> go.Figure:
    labels = _short_labels(table["category"])
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=labels,
            y=table["share"] * 100,
            name="Share of total",
            marker=dict(color=PRIMARY),
            customdata=[[format_number(v)] for v in table["value"]],
            hovertemplate="<b>%{x}</b><br>Share: %{y:.1f}%<br>" + _ht(value_label)
            + ": %{customdata[0]}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=labels,
            y=table["cumulative"] * 100,
            name="Cumulative share",
            yaxis="y2",
            mode="lines+markers",
            line=dict(color=ACCENT, width=2.5),
            hovertemplate="<b>%{x}</b><br>Cumulative: %{y:.1f}%<extra></extra>",
        )
    )
    style_figure(fig, title, legend=True)
    fig.update_layout(
        yaxis=dict(title="Share of total", ticksuffix="%", rangemode="tozero"),
        yaxis2=dict(
            title="Cumulative", overlaying="y", side="right", range=[0, 105],
            ticksuffix="%", showgrid=False,
        ),
    )
    fig.update_xaxes(tickangle=-35)
    return fig


def breakdown_figure(
    long: pd.DataFrame, order: list[str], title: str, value_label: str, mode: str
) -> go.Figure:
    """Grouped / stacked / 100% stacked horizontal bars (long: category, group, value)."""
    label_map = dict(zip(order, _short_labels(order)))
    fig = go.Figure()
    groups = list(long["group"].unique())
    for i, g in enumerate(groups):
        sub = long[long["group"] == g].set_index("category").reindex(order)
        vals = sub["value"].to_numpy()
        fig.add_trace(
            go.Bar(
                name=str(g),
                x=vals,
                y=[label_map[c] for c in order],
                orientation="h",
                marker=dict(color=PALETTE[i % len(PALETTE)]),
                customdata=[[c] for c in order],
                hovertemplate="<b>%{customdata[0]}</b><br>" + _ht(g) + ": %{x:,.2f}<extra></extra>",
            )
        )
    fig.update_layout(barmode="group" if mode == "Grouped" else "stack")
    n_bars = len(order) * (len(groups) if mode == "Grouped" else 1)
    style_figure(fig, title, legend=True, height=max(360, 30 * n_bars + 150))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(
        showgrid=True, gridcolor=GRID,
        title="% of category total" if mode == "100% stacked" else value_label,
    )
    return fig


def time_series_figure(wide: pd.DataFrame, title: str, value_label: str, split: bool) -> go.Figure:
    x = wide.index.to_timestamp()
    labels = [str(p) for p in wide.index]
    mode = "lines+markers" if len(wide) <= 60 else "lines"
    fig = go.Figure()
    for i, col in enumerate(wide.columns):
        extra = _ht(col) if split else ""
        fig.add_trace(
            go.Scatter(
                x=x,
                y=wide[col],
                mode=mode,
                name=str(col),
                line=dict(color=PALETTE[i % len(PALETTE)], width=2.5),
                marker=dict(size=6),
                connectgaps=False,
                customdata=labels,
                hovertemplate="<b>%{customdata}</b><br>" + _ht(value_label)
                + f": %{{y:,.2f}}<extra>{extra}</extra>",
            )
        )
    style_figure(fig, title, legend=split)
    fig.update_xaxes(title="Period start")
    fig.update_yaxes(title=value_label, rangemode="tozero" if not split else "normal")
    return fig


def histogram_figure(
    data: pd.DataFrame, col: str, group: Optional[str], bins: int
) -> go.Figure:
    if group:
        fig = px.histogram(
            data, x=col, color=group, nbins=bins, barmode="overlay",
            color_discrete_sequence=PALETTE,
        )
        fig.update_traces(opacity=0.65)
    else:
        fig = px.histogram(data, x=col, nbins=bins, color_discrete_sequence=[PRIMARY])
    style_figure(fig, f"Distribution of {col}", legend=bool(group))
    fig.update_yaxes(title="Records")
    fig.update_xaxes(title=col)
    return fig


def box_figure(data: pd.DataFrame, col: str, group: Optional[str]) -> go.Figure:
    if group:
        fig = px.box(
            data, x=col, y=group, color=group, orientation="h", points="outliers",
            color_discrete_sequence=PALETTE,
        )
        fig.update_yaxes(showgrid=False)
    else:
        fig = px.box(data, x=col, points="outliers", color_discrete_sequence=[PRIMARY])
    style_figure(fig, f"Spread and outliers: {col}", legend=False)
    fig.update_xaxes(title=col, showgrid=True, gridcolor=GRID)
    return fig


# --------------------------------------------------------------------------- #
# Controls and filters
# --------------------------------------------------------------------------- #
def render_controls(work: pd.DataFrame, info: DatasetInfo, sig: str) -> Ctx:
    def key(name: str) -> str:
        return f"{KEY}_{sig}_{name}"

    col_index = {c: i for i, c in enumerate(work.columns)}

    with st.expander("Dashboard controls and filters", expanded=True):
        c1, c2, c3, c4 = st.columns([2, 2, 1.2, 1.2])
        measure_choice = c1.selectbox(
            "Primary measure",
            info.numeric_ordered + [ROW_COUNT],
            key=key("measure"),
            help="Numeric column to analyse. Choose 'Row count' to just count records.",
        )
        measure = None if measure_choice == ROW_COUNT else measure_choice

        if info.dimensions:
            dim_default = next(
                (i for i, c in enumerate(info.dimensions) if info.distinct.get(c, 0) >= 2), 0
            )
            dim = c2.selectbox(
                "Comparison dimension", info.dimensions, index=dim_default, key=key("dim"),
                help="Categorical column used to compare groups.",
            )
        else:
            dim = None
            c2.selectbox(
                "Comparison dimension", ["(no categorical columns)"], disabled=True, key=key("dim_none")
            )

        agg = c3.selectbox(
            "Aggregation", AGG_OPTIONS, format_func=lambda a: AGG_LABELS[a],
            key=key("agg"), disabled=measure is None,
            help="'Count' counts records (rows) in each group.",
        )
        if measure is None:
            agg = "count"
        top_n = c4.slider("Top N", 3, 25, 10, key=key("topn"))

        st.markdown("**Filters** Â· applied to every section except Data quality")
        mask = pd.Series(True, index=work.index)
        active: list[str] = []

        if info.datetime:
            f1, f2 = st.columns([1, 2])
            date_col = f1.selectbox("Date filter column", [NO_CHOICE] + info.datetime, key=key("fdate"))
            if date_col != NO_CHOICE:
                d = work[date_col].dropna()
                if not d.empty:
                    dmin, dmax = d.min().date(), d.max().date()
                    rng = f2.date_input(
                        "Date range", value=(dmin, dmax), min_value=dmin, max_value=dmax,
                        key=key(f"frange_{col_index[date_col]}"),
                    )
                    if isinstance(rng, (tuple, list)) and len(rng) == 2 and tuple(rng) != (dmin, dmax):
                        start = pd.Timestamp(rng[0])
                        end = pd.Timestamp(rng[1]) + pd.Timedelta(days=1)
                        mask &= (work[date_col] >= start) & (work[date_col] < end)
                        active.append(f"{date_col}: {rng[0]} to {rng[1]}")

        if info.dimensions:
            fcols = st.multiselect("Filter by category columns", info.dimensions, key=key("fcols"))
            if fcols:
                grid = st.columns(min(3, len(fcols)))
                for i, col in enumerate(fcols):
                    series = work[col].fillna(MISSING_LABEL)
                    counts = series.value_counts()
                    options = list(counts.index[:MAX_FILTER_OPTIONS])
                    help_text = (
                        f"Showing the {MAX_FILTER_OPTIONS} most frequent of {len(counts):,} values."
                        if len(counts) > MAX_FILTER_OPTIONS else None
                    )
                    with grid[i % len(grid)]:
                        chosen = st.multiselect(
                            col, options, key=key(f"fval_{col_index[col]}"),
                            help=help_text, placeholder="All values",
                        )
                    if chosen:
                        mask &= series.isin(chosen)
                        active.append(f"{col}: {len(chosen)} selected")

    filtered = bool(active)
    df = work[mask] if filtered else work
    st.caption(
        f"Showing **{len(df):,}** of {len(work):,} records"
        + (f" Â· active filters: {_md('; '.join(active))}" if active else " Â· no filters active")
    )
    ctx = Ctx(sig, info, work, df, measure, agg, dim, top_n, filtered)
    if dim is not None and len(df):
        ctx.agg_df = aggregate_by(df, dim, measure, agg)
    return ctx


# --------------------------------------------------------------------------- #
# Section A - Executive overview
# --------------------------------------------------------------------------- #
def render_overview(ctx: Ctx) -> None:
    info, df = ctx.info, ctx.df
    n, total_n = len(df), len(ctx.full)
    cells = max(info.n_rows * info.n_cols, 1)

    kpi_cards(
        [
            ("Records", f"{n:,}", f"{n / total_n:.0%} of dataset" if ctx.filtered else "Full dataset"),
            ("Columns", f"{info.n_cols:,}",
             f"{len(info.dimensions)} categorical Â· {len(info.datetime)} date"),
            ("Numeric fields", f"{len(info.numeric):,}",
             f"{len(info.id_like)} look like identifiers" if info.id_like else "Available as measures"),
            ("Missing cells", f"{info.total_missing:,}",
             f"{100 * info.total_missing / cells:.1f}% of cells Â· full dataset"),
            ("Duplicate rows", f"{info.duplicate_rows:,}",
             f"{100 * info.duplicate_rows / max(info.n_rows, 1):.1f}% of rows Â· full dataset"),
        ]
    )

    m = ctx.measure
    if m is not None:
        valid = df[m].dropna()
        if valid.empty:
            st.warning(f"'{m}' has no valid numeric values in the current selection.")
        else:
            kpi_cards(
                [
                    (f"Sum Â· {m}", format_number(valid.sum()), "Missing values ignored"),
                    (f"Average Â· {m}", format_number(valid.mean()), "Arithmetic mean"),
                    (f"Median Â· {m}", format_number(valid.median()), "Middle value"),
                    ("Valid values", f"{len(valid):,}", f"{len(valid) / max(n, 1):.1%} of records"),
                ]
            )
        if m in info.invalid_values:
            st.caption(
                f"{info.invalid_values[m]:,} non-numeric entries in '{m}' are excluded from calculations."
            )
    else:
        st.caption("No numeric column selected - charts below show record counts.")

    if ctx.dim is None:
        st.info("No categorical column was detected, so category comparisons are unavailable. "
                "Showing the distribution of the primary measure instead.")
        if m is not None and df[m].notna().any():
            show_chart(histogram_figure(_sample(df[[m]], MAX_DIST_POINTS), m, None, 30), ctx.key("ov_hist"))
        return

    agg_df = ctx.agg_df
    if agg_df is None or agg_df.empty:
        st.warning("There is no data to compare for this combination of measure and dimension.")
        return

    additive = is_additive(agg_df, ctx.agg)
    left, right = st.columns([1.15, 1])
    with left:
        top = agg_df.head(ctx.top_n)
        sub = f"Top {len(top)} of {len(agg_df):,} categories" if len(agg_df) > len(top) else None
        fig = ranked_bar_figure(top, f"{ctx.metric_label} by {ctx.dim}", ctx.metric_label)
        if sub:
            fig = style_figure(fig, f"{ctx.metric_label} by {ctx.dim}", subtitle=sub,
                               height=fig.layout.height)
        show_chart(fig, ctx.key("ov_rank"))
    with right:
        if additive and len(agg_df) > 1:
            table = contribution_table(agg_df, ctx.top_n)
            show_chart(
                pareto_figure(table, f"Contribution to total by {ctx.dim}", ctx.metric_label),
                ctx.key("ov_pareto"),
            )
        else:
            st.info(
                "Contribution-to-total is shown only for non-negative sums or counts with more than "
                "one category. Averages and medians are not additive, so shares would be misleading."
            )

    obs: list[str] = []
    top_row = agg_df.iloc[0]
    line = (f"**{_md(top_row['category'])}** has the highest {_md(ctx.metric_label.lower())} "
            f"({format_number(top_row['value'])})")
    if additive:
        line += f", {100 * top_row['value'] / agg_df['value'].sum():.1f}% of the total"
    obs.append(line + ".")
    if len(agg_df) > 1:
        low = agg_df.iloc[-1]
        obs.append(f"The lowest is **{_md(low['category'])}** ({format_number(low['value'])}).")
    if additive and len(agg_df) > 3:
        share3 = 100 * agg_df["value"].head(3).sum() / agg_df["value"].sum()
        obs.append(f"The top 3 of {len(agg_df):,} categories account for {share3:.1f}% of the total.")
    if m is not None:
        valid = df[m].dropna()
        if len(valid) > 1 and valid.median() != 0:
            mean, med = valid.mean(), valid.median()
            if mean > 1.25 * med > 0:
                obs.append(f"The average of {_md(m)} ({format_number(mean)}) is well above its median "
                           f"({format_number(med)}), so a minority of high values pulls the average up.")
    q = info.quality
    if not q.empty and q["Missing"].max() > 0:
        worst = q.sort_values("Missing %", ascending=False).iloc[0]
        obs.append(f"Largest share of missing values: **{_md(worst['Column'])}** "
                   f"({worst['Missing %']:.1f}%).")
    else:
        obs.append("No missing values were found in the dataset.")
    if info.duplicate_rows:
        obs.append(f"{info.duplicate_rows:,} fully duplicated rows are present in the dataset.")
    show_observations(obs)


# --------------------------------------------------------------------------- #
# Section B - Trend analysis
# --------------------------------------------------------------------------- #
def _auto_granularity(dates: pd.Series) -> str:
    d = dates.dropna()
    if d.empty:
        return "Monthly"
    span = (d.max() - d.min()).days
    if span <= 31:
        return "Daily"
    if span <= 180:
        return "Weekly"
    if span <= 1100:
        return "Monthly"
    if span <= 3650:
        return "Quarterly"
    return "Yearly"


def render_category_fallback(ctx: Ctx) -> None:
    """Alternative analysis used when a time series is not possible."""
    if ctx.dim and ctx.agg_df is not None and not ctx.agg_df.empty:
        top = ctx.agg_df.head(ctx.top_n)
        show_chart(
            ranked_bar_figure(top, f"{ctx.metric_label} by {ctx.dim}", ctx.metric_label),
            ctx.key("alt_rank"),
        )
    elif ctx.measure and ctx.df[ctx.measure].notna().any():
        show_chart(
            histogram_figure(_sample(ctx.df[[ctx.measure]], MAX_DIST_POINTS), ctx.measure, None, 30),
            ctx.key("alt_hist"),
        )


def render_trend(ctx: Ctx) -> None:
    info, df = ctx.info, ctx.df
    if not info.datetime:
        st.info(
            "No date/time column was detected, so a time series cannot be drawn. Plotting an "
            "unordered category as a line would be misleading. Showing a category comparison instead."
        )
        render_category_fallback(ctx)
        return

    c1, c2, c3 = st.columns(3)
    date_col = c1.selectbox("Date column", info.datetime, key=ctx.key("t_date"))
    valid_dates = df[date_col].dropna()
    if valid_dates.empty:
        st.warning(f"'{date_col}' has no valid dates in the current selection.")
        return
    grans = list(GRANULARITY)
    gran = c2.selectbox(
        "Time granularity", grans, index=grans.index(_auto_granularity(valid_dates)),
        key=ctx.key("t_gran"),
    )
    split_opts = [NO_CHOICE] + groupable_dims(info, 2, 20)
    split_choice = c3.selectbox(
        "Compare categories (optional)", split_opts, key=ctx.key("t_split"),
        help="Draws one line per category (up to 6 most frequent).",
    )
    split = None if split_choice == NO_CHOICE else split_choice

    freq, days = GRANULARITY[gran]
    span_days = (valid_dates.max() - valid_dates.min()).days + 1
    if span_days / days > MAX_PERIODS:
        st.warning(f"{gran} granularity would create more than {MAX_PERIODS:,} points for this date "
                   f"range. Please choose a coarser granularity.")
        return

    wide = build_time_series(df, date_col, ctx.measure, ctx.agg, freq, split)
    if wide is None or wide.dropna(how="all").empty:
        st.warning("No data is available for the selected date column and measure.")
        return

    dropped = int(df[date_col].isna().sum())
    if dropped:
        st.caption(f"{dropped:,} records have a missing or unparseable date and are excluded from this chart.")

    title = f"{ctx.metric_label} over time ({gran.lower()})"
    show_chart(time_series_figure(wide, title, ctx.metric_label, split is not None), ctx.key("t_chart"))

    if split is None:
        s = wide["Overall"].dropna()
        obs: list[str] = []
        if not s.empty:
            peak, trough = s.idxmax(), s.idxmin()
            obs.append(f"Highest {_md(ctx.metric_label.lower())}: **{peak}** ({format_number(s.max())}).")
            if len(s) > 1:
                obs.append(f"Lowest: **{trough}** ({format_number(s.min())}).")
                last, prev = s.iloc[-1], s.iloc[-2]
                if prev != 0:
                    obs.append(f"The latest period ({s.index[-1]}) is {format_number(last)}, "
                               f"{100 * (last - prev) / abs(prev):+.1f}% versus the previous period "
                               f"({format_number(prev)}). The latest period may be incomplete.")
        show_observations(obs)

    with st.expander("View aggregated data"):
        table = wide.copy()
        table.index = [str(p) for p in table.index]
        table = table.rename_axis("Period").reset_index()
        show_table(table, height=300)
        st.download_button("Download trend data (CSV)", table.to_csv(index=False).encode("utf-8"),
                           file_name="trend_data.csv", mime="text/csv", key=ctx.key("t_dl"))


# --------------------------------------------------------------------------- #
# Section C - Category and segment analysis
# --------------------------------------------------------------------------- #
def render_category(ctx: Ctx) -> None:
    info, df = ctx.info, ctx.df
    if ctx.dim is None or ctx.agg_df is None or ctx.agg_df.empty:
        st.info("This section needs at least one categorical column with data in the current selection.")
        return
    agg_df = ctx.agg_df
    additive = is_additive(agg_df, ctx.agg)

    c1, c2, c3 = st.columns(3)
    rank_mode = c1.radio("Show", ["Highest", "Lowest"], horizontal=True, key=ctx.key("c_rank"))
    brk_opts = [NO_CHOICE] + [c for c in groupable_dims(info, 2, 8) if c != ctx.dim]
    brk_choice = c2.selectbox("Break down by (optional)", brk_opts, key=ctx.key("c_brk"))
    brk = None if brk_choice == NO_CHOICE else brk_choice
    modes = ["Grouped"] + (["Stacked", "100% stacked"] if additive else [])
    mode = c3.radio("Bar layout", modes, horizontal=True, key=ctx.key("c_mode"), disabled=brk is None)
    if brk and not additive:
        st.caption("Stacked layouts are hidden because averages/medians (or negative values) "
                   "cannot be added across groups.")

    ordered = agg_df if rank_mode == "Highest" else agg_df.iloc[::-1]
    top = ordered.head(ctx.top_n).reset_index(drop=True)
    order = list(top["category"])
    note = f"{'Top' if rank_mode == 'Highest' else 'Bottom'} {len(top)} of {len(agg_df):,} categories"

    if brk is None:
        fig = ranked_bar_figure(top, f"{ctx.metric_label} by {ctx.dim}", ctx.metric_label)
        fig = style_figure(fig, f"{ctx.metric_label} by {ctx.dim}", subtitle=note, height=fig.layout.height)
        show_chart(fig, ctx.key("c_rank_chart"))
    else:
        sub = df[df[ctx.dim].fillna(MISSING_LABEL).astype(str).isin(order)]
        tmp = pd.DataFrame(
            {
                "category": sub[ctx.dim].fillna(MISSING_LABEL).astype(str),
                "group": sub[brk].fillna(MISSING_LABEL).astype(str),
            }
        )
        if ctx.measure is not None and ctx.agg != "count":
            tmp["m"] = sub[ctx.measure]
        long = _agg_series(tmp.groupby(["category", "group"]), ctx.agg).rename("value").reset_index()
        long = long.dropna(subset=["value"])
        if mode == "100% stacked":
            totals = long.groupby("category")["value"].transform("sum")
            long["value"] = 100 * long["value"] / totals.where(totals != 0)
        fig = breakdown_figure(long, order, f"{ctx.metric_label} by {ctx.dim} and {brk}",
                               ctx.metric_label, mode)
        show_chart(fig, ctx.key("c_brk_chart"))
        st.caption(note)

    st.markdown("**Category summary**")
    table = summary_table(df, ctx.dim, ctx.measure)
    show_table(table.head(MAX_TABLE_ROWS).round(2), height=320)
    if len(table) > MAX_TABLE_ROWS:
        st.caption(f"Table shows the first {MAX_TABLE_ROWS} of {len(table):,} categories; "
                   "the download contains all of them.")
    st.download_button("Download category summary (CSV)", table.to_csv(index=False).encode("utf-8"),
                       file_name="category_summary.csv", mime="text/csv", key=ctx.key("c_dl"))

    obs = [f"**{_md(agg_df.iloc[0]['category'])}** ranks first on {_md(ctx.metric_label.lower())} "
           f"({format_number(agg_df.iloc[0]['value'])})."]
    if (agg_df["category"] == MISSING_LABEL).any():
        miss = agg_df[agg_df["category"] == MISSING_LABEL].iloc[0]
        obs.append(f"{int(miss['records']):,} records have no value in '{_md(ctx.dim)}' and are grouped "
                   f"as {MISSING_LABEL}.")
    if additive and len(agg_df) > 1:
        obs.append(f"The top {min(ctx.top_n, len(agg_df))} categories contribute "
                   f"{100 * agg_df['value'].head(ctx.top_n).sum() / agg_df['value'].sum():.1f}% of the total.")
    show_observations(obs)


# --------------------------------------------------------------------------- #
# Section D - Relationships and drivers
# --------------------------------------------------------------------------- #
def render_relationships(ctx: Ctx) -> None:
    info, df = ctx.info, ctx.df
    nums = [c for c in info.numeric_ordered if df[c].notna().sum() >= 3]
    if len(nums) < 2:
        st.info("Relationship analysis needs at least two numeric columns with 3 or more valid values. "
                "See the Distributions section for single-column analysis.")
        return

    c1, c2, c3 = st.columns(3)
    x = c1.selectbox("X axis", nums, index=0, key=ctx.key("r_x"))
    y = c2.selectbox("Y axis", nums, index=1, key=ctx.key("r_y"))
    color_opts = [NO_CHOICE] + groupable_dims(info, 2, 12)
    color_choice = c3.selectbox("Colour by (optional)", color_opts, key=ctx.key("r_color"))
    color = None if color_choice == NO_CHOICE else color_choice
    show_trend = st.checkbox("Show linear trend line", value=True, key=ctx.key("r_trend"))
    if x == y:
        st.warning("Choose two different columns.")
    else:
        plot = df[[x, y] + ([color] if color else [])].copy().dropna(subset=[x, y])
        if len(plot) < 3:
            st.warning("Fewer than 3 records have valid values for both columns.")
        else:
            xv, yv = plot[x].to_numpy(float), plot[y].to_numpy(float)
            r = rho = np.nan
            if np.ptp(xv) > 0 and np.ptp(yv) > 0:
                r = float(np.corrcoef(xv, yv)[0, 1])
                rho = float(plot[x].rank().corr(plot[y].rank()))
            drawn = _sample(plot, MAX_SCATTER_POINTS)
            if color:
                drawn = drawn.copy()
                keep = drawn[color].fillna(MISSING_LABEL).value_counts().head(8).index
                drawn[color] = drawn[color].fillna(MISSING_LABEL).where(
                    drawn[color].fillna(MISSING_LABEL).isin(keep), "Other")
            fig = px.scatter(drawn, x=x, y=y, color=color, opacity=0.65,
                             color_discrete_sequence=PALETTE)
            fig.update_traces(marker=dict(size=7))
            if not color:
                fig.update_traces(marker=dict(color=PRIMARY, size=7))
            if show_trend and len(plot) >= 5 and np.isfinite(r):
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    slope, intercept = np.polyfit(xv, yv, 1)
                xs = np.array([xv.min(), xv.max()])
                fig.add_trace(go.Scatter(x=xs, y=slope * xs + intercept, mode="lines",
                                         name="Linear fit", hoverinfo="skip",
                                         line=dict(color=NEGATIVE, dash="dash", width=2)))
            sub = f"{len(plot):,} records with valid values"
            if len(plot) > MAX_SCATTER_POINTS:
                sub += f" Â· {MAX_SCATTER_POINTS:,} randomly sampled points drawn"
            style_figure(fig, f"{y} vs {x}", legend=bool(color) or show_trend, subtitle=sub)
            fig.update_xaxes(title=x)
            fig.update_yaxes(title=y)
            show_chart(fig, ctx.key("r_scatter"))

            k1, k2, k3 = st.columns(3)
            k1.metric("Pearson r", f"{r:.3f}" if np.isfinite(r) else "n/a")
            k2.metric("Spearman Ï", f"{rho:.3f}" if np.isfinite(rho) else "n/a")
            k3.metric("Paired records", f"{len(plot):,}")
            if np.isfinite(r):
                direction = "positive" if r > 0 else "negative"
                st.markdown(
                    f"- The linear relationship between **{_md(x)}** and **{_md(y)}** is "
                    f"**{strength_label(r)} and {direction}** (r = {r:.2f}).\n"
                    "- Pearson r is sensitive to outliers; Spearman Ï checks whether the *ranking* "
                    "relationship agrees."
                )
            else:
                st.info("A correlation cannot be computed because one column has no variation.")
            if len(plot) < 30:
                st.warning("Small sample: correlations from fewer than 30 records are unreliable.")
    st.caption("Correlation does not establish causation. A strong association can be caused by a "
               "third factor, by chance, or by how the data was collected.")

    st.divider()
    st.markdown("**Correlation matrix**")
    default_cols = nums[:12]
    chosen = st.multiselect("Numeric columns to include", nums, default=default_cols,
                            key=ctx.key("r_heat_cols"))
    usable = [c for c in chosen if df[c].nunique(dropna=True) > 1]
    skipped = [c for c in chosen if c not in usable]
    if skipped:
        st.caption("Skipped (no variation): " + ", ".join(skipped))
    if len(usable) < 2:
        st.info("Select at least two numeric columns that vary.")
        return
    corr = df[usable].corr(min_periods=3)
    n = len(usable)
    fig = go.Figure(
        go.Heatmap(
            z=corr.values, x=usable, y=usable, zmin=-1, zmax=1, colorscale=DIVERGING,
            texttemplate="%{z:.2f}" if n <= 12 else None,
            hovertemplate="%{y} vs %{x}<br>r = %{z:.2f}<extra></extra>",
            colorbar=dict(title="r"),
        )
    )
    style_figure(fig, "Correlation between numeric columns", height=max(420, 42 * n + 140),
                 subtitle="Pearson r, pairwise complete observations")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(tickangle=-35)
    show_chart(fig, ctx.key("r_heat"))

    pairs = []
    for i, a in enumerate(usable):
        for b in usable[i + 1:]:
            v = corr.loc[a, b]
            if pd.notna(v):
                pairs.append((a, b, float(v)))
    pairs.sort(key=lambda t: -abs(t[2]))
    if pairs:
        table = pd.DataFrame(
            [{"Column A": a, "Column B": b, "Pearson r": round(v, 3), "Strength": strength_label(v)}
             for a, b, v in pairs[:10]]
        )
        st.markdown("**Strongest pairs**")
        show_table(table)
        strong = [p for p in pairs if abs(p[2]) >= 0.5]
        if not strong:
            st.caption("No pair reaches |r| â‰¥ 0.5 in the selected columns.")


# --------------------------------------------------------------------------- #
# Section E - Distribution analysis
# --------------------------------------------------------------------------- #
def render_distribution(ctx: Ctx) -> None:
    info, df = ctx.info, ctx.df
    nums = [c for c in info.numeric_ordered if df[c].notna().any()]
    if not nums:
        st.info("Distribution analysis needs at least one numeric column with valid values.")
        return

    default_idx = nums.index(ctx.measure) if ctx.measure in nums else 0
    c1, c2, c3 = st.columns(3)
    col = c1.selectbox("Numeric column", nums, index=default_idx, key=ctx.key("d_col"))
    group_opts = [NO_CHOICE] + groupable_dims(info, 2, 12)
    group_choice = c2.selectbox("Group by (optional)", group_opts, key=ctx.key("d_group"))
    group = None if group_choice == NO_CHOICE else group_choice
    bins = c3.slider("Histogram bins", 5, 100, 30, key=ctx.key("d_bins"))

    cols = [col] + ([group] if group else [])
    data = df[cols].copy()
    if group:
        data[group] = data[group].fillna(MISSING_LABEL)
    data = data.dropna(subset=[col])
    if data.empty:
        st.warning("No valid values in the current selection.")
        return

    drawn = _sample(data, MAX_DIST_POINTS)
    if len(data) > MAX_DIST_POINTS:
        st.caption(f"Charts use a random sample of {MAX_DIST_POINTS:,} records; statistics use all "
                   f"{len(data):,}.")

    left, right = st.columns(2)
    with left:
        show_chart(histogram_figure(drawn, col, group, bins), ctx.key("d_hist"))
    with right:
        show_chart(box_figure(drawn, col, group), ctx.key("d_box"))

    st.markdown("**Distribution statistics**")
    rows = []
    if group:
        for g, part in data.groupby(group, sort=True):
            stats = describe_series(part[col])
            if stats:
                rows.append({group: g, **stats})
    else:
        stats = describe_series(data[col])
        if stats:
            rows.append({"Group": "All records", **stats})
    table = pd.DataFrame(rows)
    show_table(table.round(4))
    st.download_button("Download distribution statistics (CSV)", table.to_csv(index=False).encode("utf-8"),
                       file_name="distribution_statistics.csv", mime="text/csv", key=ctx.key("d_dl"))

    overall = describe_series(data[col])
    obs = [f"Median **{format_number(overall['Median'])}**, middle 50% of values between "
           f"{format_number(overall['Q1'])} and {format_number(overall['Q3'])}; "
           f"range {format_number(overall['Min'])} to {format_number(overall['Max'])}."]
    n_out = overall["Outliers (1.5Ã—IQR rule)"]
    if n_out:
        obs.append(f"{n_out:,} values ({100 * n_out / overall['Count']:.1f}%) fall outside the 1.5Ã—IQR "
                   "fences. Outliers are not necessarily errors - they may be legitimate large or "
                   "small transactions, so investigate before removing them.")
    else:
        obs.append("No values fall outside the 1.5Ã—IQR fences.")
    show_observations(obs)


# --------------------------------------------------------------------------- #
# Section F - Data quality
# --------------------------------------------------------------------------- #
def render_quality(ctx: Ctx) -> None:
    info = ctx.info
    q = info.quality
    st.caption("Quality metrics describe the full dataset passed to the dashboard (filters do not apply).")
    cells = max(info.n_rows * info.n_cols, 1)
    kpi_cards(
        [
            ("Rows", f"{info.n_rows:,}", ""),
            ("Columns", f"{info.n_cols:,}", ""),
            ("Missing cells", f"{info.total_missing:,}", f"{100 * info.total_missing / cells:.1f}% of cells"),
            ("Duplicate rows", f"{info.duplicate_rows:,}",
             f"{100 * info.duplicate_rows / max(info.n_rows, 1):.1f}% of rows"),
            ("Empty columns", f"{len(info.empty):,}", ""),
        ]
    )

    warnings_list = []
    if info.empty:
        warnings_list.append("Entirely empty columns: " + ", ".join(info.empty))
    if info.constant:
        warnings_list.append("Columns with a single constant value: " + ", ".join(info.constant))
    high = q[q["Missing %"] >= 30]["Column"].tolist() if not q.empty else []
    if high:
        warnings_list.append("Columns with 30% or more missing values: " + ", ".join(high))
    for c, k in info.invalid_values.items():
        warnings_list.append(f"'{c}': {k:,} entries could not be parsed and are ignored in calculations.")
    if info.parsed_from_text:
        warnings_list.append("Detected numbers/dates stored as text in: " + ", ".join(info.parsed_from_text))
    if info.duplicate_rows:
        warnings_list.append(f"{info.duplicate_rows:,} duplicate rows are present.")
    if warnings_list:
        st.warning("**Quality warnings**\n\n" + "\n".join(f"- {w}" for w in warnings_list))
    else:
        st.success("No quality warnings were detected.")

    miss = q[q["Missing"] > 0].sort_values("Missing %", ascending=False).head(20)
    if miss.empty:
        st.success("No missing values in any column.")
    else:
        fig = go.Figure(
            go.Bar(
                x=miss["Missing %"], y=_short_labels(miss["Column"]), orientation="h",
                marker=dict(color=[NEGATIVE if v >= 50 else PRIMARY for v in miss["Missing %"]]),
                text=[f"{v:.1f}%" for v in miss["Missing %"]], textposition="outside", cliponaxis=False,
                customdata=[[c, int(m)] for c, m in zip(miss["Column"], miss["Missing"])],
                hovertemplate="<b>%{customdata[0]}</b><br>Missing: %{x:.1f}% "
                              "(%{customdata[1]:,} rows)<extra></extra>",
            )
        )
        style_figure(fig, "Missing values by column", height=max(300, 34 * len(miss) + 120),
                     subtitle="Red = at least 50% missing" if (miss["Missing %"] >= 50).any() else None)
        fig.update_yaxes(autorange="reversed", showgrid=False)
        fig.update_xaxes(showgrid=True, gridcolor=GRID, title="Missing (%)",
                         range=[0, max(100, miss["Missing %"].max() * 1.1)])
        show_chart(fig, ctx.key("q_chart"))

    st.markdown("**Column profile**")
    show_table(q)

    summary = pd.DataFrame(
        {
            "Metric": ["Rows", "Columns", "Missing cells", "Missing cells (%)", "Duplicate rows",
                       "Empty columns", "Numeric columns", "Categorical columns", "Boolean columns",
                       "Datetime columns"],
            "Value": [info.n_rows, info.n_cols, info.total_missing,
                      round(100 * info.total_missing / cells, 2), info.duplicate_rows,
                      len(info.empty), len(info.numeric), len(info.categorical),
                      len(info.boolean), len(info.datetime)],
        }
    )
    d1, d2 = st.columns(2)
    d1.download_button("Download column quality report (CSV)", q.to_csv(index=False).encode("utf-8"),
                       file_name="data_quality_columns.csv", mime="text/csv", key=ctx.key("q_dl1"))
    d2.download_button("Download dataset summary (CSV)", summary.to_csv(index=False).encode("utf-8"),
                       file_name="data_quality_summary.csv", mime="text/csv", key=ctx.key("q_dl2"))


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def _signature(df: pd.DataFrame) -> str:
    """Stable id for widget keys. Includes a content fingerprint so two datasets with
    the same schema and row count but different values never share widget state."""
    raw = "|".join(map(str, df.columns)) + f"#{df.shape[0]}x{df.shape[1]}"
    try:
        edge = pd.concat([df.head(100), df.tail(100)]).astype(str)
        raw += "#" + str(int(pd.util.hash_pandas_object(edge, index=False).sum()))
    except Exception:  # unusual cell types: fall back to schema + shape only
        pass
    return hashlib.md5(raw.encode("utf-8", "ignore")).hexdigest()[:8]


def _render(df: pd.DataFrame) -> None:
    work, info = get_prepared(df)
    ctx = render_controls(work, info, _signature(df))
    if len(ctx.df) == 0:
        st.warning("No records match the current filters. Adjust or clear the filters above.")
        return

    tabs = st.tabs(
        ["Executive overview", "Trend analysis", "Category & segment",
         "Relationships & drivers", "Distributions", "Data quality"]
    )
    for tab, fn in zip(
        tabs,
        [render_overview, render_trend, render_category, render_relationships,
         render_distribution, render_quality],
    ):
        with tab:
            try:
                fn(ctx)
            except Exception as exc:  # keep other sections usable
                st.error(f"This section could not be rendered: {exc}")


def render_data_quality(df: pd.DataFrame) -> None:
    """Render only the data-quality section (used by the Data Quality page)."""
    if not isinstance(df, pd.DataFrame) or df.shape[1] == 0 or len(df) == 0:
        st.info("The dataset is empty, so there is nothing to assess yet.")
        return
    try:
        work, info = get_prepared(df)
        ctx = Ctx(_signature(df), info, work, work, None, "count", None, 10, False)
        render_quality(ctx)
    except Exception as exc:
        st.error(f"The quality report could not be rendered: {exc}")


def render_visualization(df: pd.DataFrame) -> None:
    """Render the analytics dashboard for ``df`` (the cleaned DataFrame)."""
    if not isinstance(df, pd.DataFrame) or df.shape[1] == 0 or len(df) == 0:
        st.info("The dataset is empty, so there is nothing to visualise yet.")
        return
    try:
        _render(df)
    except Exception as exc:
        st.error(f"The dashboard could not be rendered: {exc}")
        with st.expander("Technical details"):
            st.exception(exc)
