"""GEMA Storage Classification Pilot – Streamlit Dashboard.

Zeigt Runs, Kennzahlen, Klassifizierungsdetails, Fehler, Logs und KI-Readiness.
Liest Reports ausschliesslich aus Azure Blob Storage – kein lokaler Reports-Ordner.

Starten: streamlit run frontend/app.py  (oder docker compose up dashboard)
"""

from __future__ import annotations

import pathlib
import threading
import time

import streamlit as st

_DEVICE_CODE_MSG_FILE = pathlib.Path("/tmp/azure_device_code.txt")

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="GEMA Classification Pilot",
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
    st.title("GEMA Classification Pilot")
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

# ---------------------------------------------------------------------------
# Sidebar – run selection & navigation
# ---------------------------------------------------------------------------
st.sidebar.title("GEMA Classification")
st.sidebar.caption(f"Storage Klassifizierungs-Pilot · Worker {repo.config.worker_version}")
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

selected_run = st.sidebar.selectbox(
    "Run auswählen",
    runs,
    index=0,
    help="Neueste Runs stehen oben.",
)

PAGES = [
    "Übersicht",
    "Klassenverteilung",
    "Klassifizierungs-Details",
    "KI-Analyse",
    "Fehler",
    "Ungetaggte Dateien",
    "Stichproben / Review",
    "Logs",
    "LLM Readiness",
    "Run Commands",
]

page = st.sidebar.radio("Navigation", PAGES, label_visibility="collapsed")

st.sidebar.markdown("---")
st.sidebar.caption(f"Run: `{selected_run}`")

import pandas as pd
import components as comp


# ---------------------------------------------------------------------------
# Helper: lazy loaders from Azure
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def _summary(run_id: str) -> dict:
    return repo.get_run_summary(run_id)


@st.cache_data(ttl=60)
def _csv(run_id: str, filename: str) -> pd.DataFrame:
    return repo.get_csv(run_id, filename)


@st.cache_data(ttl=60)
def _events(run_id: str) -> pd.DataFrame:
    return repo.get_events(run_id)


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
# Page: KI-Analyse
# ---------------------------------------------------------------------------

def page_ai_analysis(run_id: str) -> None:
    st.header("KI-Analyse")
    summary = _summary(run_id)
    ai_enabled = summary.get("enable_ai", False)
    ai_provider = summary.get("ai_provider", "none")

    if not ai_enabled or ai_provider == "none":
        st.info(
            "**KI war in diesem Lauf deaktiviert** (`ENABLE_AI=false` oder `AI_PROVIDER=none`).\n\n"
            "Die Tabelle unten zeigt Dateien, die für einen KI-Aufruf in Frage kämen."
        )

    # AI summary metrics
    comp.metric_row({
        "KI-Anbieter": ai_provider,
        "KI-Kandidaten": summary.get("ai_candidates", 0),
        "KI-Aufrufe": summary.get("ai_calls_used", 0),
        "KI-Überspringen": summary.get("ai_calls_skipped", 0),
        "KI-Fehler": summary.get("ai_errors", 0),
    })

    st.divider()

    # ai-candidates.csv
    cand_df = _csv(run_id, "ai-candidates.csv")
    if not cand_df.empty:
        st.subheader(f"KI-Kandidaten ({len(cand_df)} Einträge)")
        with st.expander("Filter", expanded=False):
            cand_df = comp.multiselect_filter(cand_df, "ai_candidate_reason", "Kandidat-Grund")
            cand_df = comp.multiselect_filter(cand_df, "ai_skipped_reason", "Skip-Grund")
            cand_df = comp.multiselect_filter(cand_df, "extension", "Dateiendung")
        comp.show_dataframe(cand_df, height=400)
    else:
        comp.empty_state("ai-candidates.csv nicht gefunden oder kein KI-Kandidat erkannt.")

    # Details: blobs where llm_used=true
    details_df = _csv(run_id, "classification-details.csv")
    if not details_df.empty and "llm_used" in details_df.columns:
        ai_used_df = details_df[details_df["llm_used"] == "true"]
        if not ai_used_df.empty:
            st.divider()
            st.subheader(f"Vom KI klassifiziert ({len(ai_used_df)} Blobs)")
            cols = [c for c in ["blob_name", "class", "confidence", "ai_provider",
                                "ai_reason", "ai_input_chars", "reason_code"]
                    if c in ai_used_df.columns]
            comp.show_dataframe(ai_used_df[cols] if cols else ai_used_df, height=350)

    st.divider()
    st.subheader("Aktivierung")
    st.code("""
# .env oder docker-compose.yml:
ENABLE_AI=true
AI_PROVIDER=foundry
AI_FOUNDRY_ENDPOINT=https://<resource>.openai.azure.com/
AI_FOUNDRY_MODEL_DEPLOYMENT=gpt-4o
AI_MAX_CALLS_PER_RUN=20

# oder CLI-Override:
docker compose run --rm worker --mode classify --enable-ai --ai-provider foundry --ai-max-calls 20
""", language="bash")


