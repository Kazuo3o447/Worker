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
        st.warning("**[DRY RUN]** – In diesem Lauf wurden keine Blob-Tags und keine Metadata in Azure geschrieben.")


def error_banner(count: int) -> None:
    if count > 0:
        st.error(f"**{count} Fehler** in diesem Lauf. Bitte die Fehler-Seite prüfen.")
    else:
        st.success("Keine Fehler in diesem Lauf.")


def empty_state(message: str) -> None:
    st.info(message)


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
    "br":          "[BR]",
    "hr":          "[HR]",
    "dsgvo":       "[DSGVO]",
    "finance":     "[FIN]",
    "contract":    "[VERT]",
    "technical":   "[TECH]",
    "unknown":     "[?]",
    "unreadable":  "[-]",
    "error":       "[ERR]",
}


def class_icon(class_label: str) -> str:
    return CLASS_COLOURS.get(class_label, "⚪")


# ---------------------------------------------------------------------------
# AdminLTE-inspired KPI / Card components
# ---------------------------------------------------------------------------

_HEALTH_LABELS = {"green": "GRÜN", "yellow": "GELB", "red": "ROT"}
_HEALTH_ICONS: dict[str, str] = {}


def kpi_card(title: str, value: Any, subtitle: str | None = None) -> None:
    """Render a single KPI metric card using st.metric."""
    st.metric(label=title, value=str(value), help=subtitle)


def status_badge(label: str, status: str) -> None:
    """Render a coloured inline badge using st.success/warning/error."""
    icon = _HEALTH_ICONS.get(status, "")
    text = f"{icon} **{label}**".lstrip()
    if status == "green":
        st.success(text)
    elif status == "yellow":
        st.warning(text)
    elif status == "red":
        st.error(text)
    else:
        st.info(text)


def health_banner(status: str, message: str = "") -> None:
    """Full-width health banner (GRÜN / GELB / ROT)."""
    label = _HEALTH_LABELS.get(status, status.upper())
    text = f"**{label}** – {message}" if message else f"**{label}**"
    if status == "green":
        st.success(text)
    elif status == "yellow":
        st.warning(text)
    else:
        st.error(text)


def section_header(title: str, subtitle: str | None = None) -> None:
    """Render a section heading with optional caption."""
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)


def admin_card(title: str, body: str) -> None:
    """Render a titled info card using st.info."""
    st.info(f"**{title}**\n\n{body}")


def risk_card(title: str, count: int, severity: str, recommendation: str) -> None:
    """Render a risk summary card."""
    text = f"**{title}** – Anzahl: {count}\n\n_{recommendation}_"
    if severity == "red":
        st.error(text)
    elif severity == "yellow":
        st.warning(text)
    else:
        st.info(text)


def token_summary_card(summary: dict[str, Any]) -> None:
    """Render a token summary block from run-summary.json fields."""
    factor = summary.get("ai_token_estimation_safety_factor", "-")
    raw    = int(summary.get("ai_estimated_tokens_raw_total", 0))
    buf    = int(summary.get("ai_estimated_tokens_buffered_total", 0))
    real   = int(summary.get("ai_total_tokens", summary.get("ai_total_tokens_sum", 0)))
    prompt = int(summary.get("ai_prompt_tokens_total", 0))
    comp_t = int(summary.get("ai_completion_tokens_total", 0))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prompt-Tokens (real)", f"{prompt:,}")
    c2.metric("Completion-Tokens", f"{comp_t:,}")
    c3.metric("Gesamt-Tokens (real)", f"{real:,}")
    c4.metric("Safety Factor", str(factor))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Estimated Raw", f"{raw:,}")
    c6.metric("Estimated Buffered", f"{buf:,}")
    if real > 0 and buf > 0:
        diff_pct = (buf - real) / real * 100
        sign = "+" if diff_pct >= 0 else ""
        c7.metric("Buffered vs. Real", f"{sign}{diff_pct:.1f}%",
                  help="Positiv = Puffer ausreichend. Negativ = Puffer zu niedrig.")
    else:
        c7.metric("Buffered vs. Real", "n/a")
    source = summary.get("ai_token_source_breakdown", "-")
    c8.metric("Token-Quelle", source)


