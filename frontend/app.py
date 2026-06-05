"""GEMA Storage Classification Pilot – Andre3000 Admin-Cockpit.

10 Bereiche:  Cockpit | Runs | Run Detail | Klassifizierung | KI Readiness |
              Dateien & Dateitypen | Fehler & Risiken | Reports & Exporte |
              Konfiguration | Run Commands

Read-only: keine Blob-Schreiboperationen, keine AI-Aufrufe, keine Worker-Starts.
Starten: streamlit run frontend/app.py  (oder docker compose up dashboard)
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import threading
import time

# Ensure the parent directory (storage-classification-pilot) is in sys.path
_frontend_dir = pathlib.Path(__file__).resolve().parent
if str(_frontend_dir.parent) not in sys.path:
    sys.path.insert(0, str(_frontend_dir.parent))

import pandas as pd
import streamlit as st

_DEVICE_CODE_MSG_FILE = pathlib.Path(tempfile.gettempdir()) / "azure_device_code.txt"

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Andre3000",
    page_icon="G",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Azure connection (cached)
# ---------------------------------------------------------------------------
try:
    from frontend.config import load_frontend_config
    from frontend.azure_report_repository import AzureReportRepository
except ModuleNotFoundError:
    from config import load_frontend_config  # type: ignore[no-redef]
    from azure_report_repository import AzureReportRepository  # type: ignore[no-redef]


@st.cache_resource
def _get_repo() -> AzureReportRepository:
    cfg = load_frontend_config()
    return AzureReportRepository(cfg)


@st.cache_resource
def _get_auth_state() -> dict:  # type: ignore[type-arg]
    """Shared auth state – created once, lives for the lifetime of the server."""
    return {"event": threading.Event(), "ok": None, "err": "", "started": False}


def _ensure_auth_thread() -> None:
    """Launch the Azure auth check exactly once in a background thread."""
    state = _get_auth_state()
    if state["started"]:
        return
    state["started"] = True

    def _run() -> None:
        try:
            r = _get_repo()
            ok, err = r.is_available()
            state["ok"] = ok
            state["err"] = err
        except Exception as exc:  # noqa: BLE001
            state["ok"] = False
            state["err"] = str(exc)
        finally:
            _DEVICE_CODE_MSG_FILE.unlink(missing_ok=True)
            state["event"].set()

    threading.Thread(target=_run, daemon=True).start()


_ensure_auth_thread()
_auth = _get_auth_state()

if not _auth["event"].is_set():
    st.title("Andre3000")
    if _DEVICE_CODE_MSG_FILE.exists():
        st.info(_DEVICE_CODE_MSG_FILE.read_text(encoding="utf-8"))
    else:
        st.info("Verbinde mit Azure Blob Storage ...")
    _wait = st.session_state.get("_auth_wait", 0) + 1
    st.session_state["_auth_wait"] = _wait
    if _wait > 300:  # 5-Minuten-Timeout
        st.error("Timeout: Azure-Verbindung fehlgeschlagen nach 5 Minuten.")
        st.stop()
    time.sleep(1)
    st.rerun()

if _auth["ok"] is False:
    st.error(
        "**Azure Blob Storage nicht erreichbar.**\n\n"
        f"Fehler: `{_auth['err']}`\n\n"
        "Prüfe AUTH_MODE, AZURE_STORAGE_ACCOUNT und REPORT_CONTAINER."
    )
    st.stop()

repo = _get_repo()

try:
    import components as comp
except ModuleNotFoundError:
    from frontend import components as comp  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("Andre3000")
st.sidebar.caption(f"Worker Version: {repo.config.worker_version}")
st.sidebar.markdown(
    f"**Storage:** `{repo.config.storage_account}`  \n"
    f"**Source:** `{repo.config.source_container}`  \n"
    f"**Reports:** `{repo.config.report_container}`"
)
st.sidebar.markdown("---")

runs = repo.list_run_ids()

if not runs:
    st.warning(
        "**Keine Runs gefunden.**\n\n"
        f"Reports-Container: `{repo.config.report_container}` · "
        f"Prefix: `{repo.config.worker_version}/`\n\n"
        "Starte zuerst den Worker:"
    )
    st.code("docker compose run --rm worker --mode classify --max-files 50 --dry-run")
    st.stop()

PAGES = [
    "Cockpit",
    "Runs",
    "Run Detail",
    "Klassifizierung",
    "KI Readiness",
    "Dateien & Dateitypen",
    "Fehler & Risiken",
    "Reports & Exporte",
    "Konfiguration",
    "Run Commands",
]

page = st.sidebar.radio("Navigation", PAGES, label_visibility="collapsed")

# Run selector (relevant for detail pages)
RUN_PAGES = {"Run Detail", "Klassifizierung", "KI Readiness",
             "Dateien & Dateitypen", "Fehler & Risiken", "Reports & Exporte"}

if page in RUN_PAGES:
    st.sidebar.markdown("---")
    selected_run = st.sidebar.selectbox(
        "Run auswählen",
        runs,
        index=0,
        help="Neueste Runs stehen oben.",
    )
    st.sidebar.caption(f"`{selected_run}`")
else:
    selected_run = runs[0]

st.sidebar.markdown("---")
ai_status = "aktiviert" if repo.config.enable_ai else "deaktiviert"
st.sidebar.caption(f"AI: {ai_status} · {repo.config.ai_provider}")


# ---------------------------------------------------------------------------
# Caching helpers
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def _summary(run_id: str) -> dict:
    return repo.get_run_summary(run_id)


@st.cache_data(ttl=60)
def _admin_report(run_id: str) -> dict:
    return repo.get_report_json(run_id, "admin-report.json")


@st.cache_data(ttl=60)
def _csv(run_id: str, filename: str) -> pd.DataFrame:
    return repo.get_csv(run_id, filename)


@st.cache_data(ttl=60)
def _events(run_id: str) -> pd.DataFrame:
    return repo.get_events(run_id)


@st.cache_data(ttl=120)
def _all_summaries() -> list[dict]:
    """Load run-summary.json for all runs (cached 2 min)."""
    result = []
    for run_id in runs:
        s = _summary(run_id)
        s["_run_id"] = run_id
        result.append(s)
    return result


# ---------------------------------------------------------------------------
# Health helpers
# ---------------------------------------------------------------------------

def _health(summary: dict) -> str:
    """Return 'red' | 'yellow' | 'green'."""
    if int(summary.get("files_error", 0)) > 0:
        return "red"
    if int(summary.get("files_unknown", 0)) > 0 or int(summary.get("ai_candidates", 0)) > 0:
        return "yellow"
    return "green"


def _render_health(summary: dict) -> None:
    h = _health(summary)
    if h == "red":
        st.error("Rot – Fehler vorhanden. Eingriff erforderlich.")
    elif h == "yellow":
        st.warning("Gelb – Offene Punkte: Unknown-Dateien oder KI-Kandidaten vorhanden.")
    else:
        st.success("Grün – Keine Fehler, keine offenen Risiken.")


def _next_action(summary: dict, admin: dict) -> str:
    actions = admin.get("next_actions", [])
    if actions:
        return actions[0]
    errors = int(summary.get("files_error", 0))
    if errors > 0:
        return f"Fehler prüfen: {errors} Dateien konnten nicht verarbeitet werden"
    unknown = int(summary.get("files_unknown", 0))
    ai_cand = int(summary.get("ai_candidates", 0))
    if unknown > 0 and not summary.get("enable_ai", False):
        return f"KI-Dry-Run vorbereiten: {unknown} unknown-Dateien vorhanden"
    if ai_cand > 0:
        return f"KI-Kandidaten prüfen: {ai_cand} Dateien für KI-Klassifizierung bereit"
    return "Kein Handlungsbedarf – Lauf war erfolgreich."


def compile_pdf_on_the_fly_frontend(run_id: str) -> bytes | None:
    """Dynamically generate the beautifully formatted PDF report with landscape and pie charts from the current run data."""
    summary_dict = _summary(run_id)
    if not summary_dict:
        return None
    details_df = _csv(run_id, "classification-details.csv")
    
    try:
        from app.models import RunSummary, ClassificationResult
        from app.reports import _build_admin_report_pdf
        
        summary_obj = RunSummary(
            run_id=summary_dict.get("run_id", run_id),
            mode=summary_dict.get("mode", ""),
            status=summary_dict.get("status", ""),
            worker_name=summary_dict.get("worker_name", "Andre3000"),
            worker_version=summary_dict.get("worker_version", ""),
            storage_account=summary_dict.get("storage_account", ""),
            source_container=summary_dict.get("source_container", ""),
            report_container=summary_dict.get("report_container", ""),
            prefix=summary_dict.get("prefix", ""),
            dry_run=bool(summary_dict.get("dry_run", False)),
            force=bool(summary_dict.get("force", False)),
            max_files=int(summary_dict.get("max_files", 0)),
            started_at=summary_dict.get("started_at", ""),
            finished_at=summary_dict.get("finished_at", ""),
            files_seen=int(summary_dict.get("files_seen", 0)),
            files_untagged=int(summary_dict.get("files_untagged", 0)),
            files_skipped=int(summary_dict.get("files_skipped", 0)),
            files_processed=int(summary_dict.get("files_processed", 0)),
            files_classified=int(summary_dict.get("files_classified", 0)),
            files_unknown=int(summary_dict.get("files_unknown", 0)),
            files_error=int(summary_dict.get("files_error", 0)),
            bytes_seen=int(summary_dict.get("bytes_seen", 0)),
            bytes_processed=int(summary_dict.get("bytes_processed", 0)),
            duration_seconds=float(summary_dict.get("duration_seconds", 0.0)),
            enable_ai=bool(summary_dict.get("enable_ai", False)),
            ai_provider=summary_dict.get("ai_provider", "none"),
            ai_max_calls_per_run=int(summary_dict.get("ai_max_calls_per_run", 0)),
            ai_calls_used=int(summary_dict.get("ai_calls_used", 0)),
            ai_calls_skipped=int(summary_dict.get("ai_calls_skipped", 0)),
            ai_errors=int(summary_dict.get("ai_errors", 0)),
            ai_candidates=int(summary_dict.get("ai_candidates", 0))
        )
        
        results_list = []
        if not details_df.empty:
            for _, row in details_df.iterrows():
                # Helper to safecast string values from dataframe
                def _val_str(col: str, default: str = "") -> str:
                    v = row.get(col)
                    if pd.isna(v) or v is None:
                        return default
                    return str(v).strip()
                
                # Check confidence float conversion to clean numeric string (eg. 85.0 -> 85)
                raw_conf = row.get("confidence")
                conf_str = ""
                if pd.notna(raw_conf) and raw_conf is not None:
                    try:
                        conf_str = str(int(float(raw_conf)))
                    except Exception:
                        conf_str = str(raw_conf).strip()
                
                results_list.append(ClassificationResult(
                    run_id=_val_str("run_id", run_id),
                    processed_at=_val_str("processed_at"),
                    blob_name=_val_str("blob_name"),
                    container=_val_str("container"),
                    size_bytes=int(row.get("size_bytes", 0) if pd.notna(row.get("size_bytes")) else 0),
                    extension=_val_str("extension"),
                    last_modified=_val_str("last_modified"),
                    etag=_val_str("etag"),
                    existing_status_before=_val_str("existing_status_before"),
                    action=_val_str("action"),
                    status=_val_str("status"),
                    class_label=_val_str("class", _val_str("class_label")),
                    dsgvo=_val_str("dsgvo", "false").lower(),
                    archive_candidate=_val_str("archive_candidate", "false").lower(),
                    confidence=conf_str,
                    readable=_val_str("readable", "true"),
                    llm_used=_val_str("llm_used", "false"),
                    reason_code=_val_str("reason_code"),
                    error_reason=_val_str("error_reason"),
                    metadata_written=_val_str("metadata_written", "false"),
                    tags_written=_val_str("tags_written", "false"),
                    duration_ms=int(row.get("duration_ms", 0) if pd.notna(row.get("duration_ms")) else 0),
                    needs_ai=str(row.get("needs_ai", "false")).lower() == "true"
                ))
        return _build_admin_report_pdf(summary_obj, results_list)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Page: Übersicht
# ---------------------------------------------------------------------------

def page_overview(run_id: str) -> None:
    st.header("Lauf-Übersicht")
    summary = _summary(run_id)
    if not summary:
        comp.empty_state("run-summary.json nicht gefunden.")
        return

    comp.dry_run_badge(summary.get("dry_run", False))

    # Key metrics
    comp.metric_row({
        "Mode": summary.get("mode", "-"),
        "Worker Version": summary.get("worker_version", "-"),
        "Started": str(summary.get("started_at", "-"))[:19].replace("T", " "),
        "Dauer (s)": f"{summary.get('duration_seconds', 0):.1f}",
    })
    st.divider()
    comp.metric_row({
        "Gesehen": summary.get("files_seen", 0),
        "Ungetaggt": summary.get("files_untagged", 0),
        "Verarbeitet": summary.get("files_processed", 0),
        "Klassifiziert": summary.get("files_classified", 0),
    })
    comp.metric_row({
        "Unknown": summary.get("files_unknown", 0),
        "Fehler": summary.get("files_error", 0),
        "GB verarbeitet": f"{summary.get('gb_processed', 0):.4f}",
        "Übersprungen": summary.get("files_skipped", 0),
    })
    comp.metric_row({
        "Durchsatz (Dateien/h)": summary.get("throughput_files_per_hour", 0),
        "Durchsatz (GB/h)": summary.get("throughput_gb_per_hour", 0),
        "KI Kandidaten": summary.get("ai_candidates", 0),
        "KI Aufrufe": summary.get("ai_calls_used", 0),
    })
    st.divider()

    comp.error_banner(int(summary.get("files_error", 0)))

    with st.expander("run-summary.json (vollständig)"):
        st.json(summary)


# ---------------------------------------------------------------------------
# Page: Klassenverteilung
# ---------------------------------------------------------------------------

def page_class_distribution(run_id: str) -> None:
    st.header("Klassenverteilung")
    df = _csv(run_id, "classification-summary.csv")
    if df.empty:
        comp.empty_state("classification-summary.csv nicht gefunden.")
        return

    # Show key/value table
    class_keys = [k for k in df.get("key", pd.Series()).tolist() if str(k).startswith("class_")]
    if class_keys:
        class_df = df[df["key"].isin(class_keys)].copy()
        class_df.columns = ["Klasse", "Anzahl"]
        class_df["Klasse"] = class_df["Klasse"].str.replace("class_", "", regex=False)
        class_df["Anzahl"] = pd.to_numeric(class_df["Anzahl"], errors="coerce").fillna(0).astype(int)
        class_df = class_df.sort_values("Anzahl", ascending=False)

        col1, col2 = st.columns([1, 2])
        with col1:
            st.subheader("Tabelle")
            comp.show_dataframe(class_df, height=300)
        with col2:
            st.subheader("Balkendiagramm")
            if not class_df.empty:
                st.bar_chart(class_df.set_index("Klasse")["Anzahl"])

    st.divider()
    st.subheader("Alle Metriken")
    comp.show_dataframe(df, height=500)


# ---------------------------------------------------------------------------
# Page: Klassifizierungs-Details
# ---------------------------------------------------------------------------

def page_details(run_id: str) -> None:
    st.header("Klassifizierungs-Details")
    df = _csv(run_id, "classification-details.csv")
    if df.empty:
        comp.empty_state("classification-details.csv nicht gefunden oder leer.")
        return

    st.caption(f"{len(df)} Einträge geladen")

    with st.expander("Filter", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            df = comp.multiselect_filter(df, "class", "Klasse")
            df = comp.multiselect_filter(df, "status", "Status")
        with col2:
            df = comp.multiselect_filter(df, "dsgvo", "DSGVO")
            df = comp.multiselect_filter(df, "archive_candidate", "Archiv-Kandidat")
        with col3:
            df = comp.multiselect_filter(df, "llm_used", "LLM genutzt")
            df = comp.multiselect_filter(df, "extension", "Dateiendung")

        if "confidence" in df.columns:
            df["_conf_num"] = pd.to_numeric(df["confidence"], errors="coerce").fillna(0)
            min_conf, max_conf = st.slider("Confidence-Bereich", 0, 100, (0, 100))
            df = df[(df["_conf_num"] >= min_conf) & (df["_conf_num"] <= max_conf)]
            df = df.drop(columns=["_conf_num"])

        df = comp.text_search_filter(df, "blob_name", "Blob-Name enthält")

    st.caption(f"{len(df)} Einträge nach Filter")
    comp.show_dataframe(df, height=480)


# ---------------------------------------------------------------------------
# Page: Fehler
# ---------------------------------------------------------------------------

def page_errors(run_id: str) -> None:
    st.header("Fehler")
    df = _csv(run_id, "classification-errors.csv")

    if df.empty:
        st.success("Keine Fehler in diesem Lauf.")
        return

    st.error(f"**{len(df)} Fehler** gefunden")

    with st.expander("Filter", expanded=False):
        df = comp.multiselect_filter(df, "error_stage", "Fehler-Stufe")
        df = comp.text_search_filter(df, "error_reason", "Fehler-Grund enthält")

    comp.show_dataframe(df, height=450)


# ---------------------------------------------------------------------------
# Page: Ungetaggte Dateien
# ---------------------------------------------------------------------------

def page_untagged(run_id: str) -> None:
    st.header("Ungetaggte Dateien")
    df = _csv(run_id, "untagged-files.csv")

    if df.empty:
        comp.empty_state("untagged-files.csv nicht gefunden oder leer.")
        return

    st.info(f"**{len(df)} ungetaggte / retry-fähige Dateien** in diesem Lauf erkannt.")

    with st.expander("Filter", expanded=False):
        df = comp.multiselect_filter(df, "extension", "Dateiendung")
        df = comp.multiselect_filter(df, "reason", "Grund")

    comp.show_dataframe(df, height=450)


# ---------------------------------------------------------------------------
# Page: Stichproben / Review
# ---------------------------------------------------------------------------

def page_samples(run_id: str) -> None:
    st.header("Stichproben – fachliche Prüfung")
    df = _csv(run_id, "classification-samples.csv")

    if df.empty:
        comp.empty_state("classification-samples.csv nicht gefunden oder leer.")
        return

    groups = sorted(df["sample_group"].unique().tolist()) if "sample_group" in df.columns else []
    if not groups:
        comp.show_dataframe(df)
        return

    selected_groups = st.multiselect(
        "Klassen anzeigen",
        groups,
        default=groups,
        help="Wähle die Klassen, deren Stichproben angezeigt werden sollen.",
    )

    for grp in selected_groups:
        grp_df = df[df["sample_group"] == grp]
        with st.expander(f"Klasse: {grp}  ({len(grp_df)} Stichproben)", expanded=grp in ("unknown", "br", "hr", "dsgvo")):
            comp.show_dataframe(grp_df, height=280)


# ---------------------------------------------------------------------------
# Page: Logs
# ---------------------------------------------------------------------------

def page_logs(run_id: str) -> None:
    st.header("Lauf-Events (run-events.jsonl)")
    df = _events(run_id)

    if df.empty:
        comp.empty_state(
            "run-events.jsonl nicht gefunden. "
            "Stelle sicher, dass der Worker die Datei nach Azure hochlädt (UPLOAD_REPORTS=true)."
        )
        return

    st.caption(f"{len(df)} Events geladen")

    with st.expander("Filter", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            df = comp.multiselect_filter(df, "level", "Log-Level")
            df = comp.multiselect_filter(df, "event", "Event-Typ")
        with col2:
            df = comp.text_search_filter(df, "blob_name", "Blob-Name enthält")
            df = comp.text_search_filter(df, "message", "Message enthält")

    # Errors prominently
    error_df = df[df["level"].isin(["ERROR", "WARNING"])] if "level" in df.columns else pd.DataFrame()
    if not error_df.empty:
        with st.expander(f"{len(error_df)} Fehler / Warnungen", expanded=True):
            comp.show_dataframe(error_df, height=250)

    st.subheader("Alle Events")
    display_cols = [c for c in ["timestamp", "level", "event", "message", "blob_name", "error_reason", "duration_ms"]
                    if c in df.columns]
    comp.show_dataframe(df[display_cols] if display_cols else df, height=420)


# ---------------------------------------------------------------------------
# Page: KI Readiness (vereint KI-Analyse + LLM Readiness)
# ---------------------------------------------------------------------------

def page_ki_readiness(run_id: str) -> None:
    st.header("KI Readiness")
    summary = _summary(run_id)
    ai_enabled = summary.get("enable_ai", False)
    ai_provider = summary.get("ai_provider", "none")

    if not ai_enabled or ai_provider == "none":
        st.info(
            "**KI war in diesem Lauf deaktiviert** (`ENABLE_AI=false` oder `AI_PROVIDER=none`).\n\n"
            "Die Tabelle unten zeigt Dateien, die für einen KI-Aufruf in Frage kämen."
        )

    comp.metric_row({
        "KI-Anbieter": ai_provider,
        "KI-Kandidaten": summary.get("ai_candidates", 0),
        "KI-Aufrufe": summary.get("ai_calls_used", 0),
        "KI-Überspringen": summary.get("ai_calls_skipped", 0),
        "KI-Fehler": summary.get("ai_errors", 0),
    })

    st.divider()

    # AI readiness from ai-candidates.csv
    cand_df = _csv(run_id, "ai-candidates.csv")

    # Details for needs_ai
    details_df = _csv(run_id, "classification-details.csv")
    unknown_count = 0
    low_conf_count = 0
    needs_ai_count = 0
    ai_disabled_count = 0
    top_extensions: dict = {}

    if not details_df.empty:
        if "class" in details_df.columns:
            unknown_count = int((details_df["class"] == "unknown").sum())
        if "confidence" in details_df.columns:
            conf_num = pd.to_numeric(details_df["confidence"], errors="coerce").fillna(0)
            low_conf_count = int((conf_num < 60).sum())
        if "needs_ai" in details_df.columns:
            needs_ai_count = int((details_df["needs_ai"].astype(str) == "True").sum())

    if not cand_df.empty and "ai_skipped_reason" in cand_df.columns:
        ai_disabled_count = int((cand_df["ai_skipped_reason"] == "ai_disabled").sum())
        if "extension" in cand_df.columns:
            top_extensions = cand_df["extension"].value_counts().head(5).to_dict()

    comp.metric_row({
        "Unknown": unknown_count,
        "Low Confidence (<60)": low_conf_count,
        "needs_ai=true": needs_ai_count,
        "AI-Kandidaten gesamt": len(cand_df) if not cand_df.empty else 0,
        "KI deaktiviert (skip)": ai_disabled_count,
    })

    if top_extensions:
        st.subheader("Top-Dateiendungen unter KI-Kandidaten")
        ext_df = pd.DataFrame(top_extensions.items(), columns=["Endung", "Anzahl"])
        st.bar_chart(ext_df.set_index("Endung")["Anzahl"])

    if not cand_df.empty:
        st.subheader(f"KI-Kandidaten ({len(cand_df)} Einträge)")
        with st.expander("Filter", expanded=False):
            cand_df = comp.multiselect_filter(cand_df, "ai_candidate_reason", "Kandidat-Grund")
            cand_df = comp.multiselect_filter(cand_df, "ai_skipped_reason", "Skip-Grund")
            cand_df = comp.multiselect_filter(cand_df, "extension", "Dateiendung")
        comp.show_dataframe(cand_df, height=350)

        # Recommended next command
        if needs_ai_count > 0 or len(cand_df) > 0:
            st.divider()
            st.subheader("Empfohlener nächster Befehl")
            st.info(
                f"**{needs_ai_count or len(cand_df)} Dateien** sind KI-Kandidaten. "
                "Starte einen KI-Dry-Run um die Ergebnisse zu prüfen, bevor du AI aktivierst:"
            )
            st.code(
                "docker compose run --rm worker --mode classify --dry-run"
                " --enable-ai --ai-provider foundry --ai-max-calls 20",
                language="bash",
            )
            st.warning("Die KI wird **nicht** automatisch gestartet. Befehl manuell kopieren und ausführen.")
    else:
        comp.empty_state("ai-candidates.csv nicht gefunden oder kein KI-Kandidat erkannt.")

    if not details_df.empty and "llm_used" in details_df.columns:
        ai_used_df = details_df[details_df["llm_used"] == "true"]
        if not ai_used_df.empty:
            st.divider()
            st.subheader(f"Vom KI klassifiziert ({len(ai_used_df)} Blobs)")
            cols = [c for c in ["blob_name", "class", "confidence", "ai_provider",
                                "ai_reason", "ai_input_chars", "reason_code"]
                    if c in ai_used_df.columns]
            comp.show_dataframe(ai_used_df[cols] if cols else ai_used_df, height=300)


# ---------------------------------------------------------------------------
# Page: Konfiguration
# ---------------------------------------------------------------------------

def page_config(_run_id: str) -> None:
    st.header("Konfiguration")
    st.info("Diese Seite zeigt die aktuelle Worker-Konfiguration (read-only). Keine Secrets werden angezeigt.")
    cfg = repo.config

    data = {
        "worker_name": cfg.worker_name,
        "worker_version": cfg.worker_version,
        "AZURE_STORAGE_ACCOUNT": cfg.storage_account,
        "SOURCE_CONTAINER": cfg.source_container,
        "REPORT_CONTAINER": cfg.report_container,
        "QUARANTINE_CONTAINER": cfg.quarantine_container,
        "DEFAULT_PREFIX": cfg.default_prefix or "(nicht gesetzt)",
        "DEFAULT_MAX_FILES": cfg.default_max_files,
        "AUTH_MODE": cfg.auth_mode,
        "ENABLE_AI": cfg.enable_ai,
        "AI_PROVIDER": cfg.ai_provider,
        "AI_MAX_CALLS_PER_RUN": cfg.ai_max_calls_per_run,
    }

    col1, col2 = st.columns(2)
    items = list(data.items())
    half = (len(items) + 1) // 2
    with col1:
        for k, v in items[:half]:
            st.metric(k, str(v))
    with col2:
        for k, v in items[half:]:
            st.metric(k, str(v))


# ---------------------------------------------------------------------------
# Page: Run Commands (Command Builder)
# ---------------------------------------------------------------------------

def page_run_commands(_run_id: str) -> None:
    st.header("🔧 Run Commands – Command Builder")
    st.info("Das Dashboard startet den Worker **nicht** selbst. Befehl kopieren und im Terminal ausführen.")

    cfg = repo.config

    col1, col2 = st.columns(2)
    with col1:
        mode = st.selectbox(
            "Modus",
            ["scan", "classify dry-run", "classify echtlauf"],
            index=0,
        )
        prefix = st.text_input("Prefix", value=cfg.default_prefix or "")
        max_files = st.number_input("Max Files", min_value=0, value=cfg.default_max_files, step=10)
    with col2:
        force = st.checkbox("--force (bereits klassifizierte neu verarbeiten)", value=False)
        enable_ai = st.checkbox("KI aktivieren (ENABLE_AI)", value=False)
        ai_provider = st.selectbox("KI-Anbieter", ["none", "foundry"], index=0,
                                   disabled=not enable_ai)
        ai_max_calls = st.number_input(
            "AI Max Calls", min_value=1, value=cfg.ai_max_calls_per_run, step=5,
            disabled=not enable_ai,
        )

    # Build command
    cmd_parts = ["docker compose run --rm worker"]
    if mode == "scan":
        cmd_parts.append("--mode scan")
        is_classify = False
        is_dry_run = False
    elif mode == "classify dry-run":
        cmd_parts.append("--mode classify --dry-run")
        is_classify = True
        is_dry_run = True
    else:
        cmd_parts.append("--mode classify")
        is_classify = True
        is_dry_run = False

    if prefix:
        cmd_parts.append(f'--prefix "{prefix}"')
    if max_files:
        cmd_parts.append(f"--max-files {int(max_files)}")
    if force:
        cmd_parts.append("--force")
    if enable_ai:
        cmd_parts.append("--enable-ai")
        if ai_provider != "none":
            cmd_parts.append(f"--ai-provider {ai_provider}")
        cmd_parts.append(f"--ai-max-calls {int(ai_max_calls)}")

    st.divider()
    st.subheader("Generierter Befehl")
    st.code(" \\\n  ".join(cmd_parts), language="bash")

    if is_classify and not is_dry_run:
        st.error(
            "**Echter Classify-Lauf**: Tags und Metadata werden in Azure geschrieben. "
            "Zuerst mit `classify dry-run` testen!"
        )
    if force:
        st.warning(
            "**--force aktiv**: Bereits klassifizierte Dateien werden erneut verarbeitet "
            "und Tags überschrieben."
        )
    if enable_ai:
        st.warning(
            "**KI aktiviert**: KI-Aufrufe kosten Token. "
            "Zuerst mit Dry-Run testen. Keine KI-Aktivierung ohne explizite Freigabe."
        )

    st.divider()
    st.subheader("Auth-Modi")
    st.markdown("""
