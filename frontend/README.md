# Andree3000 – Dashboard

Streamlit-Dashboard zur Analyse der Klassifizierungsergebnisse.

## Starten (Docker Compose)

```cmd
docker compose up dashboard
```

Browser: http://localhost:8501

## Starten (lokal)

```cmd
pip install -r requirements.txt
streamlit run app.py
```

## Seiten

| Seite | Beschreibung |
|-------|-------------|
| 🏠 Übersicht | run-summary.json als Kennzahlen |
| 📊 Klassenverteilung | Klassen-Metriken als Tabelle + Balkendiagramm |
| 📋 Details | classification-details.csv mit Filtern |
| ❌ Fehler | classification-errors.csv |
| 🔍 Ungetaggte Dateien | untagged-files.csv |
| 🧪 Stichproben | classification-samples.csv nach Klassen |
| 📝 Logs | run-events.jsonl als strukturierter Log-Viewer |
| 🤖 LLM Readiness | Anteil unknown/low-confidence als LLM-Vorbereitung |
| 🚀 Run Commands | Docker-Befehle zum Kopieren |

## Wichtig

- Das Dashboard schreibt **keine** Blob Tags und **keine** Metadata.
- Das Dashboard klassifiziert **keine** Blobs.
- Das Dashboard kann nur lesen, was der Worker in `local-reports/` geschrieben hat.
- `LOCAL_REPORT_DIR` (env var, Default: `local-reports`) zeigt auf das Report-Verzeichnis.