def extraction_summary_card(summary: dict[str, Any]) -> None:
    """Render an extraction summary block from run-summary.json fields."""
    method_counts = summary.get("extraction_method_counts", "-")
    success       = int(summary.get("extraction_success_count", 0))
    failed        = int(summary.get("extraction_failed_count", summary.get("extraction_error_count", 0)))
    no_text       = int(summary.get("extraction_no_text_count", 0))
    tool_missing  = int(summary.get("extraction_tool_missing_count", 0))
    chars_total   = int(summary.get("extracted_chars_total", 0))

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Extraktion erfolgreich", success)
    c2.metric("Extraktion fehlgeschlagen", failed)
    c3.metric("Extrahierte Zeichen", f"{chars_total:,}")
    c4.metric("Extraktoren", method_counts)

    if no_text > 0 or tool_missing > 0:
        c5, c6, _, _ = st.columns(4)
        c5.metric("Kein Text", no_text)
        c6.metric("Tool fehlt", tool_missing)


def ai_summary_card(summary: dict[str, Any]) -> None:
    """Render an AI summary block from run-summary.json fields."""
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("AI Provider", summary.get("ai_provider", "-"))
    c2.metric("AI Model", summary.get("ai_model", "-"))
    c3.metric("AI Prompt Version", summary.get("ai_prompt_version", "-"))
    c4.metric("AI Calls Used", summary.get("ai_calls_used", 0))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("AI Errors", summary.get("ai_errors", 0))
    c6.metric("needs_ai=true", summary.get("needs_ai_count", 0))
    c7.metric("retry_recommended", summary.get("retry_recommended_count", 0))
    c8.metric("budget_exhausted", summary.get("ai_skipped_budget_exhausted_count", 0))


def observability_missing_fields_table(summary: dict[str, Any]) -> None:
    """Render a table of observability fields with present/missing status."""
    import pandas as _pd  # noqa: PLC0415
    FIELDS = [
        ("run_duration_ms",              "Gesamtlaufzeit in ms",                  "duration_seconds",                   "Niedrig"),
        ("blob_processing_duration_ms",  "End-to-End Blob-Dauer (Download+AI+Tag)","",                                  "Mittel"),
        ("download_duration_ms",         "Download-Dauer pro Blob",               "",                                   "Niedrig"),
        ("extraction_duration_ms",       "Extraktion-Dauer pro Blob",             "",                                   "Niedrig"),
        ("report_upload_duration_ms",    "Report-Upload-Dauer",                   "",                                   "Niedrig"),
        ("files_per_hour",               "Durchsatz Dateien/h",                   "throughput_files_per_hour",          "—"),
        ("pdf_pages_processed",          "PDF-Seiten gesehen",                    "",                                   "Mittel"),
        ("validation_success_count",     "Erfolgreiche Tag-Validierungen",        "",                                   "Mittel"),
        ("validation_error_count",       "Fehlgeschlagene Validierungen",         "",                                   "Mittel"),
        ("human_review_required_count",  "Dateien die Human Review brauchen",     "",                                   "Mittel"),
        ("ground_truth_class",           "Echte KI-Accuracy (Ground Truth)",      "",                                   "Hoch (Produktion)"),
    ]
    rows = []
    for field, meaning, alt_key, prio in FIELDS:
        present = bool(summary.get(field) or (alt_key and summary.get(alt_key)))
        rows.append({
            "Feld": field,
            "Status": "vorhanden" if present else "fehlt",
            "Bedeutung": meaning,
            "Priorität": prio,
        })
    df = _pd.DataFrame(rows)
    show_dataframe(df, height=360)
