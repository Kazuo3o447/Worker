"""Reusable Streamlit UI components for the Classification Dashboard."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


# ---------------------------------------------------------------------------
# Badges / banners
# ---------------------------------------------------------------------------

def dry_run_badge(is_dry_run: bool) -> None:
    if is_dry_run:
        st.warning("🔵 **DRY RUN** – In diesem Lauf wurden keine Blob-Tags und keine Metadata in Azure geschrieben.")


def error_banner(count: int) -> None:
    if count > 0:
        st.error(f"⚠️ **{count} Fehler** in diesem Lauf. Bitte die Fehler-Seite prüfen.")
    else:
        st.success("✅ Keine Fehler in diesem Lauf.")


def empty_state(message: str) -> None:
    st.info(f"ℹ️ {message}")


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def metric_row(metrics: dict[str, Any], columns: int = 4) -> None:
    """Display a row of st.metric cards, auto-wrapping after *columns* items."""
    items = list(metrics.items())
    for i in range(0, len(items), columns):
        chunk = items[i: i + columns]
        cols = st.columns(len(chunk))
        for col, (label, value) in zip(cols, chunk):
            col.metric(label, value)


# ---------------------------------------------------------------------------
# DataFrame display
# ---------------------------------------------------------------------------

def show_dataframe(
    df: pd.DataFrame,
    height: int = 420,
    hide_index: bool = True,
) -> None:
    if df.empty:
        empty_state("Keine Daten vorhanden.")
    else:
        st.dataframe(df, use_container_width=True, height=height, hide_index=hide_index)


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------

def multiselect_filter(
    df: pd.DataFrame,
    column: str,
    label: str,
    default_all: bool = True,
) -> pd.DataFrame:
    """Render a multiselect widget and return filtered DataFrame."""
    if column not in df.columns or df.empty:
        return df
    options = sorted(df[column].dropna().unique().tolist())
    if not options:
        return df
    selected = st.multiselect(label, options, default=options if default_all else [])
    if selected:
        return df[df[column].isin(selected)]
    return df


def text_search_filter(
    df: pd.DataFrame,
    column: str,
    label: str = "Suche",
) -> pd.DataFrame:
    """Render a text input and return rows where *column* contains the query."""
    if column not in df.columns:
        return df
    query = st.text_input(label, value="")
    if query.strip():
        return df[df[column].str.contains(query.strip(), case=False, na=False)]
    return df


# ---------------------------------------------------------------------------
# Class colour map (for display)
# ---------------------------------------------------------------------------

CLASS_COLOURS: dict[str, str] = {
    "br": "🔴",
    "hr": "🟠",
    "dsgvo": "🔴",
    "finance": "🟡",
    "contract": "🟣",
    "technical": "🔵",
    "unknown": "⚫",
    "unreadable": "⚪",
    "error": "❌",
}


def class_icon(class_label: str) -> str:
    return CLASS_COLOURS.get(class_label, "⚪")