# ---------------------------------------------------------------------------
# Page: Run Commands
# ---------------------------------------------------------------------------

def page_run_commands(run_id: str) -> None:
    st.header("Run Commands")
    st.info("Das Dashboard startet den Worker **nicht** selbst. Kopiere die Befehle ins Terminal.")

    st.subheader("1 · Scan (nur lesen, keine Schreiboperationen)")
    st.code("docker compose run --rm worker --mode scan --max-files 50", language="bash")

    st.subheader("2 · Classify – Dry Run (simuliert, kein Write nach Azure)")
    st.code("docker compose run --rm worker --mode classify --dry-run --max-files 50", language="bash")

    st.subheader("3 · Classify – Echtlauf mit 50 Dateien")
    st.code("docker compose run --rm worker --mode classify --max-files 50", language="bash")

    st.subheader("4 · Report aggregieren")
    st.code("docker compose run --rm worker --mode report", language="bash")

    st.subheader("5 · Nur einen Ordner verarbeiten (Prefix)")
    st.code('docker compose run --rm worker --mode classify --prefix "_root_part000/" --max-files 20', language="bash")

    st.subheader("6 · Bereits klassifizierte Dateien erneut verarbeiten (force)")
    st.code("docker compose run --rm worker --mode classify --force --max-files 50", language="bash")

    st.divider()
    st.subheader("Auth-Modi")
    st.markdown("""
| AUTH_MODE | Beschreibung | Wann nutzen |
|-----------|-------------|-------------|
| `device_code` | Browser-Login via Device-Code-URL | Lokaler Docker-Test ohne Azure CLI |
| `default` | DefaultAzureCredential (az login / Managed Identity) | Lokal mit `az login` oder Azure |
| `connection_string` | Direkte Connection String | Nur Notfall, kein Secret ins Repo! |
    """)

    st.divider()
    st.subheader("Späterer Azure-Betrieb")
    st.code("""
# Worker als Azure Container Apps Job starten
az containerapp job start \\
  --name gema-classifier-job \\
  --resource-group rg-gema-storage-classification-pilot \\
  -- --mode classify --max-files 500
""", language="bash")

    st.button("Worker starten (deaktiviert im MVP)", disabled=True,
              help="Startlogik folgt in einer späteren Version.")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

ROUTER = {
    "Übersicht": page_overview,
    "Klassenverteilung": page_class_distribution,
    "Klassifizierungs-Details": page_details,
    "KI-Analyse": page_ai_analysis,
    "Fehler": page_errors,
    "Ungetaggte Dateien": page_untagged,
    "Stichproben / Review": page_samples,
    "Logs": page_logs,
    "Run Commands": page_run_commands,
}

handler = ROUTER.get(page)
if handler:
    handler(selected_run)
else:
    st.error(f"Unbekannte Seite: {page}")
