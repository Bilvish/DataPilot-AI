"""
ui_theme.py
===========
Shared look-and-feel for DataPilot AI: one stylesheet plus small, reusable UI helpers.

The stylesheet is deliberately narrow: it styles metrics, bordered containers,
the sidebar, tabs, buttons, and the SQL editor (via its widget key class). It does
not hide or re-position any native Streamlit control.
"""

from __future__ import annotations

import html
from typing import Iterable, Optional

import streamlit as st

ACCENT = "#4F46E5"
INK = "#0F172A"
MUTED = "#475569"
BORDER = "#E2E8F0"
SURFACE = "#F6F7FB"

# status -> (label colour, background colour). All pairs meet WCAG AA contrast on their background.
_STATUS = {
    "neutral": ("#334155", "#EEF2F7"),
    "info": ("#3730A3", "#E0E7FF"),
    "success": ("#166534", "#DCFCE7"),
    "warning": ("#92400E", "#FEF3C7"),
    "error": ("#991B1B", "#FEE2E2"),
}

CSS = f"""
<style>
:root {{ --if-accent: {ACCENT}; --if-ink: {INK}; --if-muted: {MUTED}; --if-border: {BORDER}; }}

/* Layout: consistent content width and breathing room */
.block-container {{ max-width: 1280px; padding-top: 2rem; padding-bottom: 4rem; }}

/* Typography */
h1, h2, h3 {{ letter-spacing: -0.01em; color: var(--if-ink); }}
h2 {{ font-size: 1.35rem; }}
h3 {{ font-size: 1.1rem; }}

/* Page header */
.if-header {{ display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between;
  gap: 12px; padding-bottom: 14px; margin-bottom: 18px; border-bottom: 1px solid var(--if-border); }}
.if-header h1 {{ font-size: 1.75rem; line-height: 1.2; margin: 0; padding: 0; }}
.if-header p {{ margin: 4px 0 0 0; color: var(--if-muted); font-size: 0.95rem; }}
.if-chips {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }}
.if-chip {{ display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px;
  font-size: 0.8rem; font-weight: 600; white-space: nowrap; max-width: 320px; overflow: hidden; text-overflow: ellipsis; }}
.if-chip.file {{ background: #fff; color: var(--if-ink); border: 1px solid var(--if-border); font-weight: 500; }}
.if-dot {{ width: 7px; height: 7px; border-radius: 50%; background: currentColor; display: inline-block; }}

/* Section titles */
.if-section {{ margin: 22px 0 8px 0; }}
.if-section h2 {{ margin: 0; padding: 0; font-size: 1.15rem; }}
.if-section p {{ margin: 2px 0 0 0; color: var(--if-muted); font-size: 0.9rem; }}

/* Metrics and bordered containers act as cards */
[data-testid="stVerticalBlockBorderWrapper"] {{ border-radius: 12px; border-color: var(--if-border);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }}
[data-testid="stMetric"] label, [data-testid="stMetricLabel"] {{ color: var(--if-muted); font-size: 0.8rem; font-weight: 600; }}
[data-testid="stMetricValue"] {{ font-size: 1.6rem; font-weight: 700; color: var(--if-ink); }}

/* Sidebar */
[data-testid="stSidebar"] {{ border-right: 1px solid var(--if-border); }}
.if-side-card {{ background: #fff; border: 1px solid var(--if-border); border-radius: 10px; padding: 10px 12px;
  font-size: 0.85rem; color: var(--if-ink); line-height: 1.5; }}
.if-side-card b {{ display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.if-side-card span {{ color: var(--if-muted); }}
.if-footer {{ color: var(--if-muted); font-size: 0.75rem; padding-top: 12px; border-top: 1px solid var(--if-border); margin-top: 16px; }}

/* Tabs */
.stTabs [data-baseweb="tab"] {{ font-weight: 600; }}

/* Buttons */
.stButton > button, .stDownloadButton > button {{ border-radius: 8px; font-weight: 600; }}

/* Empty / welcome states */
.if-empty {{ border: 1px dashed #CBD5E1; background: {SURFACE}; border-radius: 14px; padding: 28px 24px; text-align: left; }}
.if-empty h3 {{ margin: 0 0 6px 0; }}
.if-empty p {{ color: var(--if-muted); margin: 0 0 4px 0; }}
.if-steps {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-top: 14px; }}
.if-step {{ background: #fff; border: 1px solid var(--if-border); border-radius: 12px; padding: 12px 14px; }}
.if-step .n {{ display: inline-flex; width: 22px; height: 22px; border-radius: 50%; background: var(--if-accent);
  color: #fff; font-size: 0.75rem; font-weight: 700; align-items: center; justify-content: center; margin-bottom: 6px; }}
.if-step b {{ display: block; color: var(--if-ink); }}
.if-step span {{ color: var(--if-muted); font-size: 0.85rem; }}
.if-step.done {{ border-color: #86EFAC; }}
.if-step.done .n {{ background: #166534; }}

/* SQL editor: monospace, scoped to the widget key */
.st-key-sql_query_editor textarea {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  font-size: 0.9rem; line-height: 1.55; background: #0F172A; color: #E2E8F0; border-radius: 10px; }}
.st-key-sql_query_editor textarea:focus {{ box-shadow: 0 0 0 2px #A5B4FC; }}

/* Keyboard focus visibility */
button:focus-visible, [role="tab"]:focus-visible {{ outline: 2px solid var(--if-accent); outline-offset: 2px; }}

/* Small screens */
@media (max-width: 640px) {{
  .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
  .if-header h1 {{ font-size: 1.4rem; }}
}}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def status_chip(label: str, kind: str = "neutral") -> str:
    fg, bg = _STATUS.get(kind, _STATUS["neutral"])
    return (f'<span class="if-chip" style="color:{fg};background:{bg}">'
            f'<span class="if-dot"></span>{html.escape(label)}</span>')


def page_header(title: str, subtitle: str, *, dataset_name: Optional[str] = None,
                status: Optional[tuple[str, str]] = None) -> None:
    """Top-of-page header: title, subtitle, dataset name and processing state."""
    chips = []
    if dataset_name:
        chips.append(f'<span class="if-chip file" title="{html.escape(dataset_name)}">{html.escape(dataset_name)}</span>')
    if status:
        chips.append(status_chip(*status))
    st.markdown(
        f'<div class="if-header"><div><h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p></div>'
        f'<div class="if-chips">{"".join(chips)}</div></div>',
        unsafe_allow_html=True,
    )


def section(title: str, caption: Optional[str] = None) -> None:
    cap = f"<p>{html.escape(caption)}</p>" if caption else ""
    st.markdown(f'<div class="if-section"><h2>{html.escape(title)}</h2>{cap}</div>', unsafe_allow_html=True)


def metric_row(items: Iterable[tuple[str, str, Optional[str]]]) -> None:
    """Row of bordered metric cards: (label, value, caption)."""
    items = list(items)
    for col, (label, value, caption) in zip(st.columns(len(items)), items):
        with col:
            with st.container(border=True):
                st.metric(label, value)
                st.caption(caption or " ")


def steps(items: list[tuple[str, str, bool]]) -> None:
    """Numbered workflow cards: (title, description, done)."""
    cards = "".join(
        f'<div class="if-step{" done" if done else ""}"><div class="n">{"✓" if done else i}</div>'
        f"<b>{html.escape(t)}</b><span>{html.escape(d)}</span></div>"
        for i, (t, d, done) in enumerate(items, 1)
    )
    st.markdown(f'<div class="if-steps">{cards}</div>', unsafe_allow_html=True)


def empty_state(title: str, body: str) -> None:
    st.markdown(f'<div class="if-empty"><h3>{html.escape(title)}</h3><p>{html.escape(body)}</p></div>',
                unsafe_allow_html=True)


def table(data, height: Optional[int] = None) -> None:
    kwargs = {"hide_index": True, "width": "stretch"}
    if height:
        kwargs["height"] = height
    st.dataframe(data, **kwargs)