| AUTH_MODE | Beschreibung |
|-----------|-------------|
| `device_code` | Browser-Login via Device-Code-URL (lokaler Docker-Test) |
| `default` | DefaultAzureCredential (az login / Managed Identity) |
| `connection_string` | Direkte Connection String (nur Notfall!) |
    """)


# ---------------------------------------------------------------------------
# Page: Exporte
# ---------------------------------------------------------------------------

def page_exports(run_id: str) -> None:
    st.header("Exporte")
    st.caption(f"Run: `{run_id}`")

    # admin-report.pdf
    st.subheader("Admin-Report PDF")
    pdf_bytes = compile_pdf_on_the_fly_frontend(run_id)
    if not pdf_bytes:
        pdf_bytes = repo.get_report_bytes(run_id, "admin-report.pdf")
    if pdf_bytes:
        st.download_button(
            "Admin-Report PDF herunterladen",
            data=pdf_bytes,
            file_name=f"admin-report-{run_id}.pdf",
            mime="application/pdf",
        )
    else:
        st.warning("admin-report.pdf nicht gefunden. Dieser Run wurde vor Einführung der Admin-Reports erzeugt.")

    # admin-report.json
    st.subheader("Admin-Report JSON")
    json_bytes = repo.get_report_bytes(run_id, "admin-report.json")
    if json_bytes:
        st.download_button(
            "Admin-Report JSON herunterladen",
            data=json_bytes,
            file_name=f"admin-report-{run_id}.json",
            mime="application/json",
        )
        with st.expander("Vorschau admin-report.json"):
            import json as _json
            try:
                st.json(_json.loads(json_bytes.decode("utf-8")))
            except Exception:
                st.text(json_bytes.decode("utf-8", errors="replace")[:2000])
    else:
        st.warning("admin-report.json nicht gefunden. Dieser Run wurde vor Einführung der Admin-Reports erzeugt.")

    # run-summary.json
    st.subheader("Run Summary JSON")
    summary_bytes = repo.get_report_bytes(run_id, "run-summary.json")
    if summary_bytes:
        st.download_button(
            "Run Summary JSON herunterladen",
            data=summary_bytes,
            file_name=f"run-summary-{run_id}.json",
            mime="application/json",
        )

    # Raw CSVs
    st.subheader("Raw CSVs")
    csv_files = [
        "classification-details.csv",
        "classification-summary.csv",
        "classification-errors.csv",
        "untagged-files.csv",
        "classification-samples.csv",
        "ai-candidates.csv",
    ]
    for fname in csv_files:
        raw = repo.get_report_bytes(run_id, fname)
        if raw:
            st.download_button(
                f"{fname} herunterladen",
                data=raw,
                file_name=f"{fname.replace('.csv', '')}-{run_id}.csv",
                mime="text/csv",
                key=f"dl_{fname}",
            )


# ===========================================================================
# NEW PAGES (Admin-Cockpit – 10 Bereiche)
# ===========================================================================

# ---------------------------------------------------------------------------
# 1. Cockpit
# ---------------------------------------------------------------------------

def page_cockpit() -> None:
    st.title("Andre3000 – Admin-Cockpit")
    latest = runs[0]
    summary = _summary(latest)
    admin = _admin_report(latest)

    if not summary:
        comp.empty_state("Kein run-summary.json für den neuesten Lauf gefunden.")
        return

    # Header strip
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Worker", repo.config.worker_name)
    c2.metric("Version", repo.config.worker_version)
    c3.metric("Storage Account", repo.config.storage_account)
    c4.metric("AI Status", "aktiviert" if repo.config.enable_ai else "deaktiviert")
    c1b, c2b, c3b, c4b = st.columns(4)
    c1b.metric("Source Container", repo.config.source_container)
    c2b.metric("Report Container", repo.config.report_container)
    c3b.metric("Prefix", repo.config.worker_version + "/")
    c4b.metric("Letzter Run", latest[:19].replace("T", " ") if latest else "-")

    st.divider()
    st.subheader("System-Status")
    _render_health(summary)

    action = _next_action(summary, admin)
    st.info(f"**Empfohlene nächste Aktion:** {action}")

    st.divider()
    st.subheader("KPIs – letzter Lauf")
    comp.dry_run_badge(summary.get("dry_run", False))
    comp.metric_row({
        "Letzter Run Status": summary.get("status", "-").upper(),
        "Mode": summary.get("mode", "-"),
        "Gestartet": str(summary.get("started_at", "-"))[:19].replace("T", " "),
        "Dauer (s)": f"{summary.get('duration_seconds', 0):.1f}",
    })
    st.divider()
    comp.metric_row({
        "Dateien gesehen": summary.get("files_seen", 0),
        "Verarbeitet": summary.get("files_processed", 0),
        "Klassifiziert": summary.get("files_classified", 0),
        "Unknown": summary.get("files_unknown", 0),
    })
    comp.metric_row({
        "KI-Kandidaten": summary.get("ai_candidates", 0),
        "Fehler": summary.get("files_error", 0),
        "KI-Aufrufe": summary.get("ai_calls_used", 0),
        "Durchsatz (Dateien/h)": summary.get("throughput_files_per_hour", 0),
    })
    comp.metric_row({
        "GB verarbeitet": f"{summary.get('gb_processed', 0):.4f}",
        "Übersprungen": summary.get("files_skipped", 0),
        "Ungetaggt": summary.get("files_untagged", 0),
        "Laufzeit": f"{summary.get('duration_seconds', 0):.0f}s",
    })

    # Verteilungen & Analysen (Donut / Pie Charts & Coverage Metrics)
    st.divider()
    st.subheader("Verteilungen & Analysen")
    details_df = _csv(latest, "classification-details.csv")
    if not details_df.empty:
        import altair as alt  # noqa: PLC0415
        
        col1, col2, col3 = st.columns(3)
        
        # 1. Classes / Tags distribution
        with col1:
            st.markdown("##### Klassifizierung (Tags)")
            class_col = "class" if "class" in details_df.columns else "class_label"
            if class_col in details_df.columns:
                counts = details_df[class_col].fillna("unbekannt").astype(str).value_counts().reset_index()
                counts.columns = ["Klasse", "Anzahl"]
                
                chart = alt.Chart(counts).mark_arc(innerRadius=40, outerRadius=90).encode(
                    theta=alt.Theta("Anzahl:Q", stack=True),
                    color=alt.Color("Klasse:N", scale=alt.Scale(scheme="tableau10"), legend=alt.Legend(orient="bottom")),
                    tooltip=["Klasse", "Anzahl"]
                ).properties(height=230)
                st.altair_chart(chart, use_container_width=True)
            else:
                st.caption("Klassenspalte nicht gefunden.")
                
        # 2. File extensions distribution
        with col2:
            st.markdown("##### Dateitypen (Endung)")
            ext_col = "extension"
            if ext_col in details_df.columns:
                counts = details_df[ext_col].fillna("unbekannt").astype(str).str.lower().value_counts().reset_index()
                counts.columns = ["Dateiendung", "Anzahl"]
                # Keep top 5 and group others
                if len(counts) > 5:
                    top5 = counts.iloc[:5]
                    others_sum = counts.iloc[5:]["Anzahl"].sum()
                    others_df = pd.DataFrame([{"Dateiendung": "Andere", "Anzahl": others_sum}])
                    counts = pd.concat([top5, others_df], ignore_index=True)
                
                chart = alt.Chart(counts).mark_arc(innerRadius=40, outerRadius=90).encode(
                    theta=alt.Theta("Anzahl:Q", stack=True),
                    color=alt.Color("Dateiendung:N", scale=alt.Scale(scheme="accent"), legend=alt.Legend(orient="bottom")),
                    tooltip=["Dateiendung", "Anzahl"]
                ).properties(height=230)
                st.altair_chart(chart, use_container_width=True)
            else:
                st.caption("Dateiendungsspalte nicht gefunden.")
                
        # 3. DSGVO relevancy
        with col3:
            st.markdown("##### Sicherheitsmerkmale (DSGVO)")
            dsgvo_col = "dsgvo"
            if dsgvo_col in details_df.columns:
                # Map true/false to readable text
                val_mapped = details_df[dsgvo_col].astype(str).map({"true": "DSGVO relevant", "false": "Nicht relevant", "NaN": "Unbekannt"}).fillna("Unbekannt")
                counts = val_mapped.value_counts().reset_index()
                counts.columns = ["Status", "Anzahl"]
                
                chart = alt.Chart(counts).mark_arc(innerRadius=40, outerRadius=90).encode(
                    theta=alt.Theta("Anzahl:Q", stack=True),
                    color=alt.Color("Status:N", scale=alt.Scale(scheme="category10"), legend=alt.Legend(orient="bottom")),
                    tooltip=["Status", "Anzahl"]
                ).properties(height=230)
                st.altair_chart(chart, use_container_width=True)
            else:
                st.caption("DSGVO-Spalte nicht gefunden.")

        # Coverage Indicators
        st.divider()
        st.markdown("##### Metadaten- & Tagging-Coverage")
        c_meta_1, c_meta_2, c_meta_3 = st.columns(3)
        
        total_files = len(details_df)
        with_meta = details_df["metadata_written"].astype(str).eq("true").sum() if "metadata_written" in details_df.columns else 0
        with_tags = details_df["tags_written"].astype(str).eq("true").sum() if "tags_written" in details_df.columns else 0
        with_llm = details_df["llm_used"].astype(str).eq("true").sum() if "llm_used" in details_df.columns else 0
        
        c_meta_1.metric(
            "Metadaten geschrieben", 
            f"{with_meta} / {total_files}", 
            f"{with_meta/total_files*100:.1f}% Coverage" if total_files > 0 else "0%"
        )
        c_meta_2.metric(
            "Blob-Tags geschrieben", 
            f"{with_tags} / {total_files}", 
            f"{with_tags/total_files*100:.1f}% Coverage" if total_files > 0 else "0%"
        )
        c_meta_3.metric(
            "LLM KI-Analyse genutzt", 
            f"{with_llm} / {total_files}", 
            f"{with_llm/total_files*100:.1f}% aller Dateien" if total_files > 0 else "0%"
        )
    else:
        st.warning("Keine detaillierten Klassifizierungsdaten für Diagrammverteilung vorhanden.")

    risks = admin.get("risk_assessment", [])
    if risks:
        st.divider()
        st.subheader("Risiken")
        for r in risks:
            if r.get("severity") == "error":
                st.error(r.get("message", ""))
            else:
                st.warning(r.get("message", ""))

    all_actions = admin.get("next_actions", [])
    if len(all_actions) > 1:
        st.divider()
        st.subheader("Alle empfohlenen Maßnahmen")
        for a in all_actions:
            st.markdown(f"- {a}")


# ---------------------------------------------------------------------------
# 2. Runs
# ---------------------------------------------------------------------------

def page_runs() -> None:
    st.header("Runs – Übersicht aller Läufe")
    all_s = _all_summaries()
    if not all_s:
        comp.empty_state("Keine Run-Daten gefunden.")
        return

    rows = []
    for s in all_s:
        run_id = s.get("_run_id", s.get("run_id", "-"))
        rows.append({
            "Run-ID": run_id,
            "Datum/Uhrzeit": str(s.get("started_at", "-"))[:19].replace("T", " "),
            "Modus": s.get("mode", "-"),
            "Dry Run": "✓" if s.get("dry_run") else "",
            "Force": "✓" if s.get("force") else "",
            "Prefix": s.get("prefix", "-"),
            "Max Files": s.get("max_files", "-"),
            "Gesehen": s.get("files_seen", 0),
            "Verarbeitet": s.get("files_processed", 0),
            "Unknown": s.get("files_unknown", 0),
            "KI-Kandidaten": s.get("ai_candidates", 0),
            "Fehler": s.get("files_error", 0),
            "KI-Aufrufe": s.get("ai_calls_used", 0),
            "Status": s.get("status", "-").upper(),
        })

    df = pd.DataFrame(rows)

    with st.expander("Filter", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            df = comp.multiselect_filter(df, "Modus", "Modus")
            df = comp.multiselect_filter(df, "Status", "Status")
        with c2:
            only_errors = st.checkbox("Nur Läufe mit Fehlern", value=False)
            if only_errors:
                df = df[df["Fehler"] > 0]
            only_dry = st.checkbox("Nur Dry Runs", value=False)
            if only_dry:
                df = df[df["Dry Run"] == "✓"]
        with c3:
            only_ai = st.checkbox("Nur mit AI-Aufrufen", value=False)
            if only_ai:
                df = df[pd.to_numeric(df["KI-Aufrufe"], errors="coerce").fillna(0) > 0]

    st.caption(
        f"{len(df)} Läufe · Neueste zuerst · "
        "Run im linken Menü auswählen → Run Detail öffnen"
    )
    comp.show_dataframe(df, height=420)


# ---------------------------------------------------------------------------
# 3. Run Detail
# ---------------------------------------------------------------------------

def page_run_detail(run_id: str) -> None:
    st.header(f"Run Detail – `{run_id}`")
    summary = _summary(run_id)
    admin = _admin_report(run_id)

    if not summary:
        comp.empty_state("run-summary.json nicht gefunden.")
        return

    comp.dry_run_badge(summary.get("dry_run", False))

    st.subheader("1. Executive Summary")
    _render_health(summary)
    st.info(f"**Empfohlene nächste Aktion:** {_next_action(summary, admin)}")
    with st.expander("Alle empfohlenen Maßnahmen", expanded=False):
        for a in admin.get("next_actions", []):
            st.markdown(f"- {a}")

    st.divider()
    st.subheader("2. Azure-Kontext")
    comp.metric_row({
        "Storage Account": summary.get("storage_account", "-"),
        "Source Container": summary.get("source_container", "-"),
        "Report Container": summary.get("report_container", "-"),
        "Prefix": summary.get("prefix", "(alle)") or "(alle)",
    })

    st.divider()
    st.subheader("3. Sicherheitsstatus")
    dry_run = summary.get("dry_run", False)
    force = summary.get("force", False)
    c1, c2, c3 = st.columns(3)
    c1.metric("Schreiboperationen", "DEAKTIVIERT" if dry_run else "AKTIV")
    c2.metric("Force-Modus", "✓ Aktiv" if force else "Nein")
    c3.metric("KI aktiviert", "Ja" if summary.get("enable_ai", False) else "Nein")
    if not dry_run:
        st.warning("Dieser Lauf hat Tags/Metadata in Azure geschrieben.")
    if force:
        st.warning("Force-Modus war aktiv – bereits klassifizierte Dateien wurden neu verarbeitet.")

    st.divider()
    st.subheader("4. Verarbeitung")
    comp.metric_row({
        "Gesehen": summary.get("files_seen", 0),
        "Ungetaggt": summary.get("files_untagged", 0),
        "Verarbeitet": summary.get("files_processed", 0),
        "Übersprungen": summary.get("files_skipped", 0),
    })
    comp.metric_row({
        "Klassifiziert": summary.get("files_classified", 0),
        "Unknown": summary.get("files_unknown", 0),
        "Fehler": summary.get("files_error", 0),
        "GB verarbeitet": f"{summary.get('gb_processed', 0):.4f}",
    })
    comp.metric_row({
        "Dauer (s)": f"{summary.get('duration_seconds', 0):.1f}",
        "Durchsatz (Dateien/h)": summary.get("throughput_files_per_hour", 0),
        "Durchsatz (GB/h)": summary.get("throughput_gb_per_hour", 0),
        "Mode": summary.get("mode", "-"),
    })

    st.divider()
    st.subheader("5. Klassifizierung")
    class_dist = admin.get("classification_distribution", {})
    if class_dist:
        df_class = pd.DataFrame(class_dist.items(), columns=["Klasse", "Anzahl"])
        df_class = df_class.sort_values("Anzahl", ascending=False)
        c1, c2 = st.columns([1, 2])
        with c1:
            comp.show_dataframe(df_class, height=250)
        with c2:
            if not df_class.empty:
                st.bar_chart(df_class.set_index("Klasse")["Anzahl"])

    st.divider()
    st.subheader("6. KI Readiness")
    ai_r = admin.get("ai_readiness", {})
    comp.metric_row({
        "KI-Kandidaten": ai_r.get("candidates_total", summary.get("ai_candidates", 0)),
        "Unknown": ai_r.get("unknown_total", summary.get("files_unknown", 0)),
        "Low Confidence (<60)": ai_r.get("low_confidence_total", 0),
        "KI-Aufrufe": summary.get("ai_calls_used", 0),
    })
    unknown_cnt = ai_r.get("unknown_total", summary.get("files_unknown", 0))
    if unknown_cnt > 0 and int(summary.get("ai_calls_used", 0)) == 0:
        st.info(
            f"**{unknown_cnt} Dateien** regelbasiert nicht erkannt. "
            "Nächster sinnvoller Schritt: Content Extraction + AI Dry Run."
        )

    st.divider()
    st.subheader("7. Fehler")
    err_sum = admin.get("errors_summary", [])
    if err_sum:
        comp.show_dataframe(pd.DataFrame(err_sum), height=250)
    else:
        st.success("Keine Fehler in diesem Lauf.")

    risks = admin.get("risk_assessment", [])
    if risks:
        st.divider()
        st.subheader("Risiken")
        for r in risks:
            if r.get("severity") == "error":
                st.error(r.get("message", ""))
            else:
                st.warning(r.get("message", ""))

    st.divider()
    st.subheader("8. Report-Dateien")
    report_files = repo.list_report_files(run_id)
    if report_files:
        st.code("\n".join(report_files))
    else:
        st.info("Dateiliste nicht verfügbar.")

    with st.expander("run-summary.json", expanded=False):
        st.json(summary)
    if admin:
        with st.expander("admin-report.json", expanded=False):
            st.json(admin)

    df_ev = _events(run_id)
    if not df_ev.empty and "level" in df_ev.columns:
        err_ev = df_ev[df_ev["level"].isin(["ERROR", "WARNING"])]
        if not err_ev.empty:
            with st.expander(f"Log-Fehler ({len(err_ev)} Einträge)", expanded=False):
                comp.show_dataframe(err_ev, height=250)


# ---------------------------------------------------------------------------
# 4. Klassifizierung
# ---------------------------------------------------------------------------

def page_classification(run_id: str) -> None:
    st.header("Klassifizierung")
    tab1, tab2, tab3 = st.tabs(["Verteilung", "Details", "Stichproben"])

    with tab1:
        df_sum = _csv(run_id, "classification-summary.csv")
        if df_sum.empty:
            comp.empty_state("classification-summary.csv nicht gefunden.")
        else:
            class_keys = [k for k in df_sum.get("key", pd.Series()).tolist()
                          if str(k).startswith("class_")]
            if class_keys:
                cdf = df_sum[df_sum["key"].isin(class_keys)].copy()
                cdf.columns = ["Klasse", "Anzahl"]
                cdf["Klasse"] = cdf["Klasse"].str.replace("class_", "", regex=False)
                cdf["Anzahl"] = pd.to_numeric(cdf["Anzahl"], errors="coerce").fillna(0).astype(int)
                cdf = cdf.sort_values("Anzahl", ascending=False)
                c1, c2 = st.columns([1, 2])
                with c1:
                    comp.show_dataframe(cdf, height=300)
                with c2:
                    st.bar_chart(cdf.set_index("Klasse")["Anzahl"])
            st.divider()
            st.subheader("Alle Metriken")
            comp.show_dataframe(df_sum, height=400)

    with tab2:
        df_det = _csv(run_id, "classification-details.csv")
        if df_det.empty:
            comp.empty_state("classification-details.csv nicht gefunden.")
        else:
            st.caption(f"{len(df_det)} Einträge geladen")
            with st.expander("Filter", expanded=True):
                c1, c2, c3 = st.columns(3)
                with c1:
                    df_det = comp.multiselect_filter(df_det, "class", "Klasse")
                    df_det = comp.multiselect_filter(df_det, "status", "Status")
                with c2:
                    df_det = comp.multiselect_filter(df_det, "dsgvo", "DSGVO")
                    df_det = comp.multiselect_filter(df_det, "archive_candidate", "Archiv-Kandidat")
                with c3:
                    df_det = comp.multiselect_filter(df_det, "llm_used", "LLM genutzt")
                    df_det = comp.multiselect_filter(df_det, "extension", "Dateiendung")
                if "confidence" in df_det.columns:
                    df_det["_conf"] = pd.to_numeric(df_det["confidence"], errors="coerce").fillna(0)
                    mn, mx = st.slider("Confidence-Bereich", 0, 100, (0, 100))
                    df_det = df_det[(df_det["_conf"] >= mn) & (df_det["_conf"] <= mx)]
                    df_det = df_det.drop(columns=["_conf"])
                df_det = comp.text_search_filter(df_det, "blob_name", "Blob-Name enthält")
            st.caption(f"{len(df_det)} Einträge nach Filter")
            show_cols = [c for c in ["blob_name", "class", "confidence", "dsgvo",
                                     "archive_candidate", "llm_used", "reason_code",
                                     "status", "processed_at"]
                         if c in df_det.columns]
            comp.show_dataframe(df_det[show_cols] if show_cols else df_det, height=480)

    with tab3:
        df_samp = _csv(run_id, "classification-samples.csv")
        if df_samp.empty:
            comp.empty_state("classification-samples.csv nicht gefunden.")
        else:
            groups = sorted(df_samp["sample_group"].unique().tolist()) \
                if "sample_group" in df_samp.columns else []
            if not groups:
                comp.show_dataframe(df_samp)
            else:
                selected_groups = st.multiselect("Klassen", groups, default=groups)
                for grp in selected_groups:
                    gdf = df_samp[df_samp["sample_group"] == grp]
                    with st.expander(
                        f"Klasse: {grp}  ({len(gdf)} Stichproben)",
                        expanded=grp in ("unknown", "br", "hr", "dsgvo"),
                    ):
                        comp.show_dataframe(gdf, height=280)


# ---------------------------------------------------------------------------
# 5. KI Readiness
# ---------------------------------------------------------------------------

def page_ki_readiness(run_id: str) -> None:
    st.header("KI Readiness")
    summary = _summary(run_id)
    admin = _admin_report(run_id)
    ai_enabled = summary.get("enable_ai", False)
    ai_provider = summary.get("ai_provider", "none")

    if not ai_enabled or ai_provider == "none":
        st.info(
            "**KI war in diesem Lauf deaktiviert.**\n\n"
            "Die Tabelle unten zeigt Dateien, die für einen KI-Aufruf in Frage kämen."
        )

    ai_r = admin.get("ai_readiness", {})
    comp.metric_row({
        "KI-Anbieter": ai_provider,
        "KI-Kandidaten": ai_r.get("candidates_total", summary.get("ai_candidates", 0)),
        "Unknown": ai_r.get("unknown_total", summary.get("files_unknown", 0)),
        "Low Confidence (<60)": ai_r.get("low_confidence_total", 0),
    })
    comp.metric_row({
        "KI-Aufrufe": summary.get("ai_calls_used", 0),
        "KI-Übersprungen": summary.get("ai_calls_skipped", 0),
        "KI-Fehler": summary.get("ai_errors", 0),
        "needs_ai=true": ai_r.get("needs_ai_total", 0),
    })

    top_ext = ai_r.get("top_extensions", [])
    if top_ext:
        st.subheader("Top-Dateiendungen unter KI-Kandidaten")
        ext_df = pd.DataFrame(top_ext)
        if "ext" in ext_df.columns and "count" in ext_df.columns:
            st.bar_chart(ext_df.rename(columns={"ext": "Endung", "count": "Anzahl"})
                         .set_index("Endung")["Anzahl"])

    st.divider()
    cand_df = _csv(run_id, "ai-candidates.csv")
    details_df = _csv(run_id, "classification-details.csv")

    if not cand_df.empty:
        st.subheader(f"KI-Kandidaten ({len(cand_df)} Einträge)")
        with st.expander("Filter", expanded=False):
            cand_df = comp.multiselect_filter(cand_df, "ai_candidate_reason", "Kandidat-Grund")
            cand_df = comp.multiselect_filter(cand_df, "ai_skipped_reason", "Skip-Grund")
            cand_df = comp.multiselect_filter(cand_df, "extension", "Dateiendung")
        show_cols = [c for c in ["blob_name", "extension", "rule_class", "rule_confidence",
                                 "ai_candidate_reason", "ai_skipped_reason", "reason_code"]
                     if c in cand_df.columns]
        comp.show_dataframe(cand_df[show_cols] if show_cols else cand_df, height=350)
    else:
        comp.empty_state("ai-candidates.csv nicht gefunden.")

    if not details_df.empty and "llm_used" in details_df.columns:
        ai_used_df = details_df[details_df["llm_used"] == "true"]
        if not ai_used_df.empty:
            st.divider()
            st.subheader(f"Vom KI klassifiziert ({len(ai_used_df)} Blobs)")
            cols = [c for c in ["blob_name", "class", "confidence", "ai_provider",
                                "ai_reason", "ai_input_chars", "reason_code"]
                    if c in ai_used_df.columns]
            comp.show_dataframe(ai_used_df[cols] if cols else ai_used_df, height=300)

    st.divider()
    st.subheader("Nächste Aktionen")
    needs_ai = int(ai_r.get("needs_ai_total", 0)) or int(summary.get("ai_candidates", 0))
    if needs_ai > 0 and not ai_enabled:
        st.info(f"**{needs_ai} Dateien** sind KI-Kandidaten. Befehl für KI-Dry-Run:")
        st.code(
            "docker compose run --rm worker --mode classify --dry-run"
            " --enable-ai --ai-provider foundry --ai-max-calls 20",
            language="bash",
        )
        st.warning("KI wird **nicht** automatisch gestartet. Befehl manuell ausführen.")
    elif not needs_ai:
        st.success("Keine KI-Kandidaten in diesem Lauf.")


# ---------------------------------------------------------------------------
# 6. Dateien & Dateitypen
# ---------------------------------------------------------------------------

def page_file_types(run_id: str) -> None:
    st.header("Dateien & Dateitypen")
    admin = _admin_report(run_id)
    details_df = _csv(run_id, "classification-details.csv")
    tab1, tab2 = st.tabs(["Übersicht", "Dateidetails"])

    with tab1:
        ftype_dist = admin.get("file_type_distribution", [])
        if ftype_dist:
            ft_df = pd.DataFrame(ftype_dist)
            if "extension" in ft_df.columns and "count" in ft_df.columns:
                c1, c2 = st.columns([1, 2])
                with c1:
                    comp.show_dataframe(ft_df, height=350)
                with c2:
                    st.bar_chart(ft_df.set_index("extension")["count"])
        elif not details_df.empty and "extension" in details_df.columns:
            ext_counts = details_df["extension"].value_counts().reset_index()
            ext_counts.columns = ["Endung", "Anzahl"]
            c1, c2 = st.columns([1, 2])
            with c1:
                comp.show_dataframe(ext_counts, height=350)
            with c2:
                st.bar_chart(ext_counts.set_index("Endung")["Anzahl"])
        else:
            comp.empty_state("Keine Dateitype-Daten gefunden.")
            return

        if not details_df.empty:
            st.divider()
            if "readable" in details_df.columns:
                r_counts = details_df["readable"].value_counts()
                comp.metric_row({
                    "Lesbar": int(r_counts.get("true", 0)),
                    "Unlesbar": int(r_counts.get("false", 0)),
                    "Archiv-Kandidaten": int(
                        (details_df.get("archive_candidate", pd.Series()) == "true").sum()),
                    "DSGVO-Dateien": int(
                        (details_df.get("dsgvo", pd.Series()) == "true").sum()),
                })
            if "extension" in details_df.columns:
                agg: dict = {}
                for _, row in details_df.iterrows():
                    ext = row.get("extension", "(none)") or "(none)"
                    if ext not in agg:
                        agg[ext] = {"count": 0, "total_bytes": 0}
                    agg[ext]["count"] += 1
                    agg[ext]["total_bytes"] += int(row.get("size_bytes", 0) or 0)
                agg_df = pd.DataFrame([
                    {"Endung": k, "Anzahl": v["count"],
                     "Gesamt-Bytes": v["total_bytes"],
                     "Ø Bytes": v["total_bytes"] // max(v["count"], 1)}
                    for k, v in sorted(agg.items(), key=lambda x: -x[1]["count"])
                ])
                st.subheader("Aggregation nach Dateiendung")
                comp.show_dataframe(agg_df, height=350)

    with tab2:
        if details_df.empty:
            comp.empty_state("classification-details.csv nicht gefunden.")
        else:
            with st.expander("Filter", expanded=False):
                details_df = comp.multiselect_filter(details_df, "extension", "Dateiendung")
                details_df = comp.multiselect_filter(details_df, "readable", "Lesbar")
                details_df = comp.text_search_filter(details_df, "blob_name", "Blob-Name enthält")
            show_cols = [c for c in ["blob_name", "size_bytes", "extension", "readable",
                                     "archive_candidate", "reason_code", "class", "status"]
                         if c in details_df.columns]
            comp.show_dataframe(details_df[show_cols] if show_cols else details_df, height=480)


# ---------------------------------------------------------------------------
# 7. Fehler & Risiken
# ---------------------------------------------------------------------------

def page_errors_risks(run_id: str) -> None:
    st.header("Fehler & Risiken")
    admin = _admin_report(run_id)
    tab1, tab2 = st.tabs(["Fehler", "Risiken"])

    with tab1:
        df = _csv(run_id, "classification-errors.csv")
        summary = _summary(run_id)
        err_count = int(summary.get("files_error", 0))
        if df.empty and err_count == 0:
            st.success("Keine Fehler in diesem Lauf.")
        elif not df.empty:
            st.error(f"**{len(df)} Fehler** gefunden")
            comp.metric_row({
                "Fehler gesamt": len(df),
                "Fehler-Stufen": df["error_stage"].nunique() if "error_stage" in df.columns else "-",
                "Retry empfohlen": int(
                    (df.get("retry_recommended", pd.Series()) == "true").sum()),
                "Unlesbar/Unsupported": int(
                    (df.get("error_reason", pd.Series()).str.contains(
                        "unreadable|unsupported", case=False, na=False)).sum()),
            })
            with st.expander("Filter", expanded=False):
                df = comp.multiselect_filter(df, "error_stage", "Fehler-Stufe")
                df = comp.multiselect_filter(df, "retry_recommended", "Retry empfohlen")
                df = comp.text_search_filter(df, "error_reason", "Fehler-Grund enthält")
            show_cols = [c for c in ["blob_name", "error_stage", "error_reason",
                                     "error_message", "retry_recommended", "extension"]
                         if c in df.columns]
            comp.show_dataframe(df[show_cols] if show_cols else df, height=450)
        else:
            st.warning(f"{err_count} Fehler laut run-summary.json. CSV nicht gefunden.")

    with tab2:
        summary = _summary(run_id)
        risks = admin.get("risk_assessment", [])
        unknown_pct = 0.0
        proc = int(summary.get("files_processed", 0))
        if proc > 0:
            unknown_pct = int(summary.get("files_unknown", 0)) / proc * 100

        st.subheader("Risk Cards")
        ai_cand = int(summary.get("ai_candidates", 0))
        if ai_cand > 0 and not summary.get("enable_ai", False):
            st.warning(f"KI-Kandidaten vorhanden ({ai_cand}), aber KI deaktiviert")
        if unknown_pct > 80:
            st.error(f"unknown > 80% ({unknown_pct:.0f}% der verarbeiteten Dateien)")
        elif int(summary.get("files_unknown", 0)) > 0:
            st.warning(f"{summary.get('files_unknown', 0)} Dateien als unknown klassifiziert")
        if int(summary.get("files_error", 0)) > 0:
            st.error(f"{summary.get('files_error', 0)} Fehler – Retry empfohlen")
        if not summary.get("reports_uploaded", True) and proc > 0:
            st.warning("Reports wurden nicht nach Azure hochgeladen")
        if ai_cand == 0 and int(summary.get("files_unknown", 0)) == 0 \
                and int(summary.get("files_error", 0)) == 0:
            st.success("Keine Risiken erkannt.")

        if risks:
            st.divider()
            st.subheader("Risiken aus admin-report.json")
            for r in risks:
                risk_key = r.get("risk", "")
                msg = r.get("message", "")
                if r.get("severity") == "error":
                    st.error(f"[{risk_key}] {msg}")
                else:
                    st.warning(f"[{risk_key}] {msg}")


# ---------------------------------------------------------------------------
# 8. Reports & Exporte
# ---------------------------------------------------------------------------

def page_reports_exports(run_id: str) -> None:
    st.header("Reports & Exporte")
    st.caption(f"Run: `{run_id}`")

    report_files = repo.list_report_files(run_id)
    if report_files:
        with st.expander("Verfügbare Report-Dateien", expanded=True):
            st.code("\n".join(report_files))
    else:
        st.info("Dateiliste nicht verfügbar.")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Admin-Report PDF")
        pdf_bytes = compile_pdf_on_the_fly_frontend(run_id)
        if not pdf_bytes:
            pdf_bytes = repo.get_report_bytes(run_id, "admin-report.pdf")
        if pdf_bytes:
            st.download_button(
                "Admin-Report PDF herunterladen",
                data=pdf_bytes,
                file_name=f"admin-report-{run_id}.pdf",
                mime="application/pdf",
            )
            st.caption(f"Größe: {len(pdf_bytes):,} Bytes")
        else:
            st.warning(
                "admin-report.pdf nicht gefunden. "
                "Dieser Run wurde vor Einführung der Admin-Reports erzeugt."
            )

    with c2:
        st.subheader("Admin-Report JSON")
        json_bytes = repo.get_report_bytes(run_id, "admin-report.json")
        if json_bytes:
            st.download_button(
                "Admin-Report JSON herunterladen",
                data=json_bytes,
                file_name=f"admin-report-{run_id}.json",
                mime="application/json",
            )
            st.caption(f"Größe: {len(json_bytes):,} Bytes")
            with st.expander("Vorschau admin-report.json"):
                try:
                    st.json(json.loads(json_bytes.decode("utf-8")))
                except Exception:
                    st.text(json_bytes.decode("utf-8", errors="replace")[:2000])
        else:
            st.warning(
                "admin-report.json nicht gefunden. "
                "Dieser Run wurde vor Einführung der Admin-Reports erzeugt."
            )

    st.divider()
    st.subheader("Run Summary JSON")
    summary_bytes = repo.get_report_bytes(run_id, "run-summary.json")
    if summary_bytes:
        st.download_button(
            "run-summary.json herunterladen",
            data=summary_bytes,
            file_name=f"run-summary-{run_id}.json",
            mime="application/json",
        )

    st.divider()
    st.subheader("CSV Reports")
    csv_files = [
        ("classification-details.csv", "Klassifizierungsdetails"),
        ("classification-summary.csv", "Klassifizierungszusammenfassung"),
        ("classification-errors.csv", "Fehler"),
        ("untagged-files.csv", "Ungetaggte Dateien"),
        ("classification-samples.csv", "Stichproben"),
        ("ai-candidates.csv", "KI-Kandidaten"),
    ]
    cols = st.columns(3)
    for i, (fname, label) in enumerate(csv_files):
        raw = repo.get_report_bytes(run_id, fname)
        with cols[i % 3]:
            if raw:
                st.download_button(
                    label,
                    data=raw,
                    file_name=f"{fname.replace('.csv', '')}-{run_id}.csv",
                    mime="text/csv",
                    key=f"new_dl_{fname}",
                )
            else:
                st.caption(f"_{fname} nicht gefunden_")

    st.divider()
    st.subheader("Events Log")
    events_bytes = repo.get_report_bytes(run_id, "run-events.jsonl")
    if events_bytes:
        st.download_button(
            "run-events.jsonl herunterladen",
            data=events_bytes,
            file_name=f"run-events-{run_id}.jsonl",
            mime="application/jsonlines",
        )
    else:
        st.caption("_run-events.jsonl nicht gefunden_")


# ---------------------------------------------------------------------------
# 9. Konfiguration
# ---------------------------------------------------------------------------

def page_config_new() -> None:
    st.header("Konfiguration")
    st.info("Read-only. Keine Secrets werden angezeigt.")
    cfg = repo.config
    config_data = {
        "worker_name": cfg.worker_name,
        "worker_version": cfg.worker_version,
        "AZURE_STORAGE_ACCOUNT": cfg.storage_account,
        "SOURCE_CONTAINER": cfg.source_container,
        "REPORT_CONTAINER": cfg.report_container,
        "QUARANTINE_CONTAINER": cfg.quarantine_container,
        "DEFAULT_PREFIX": cfg.default_prefix or "(nicht gesetzt)",
        "DEFAULT_MAX_FILES": cfg.default_max_files,
        "AUTH_MODE": cfg.auth_mode,
        "ENABLE_AI": cfg.enable_ai,
        "AI_PROVIDER": cfg.ai_provider,
        "AI_MAX_CALLS_PER_RUN": cfg.ai_max_calls_per_run,
        "AZURE_STORAGE_CONNECTION_STRING":
            "Secret-Konfiguration aktiv – Wert wird nicht angezeigt."
            if cfg.connection_string else "(nicht gesetzt)",
    }
    c1, c2 = st.columns(2)
    items = list(config_data.items())
    half = (len(items) + 1) // 2
    with c1:
        for k, v in items[:half]:
            st.metric(k, str(v))
    with c2:
        for k, v in items[half:]:
            st.metric(k, str(v))
    if cfg.connection_string:
        st.warning(
            "**AZURE_STORAGE_CONNECTION_STRING ist gesetzt.**  \n"
            "Secret-Konfiguration aktiv – Wert wird nicht angezeigt."
        )


# ---------------------------------------------------------------------------
# 10. Run Commands
# ---------------------------------------------------------------------------

def page_run_commands_new() -> None:
    st.header("Run Commands – Command Builder")
    st.info(
        "Das Dashboard startet den Worker **nicht** selbst. "
        "Befehl kopieren und im Terminal ausführen."
    )
    cfg = repo.config
    c1, c2 = st.columns(2)
    with c1:
        mode = st.selectbox(
            "Modus", ["scan", "classify dry-run", "classify echtlauf"], index=0
        )
        prefix = st.text_input("Prefix", value=cfg.default_prefix or "")
        max_files = st.number_input("Max Files", min_value=0, value=cfg.default_max_files, step=10)
    with c2:
        force = st.checkbox("--force (bereits klassifizierte neu verarbeiten)", value=False)
        enable_ai = st.checkbox("KI aktivieren (ENABLE_AI)", value=False)
        ai_provider = st.selectbox(
            "KI-Anbieter", ["none", "foundry"], index=0, disabled=not enable_ai
        )
        ai_max_calls = st.number_input(
            "AI Max Calls", min_value=1, value=cfg.ai_max_calls_per_run,
            step=5, disabled=not enable_ai,
        )

    cmd_parts = ["docker compose run --rm worker"]
    if mode == "scan":
        cmd_parts.append("--mode scan")
        is_classify, is_dry_run = False, False
    elif mode == "classify dry-run":
        cmd_parts.append("--mode classify --dry-run")
        is_classify, is_dry_run = True, True
    else:
        cmd_parts.append("--mode classify")
        is_classify, is_dry_run = True, False

    if prefix:
        cmd_parts.append(f'--prefix "{prefix}"')
    if max_files:
        cmd_parts.append(f"--max-files {int(max_files)}")
    if force:
        cmd_parts.append("--force")
    if enable_ai:
        cmd_parts.append("--enable-ai")
        if ai_provider != "none":
            cmd_parts.append(f"--ai-provider {ai_provider}")
        cmd_parts.append(f"--ai-max-calls {int(ai_max_calls)}")

    st.divider()
    st.subheader("Generierter Befehl")
    st.code(" \\\n  ".join(cmd_parts), language="bash")

    if is_classify and not is_dry_run:
        st.error(
            "Echter Classify-Lauf: Tags und Metadata werden in Azure geschrieben. "
            "Zuerst mit `classify dry-run` testen!"
        )
    if force:
        st.warning("--force aktiv: Bereits klassifizierte Dateien werden neu verarbeitet.")
    if enable_ai:
        st.warning("KI aktiviert: Aufrufe kosten Token. Erst Dry-Run testen.")
    if int(max_files) > 50:
        st.warning("max-files > 50 ist für den Pilot nicht empfohlen.")

    st.divider()
    st.subheader("Auth-Modi")
    st.markdown("""
| AUTH_MODE | Beschreibung |
|-----------|-------------|
| `device_code` | Browser-Login via Device-Code-URL |
| `default` | DefaultAzureCredential (az login / Managed Identity) |
| `connection_string` | Direkte Connection String (nur Notfall!) |
    """)


# ---------------------------------------------------------------------------
# Router (neu – 10 Bereiche)
# ---------------------------------------------------------------------------

NEW_ROUTER = {
    "Cockpit": lambda _r: page_cockpit(),
    "Runs": lambda _r: page_runs(),
    "Run Detail": page_run_detail,
    "Klassifizierung": page_classification,
    "KI Readiness": page_ki_readiness,
    "Dateien & Dateitypen": page_file_types,
    "Fehler & Risiken": page_errors_risks,
    "Reports & Exporte": page_reports_exports,
    "Konfiguration": lambda _r: page_config_new(),
    "Run Commands": lambda _r: page_run_commands_new(),
}

handler = NEW_ROUTER.get(page)
if handler:
    handler(selected_run)
else:
    st.error(f"Unbekannte Seite: {page}")

