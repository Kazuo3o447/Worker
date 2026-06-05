# Projektstatus – GEMA Storage Classification Pilot

> **Stand:** 2026-06-05  
> **Worker-Name:** Andre3000  
> **Phase:** 5 – Admin-Cockpit, Dateityp-Router, Admin-Reports  
> **Session-Ergebnis:** Admin-Cockpit (10 Seiten), Dateityp-Router, Admin-Report JSON/PDF erweitert · 253 Tests grün ✅

---

## 1. Überblick

Der GEMA Storage Classification Pilot ist ein **Azure-first Batch-Klassifizierungs-Worker**, der Blob-Dateien im Azure Blob Storage automatisiert mit Metadaten und Index-Tags versieht. Das Dashboard zeigt die Ergebnisse in einer Streamlit-Web-UI direkt aus Azure an.

### Kernprinzipien
- **Azure-only**: Alle Reports landen in Azure (`reports/pilot-v0.1/<run_id>/`) – kein lokales Dateisystem als Primärpfad
- **Read-only Dashboard**: Das Dashboard schreibt nie in Azure; kein `set_blob_tags`, kein `classify_blob`
- **Dry-run sicher**: `--dry-run` blockiert alle Azure-Schreiboperationen zu 100 %
- **Scan-Modus sicher**: `--mode scan` nimmt keine Änderungen vor
- **AI standardmäßig deaktiviert**: `ENABLE_AI=false` in `.env`

---

## 2. Infrastruktur & Azure

| Ressource | Wert |
|---|---|
| Azure Storage Account | `stgemaclasspilot001` |
| Source Container | `cool-stage-test` |
| Report Container | `reports` |
| Quarantine Container | `quarantine-test` |
| Resource Group | `rg-gema-storage-classification-pilot` |
| Auth-Modus (Docker) | `device_code` (Browser-Login via https://login.microsoft.com/device) |
| Reports-Pfad | `reports/pilot-v0.1/<run_id>/` |
| Worker Version | `pilot-v0.1` |

---

## 3. Architektur

```
┌─────────────────────────────────────────────────────────┐
│                    docker-compose.yml                   │
│                                                         │
│  ┌──────────────────────┐   ┌───────────────────────┐  │
│  │  worker (profile)    │   │  dashboard (Port 8501) │  │
│  │  python:3.12-slim    │   │  python:3.12-slim      │  │
│  │  app/ → /app/app/    │   │  frontend/ → /app/     │  │
│  │  ENTRYPOINT: main.py │   │  CMD: streamlit app.py │  │
│  └──────────┬───────────┘   └──────────┬─────────────┘  │
│             │                          │ (read-only)     │
└─────────────┼──────────────────────────┼─────────────────┘
              │ write tags/metadata       │ list + download reports
              ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│              Azure Blob Storage                          │
│  cool-stage-test/          reports/pilot-v0.1/<run_id>/ │
│  _root_part000/*.doc       run-summary.json             │
│                            details.csv                  │
│                            errors.csv                   │
│                            untagged.csv                 │
│                            samples.csv                  │
│                            ai-candidates.csv            │
│                            events.jsonl                 │
│                            summary-kv.csv               │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Codebase – Modulübersicht

### Worker (`app/`)

| Datei | Funktion | Status |
|---|---|---|
| `main.py` | CLI-Einstiegspunkt; `--mode`, `--max-files`, `--prefix`, `--dry-run`, `--force`, `--enable-ai` | ✅ |
| `config.py` | 21-Felder-Dataclass aus Umgebungsvariablen; `AZURE_STORAGE_ACCOUNT` | ✅ |
| `worker.py` | Orchestriert `run_scan` und `run_classify`; zählt nur verarbeitete Blobs für `max_files` | ✅ |
| `classifier_rules.py` | Pfad-basierte Regeln, kein Content-Download; 6 Regeln + Fallback `unknown` | ✅ |
| `ai_policy.py` | Konservative Policy: blockiert AI wenn Regel ausreicht; Budget-Check; Extension-Blocklist | ✅ |
| `ai_foundry_client.py` | Azure AI Foundry Client (derzeit deaktiviert) | ✅ |
| `models.py` | `BlobRecord`, `RuleResult`, `ClassificationResult` (30 Felder), `RunSummary` (33 Felder) | ✅ |
| `app/reports.py` | Baut 10 Report-Dateien als `bytes`; admin-report.json (risk_assessment, file_type_distribution, worker_version) + admin-report.pdf | ✅ |
| `app/file_type_router.py` | Dateityp-Router: route_strategy (text/legacy_office/ocr/vision/archive/binary); ai_allowed; extraction_required | ✅ |
| `app/validation.py` | Validiert 8 Tags (inkl. `needs_ai`) + Metadaten vor jedem Azure-Schreibzugriff | ✅ |
| `logging_utils.py` | Strukturiertes JSON-Logging; Events nach Azure | ✅ |
| `azure_blob_repository.py` | Blob-Listing, Tag-Schreiben, Metadata-Schreiben, Report-Upload | ✅ |
| `azure_storage.py` | Azure SDK Client-Factory | ✅ |

### Dashboard (`frontend/`)

| Datei | Funktion | Status |
|---|---|---|
| `app.py` | Streamlit Admin-Cockpit; **10 Seiten** (Cockpit, Runs, Run Detail, Klassifizierung, KI Readiness, Dateien & Dateitypen, Fehler & Risiken, Reports & Exporte, Konfiguration, Run Commands); Health-Ampel; Background-Auth-Thread | ✅ |
| `config.py` | Frontend-Config inkl. `worker_name`, `source_container`, `default_prefix` | ✅ |
| `azure_report_repository.py` | Read-only Azure Client; `list_runs`, `get_report_json`, `get_report_csv`, `report_exists`, `list_report_files`, `get_report_bytes` | ✅ |
| `components.py` | Wiederverwendbare UI-Komponenten | ✅ |

### Tests (`tests/`)

| Datei | Tests | Status |
|---|---|---|
| `test_classifier_rules.py` | Regellogik, Pfad-Matching, Extension-Erkennung | ✅ |
| `test_ai_policy.py` | Policy-Entscheidungen, Budget, Blocklist | ✅ |
| `test_reports.py` | Report-Generierung, CSV-Struktur, JSON-Inhalt | ✅ |
| `test_validation.py` | Tag-Validierung, Metadaten-Validierung | ✅ |
| `test_untagged_detection.py` | Ungetaggte-Datei-Erkennung | ✅ |
| `test_file_type_router.py` | Dateityp-Router: route_strategy, ai_allowed, extraction_required, 60 Fälle | ✅ |

**Gesamt: 253 Tests – alle grün ✅**

---

## 5. Klassifizierungsregeln

Pfad-basiert, kein Content-Download – erste Übereinstimmung gewinnt:

| Klasse | Keywords | DSGVO | Archiv | Confidence | Reason Code |
|---|---|---|---|---|---|
| `br` | `betriebsrat`, `br_`, `/br/` | true | true | 90 | `path_rule_betriebsrat` |
| `dsgvo` | `dsgvo`, `datenschutz` | true | true | 85 | `path_rule_dsgvo` |
| `hr` | `personal`, `/hr/`, `human resources` | true | true | 80 | `path_rule_hr` |
| `finance` | `rechnung`, `finanz`, `buchhaltung`, `invoice` | false | true | 80 | `path_rule_finance` |
| `contract` | `vertrag`, `vereinbarung`, `contract` | false | true | 75 | `path_rule_contract` |
| `technical` | `.ps1`, `.json`, `.xml`, `.config`, `.sql`, ... | false | false | 70 | `path_rule_technical` |
| `unknown` | kein Match | false | false | 30 | `no_rule_match` |

---

## 6. Blob Index Tags (8 Tags pro Blob)

| Tag-Key | Wertebereich |
|---|---|
| `status` | `new` \| `classified` \| `error` \| `unreadable` \| `skipped` |
| `class` | `br` \| `dsgvo` \| `hr` \| `finance` \| `contract` \| `technical` \| `unknown` \| `unreadable` |
| `dsgvo` | `true` \| `false` |
| `archive_candidate` | `true` \| `false` |
| `confidence` | `0`..`100` |
| `readable` | `true` \| `false` |
| `llm_used` | `true` \| `false` |
| `needs_ai` | `true` \| `false` – gesetzt wenn `class=unknown`, `confidence < threshold`, oder `reason_code=no_rule_match` |

Azure Blob Index Tag Limit: 10. Aktuell: 8 Tags.

---

## 7. Report-Dateien (pro Run)

Pfad in Azure: `reports/pilot-v0.1/<run_id>/`

| Datei | Inhalt |
|---|---|
| `run-summary.json` | Kennzahlen inkl. `worker_name`, `dry_run`, `reports_uploaded` |
| `classification-details.csv` | Pro-Blob-Ergebnis inkl. `needs_ai`-Spalte |
| `classification-errors.csv` | Blobs mit `action=error` |
| `untagged-files.csv` | Blobs ohne `status`-Tag |
| `classification-samples.csv` | Stichproben je Klasse (max. 20 pro Gruppe) |
| `ai-candidates.csv` | KI-Kandidaten (auch wenn KI deaktiviert) |
| `run-events.jsonl` | Structured JSON Log aller Worker-Ereignisse |
| `classification-summary.csv` | Key-Value-Metriken des Laufs |
| `admin-report.json` | Konsolidierter Admin-Report (alle Kennzahlen, KI-Readiness, next actions) |
| `admin-report.pdf` | Lesbarer Admin-Report für Menschen (ReportLab) |

---

## 8. Laufende Infrastruktur

### Docker Images

| Image | Basis | Größe | Status |
|---|---|---|---|
| `storage-classification-pilot-worker` | `python:3.12-slim` | ~251 MB | ✅ gebaut |
| `storage-classification-pilot-dashboard` | `python:3.12-slim` | ~806 MB | ✅ gebaut |

### Sicherheit
- Beide Container laufen als **non-root** (`worker` / `dashboard`)
- Kein `local-reports`-Volume
- API Keys nie geloggt (markiert als `never logged` in Config)

---

## 9. Durchgeführte Runs

### Run 1 – Scan (`20260605T090242Z`)
```
--mode scan --prefix "_root_part000/" --max-files 50
```
- 50 Blobs gesehen (`.doc`-Dateien mit numerischen Namen)
- 8 Report-Dateien nach Azure hochgeladen
- Keine Writes an Blobs

### Run 2 – Dry-Run Classify (`20260605T091356Z`)
```
--mode classify --prefix "_root_part000/" --max-files 50 --dry-run
```
- 50 Blobs verarbeitet, alle klassifiziert
- 100 % `class=unknown`, `confidence=30`, `reason_code=no_rule_match`
- `dry_run=true` → 0 Azure-Schreiboperationen an Blobs
- 8 Reports nach Azure hochgeladen
- `reports_uploaded=true`

**Erkenntnis:** Alle Dateien in `_root_part000/` haben rein numerische Namen (z. B. `100001_24042013 155126.doc`) → keine Regel trifft → `unknown`. Für echte Klassifizierung wird KI oder Content-Analyse benötigt.

---

## 10. Dashboard – Aktueller Stand

| Aspekt | Status |
|---|---|
| Streamlit-Server | ✅ läuft auf `http://localhost:8501` |
| Azure-Auth (device_code) | ✅ Background-Thread; Device-Code erscheint in UI und Container-Logs |
| Import-Kompatibilität (lokal + Docker) | ✅ `try/except ModuleNotFoundError` in `app.py` und `azure_report_repository.py` |
| UI zeigt Device-Code-Login | ✅ Link + Code in Streamlit-Info-Box |
| Auto-Reload nach Login | ✅ `st.rerun()` jede Sekunde bis Auth fertig |
| Admin-Cockpit (10 Bereiche) | ✅ Cockpit, Runs, Run Detail, Klassifizierung, KI Readiness, Dateien & Dateitypen, Fehler & Risiken, Reports & Exporte, Konfiguration, Run Commands |
| Health-Ampel | ✅ Grün/Gelb/Rot basierend auf errors/unknown/ai_candidates |
| Empfohlene nächste Aktionen | ✅ Narrativ aus admin-report.json oder berechnet |
| Run-Tabelle (alle Läufe) | ✅ Tabelle mit Filtern auf der Runs-Seite |
| Live PDF Compilation | ✅ Generiert PDF on-the-fly mit Layoutwechsel und Vektorgrafiken live aus CSV-Ergebnissen |
| GEMA Enterprise Style | ✅ Seriöser und professioneller Look unter Verzicht auf bunte/verspielte Emojis sowie einheitlicher Farbwahl |
| Download-Center | ✅ PDF, JSON, 6 CSVs, JSONL auf Reports & Exporte |

### Bekannter Login-Flow
1. Dashboard starten: `docker compose up dashboard` (aus dem Projektverzeichnis)
2. Browser öffnet `http://localhost:8501`
3. UI zeigt: **Öffne https://login.microsoft.com/device · Code eingeben: `XXXXXXXXX`**
4. Login mit Azure-Account abschließen
5. Dashboard lädt automatisch Runs aus Azure

---

## 11. Behobene Bugs (diese Session)

| # | Datei | Problem | Fix |
|---|---|---|---|
| 1 | `app/config.py` | Duplicate Phase-2-Config-Klasse | Alte Klasse entfernt |
| 2 | `app/config.py` | `STORAGE_ACCOUNT` statt `AZURE_STORAGE_ACCOUNT` | Env-Var korrigiert |
| 3 | `app/worker.py` | `classify_blob` mit 3 statt 1 Argument aufgerufen | Signatur korrigiert |
| 4 | `app/worker.py` | `max_files` zählte alle gesehenen Blobs | Zählt jetzt nur verarbeitete |
| 5 | `app/worker.py` | Tags `readable`, `llm_used` fehlten | Hinzugefügt (7 Tags total) |
| 6 | `app/worker.py` | Metadata `original_path`, `model_name`, `processed_at` fehlten | Hinzugefügt |
| 7 | `app/worker.py` | `rule_class` in AI-Kandidaten-Zeile war post-AI | `rule_class_before_ai` eingefügt |
| 8 | `app/worker.py` | AI-Fehler setzte nicht `action="error"` | Korrigiert |
| 9 | `app/models.py` | `RunSummary` hatte 13 Felder zu wenig | Alle 33 Felder ergänzt |
| 10 | `app/logging_utils.py` | Doppelte `_emit`/`_now_iso`/Helper-Funktionen | Zweite Kopie entfernt |
| 11 | `.env.example` | `WORKER_VERSION=v0` | `pilot-v0.1` |
| 12 | `.env.example` | `DEFAULT_PREFIX` leer | `_root_part000/` |
| 13 | `Dockerfile` + `frontend/Dockerfile` | `mkdir -p local-reports` | Entfernt |
| 14 | `frontend/report_loader.py` | Veralteter lokaler File-Reader | Datei gelöscht |
| 15 | `app/logging_utils.py` | `log_run_finished`: `run_id` doppelt übergeben → `TypeError` | Explizites `run_id=` entfernt |
| 16 | `docker-compose.yml` | `command: streamlit run frontend/app.py` | Zu `app.py` korrigiert |
| 17 | `frontend/app.py` + `azure_report_repository.py` | `from frontend.config import ...` schlägt im Container fehl | `try/except ModuleNotFoundError` |
| 18 | `frontend/app.py` | `DeviceCodeCredential` blockiert Streamlit-Script-Runner | Background-Thread + Polling + Device-Code in UI |

---

## 12. Nächste Schritte

### Prio 1 – Content Extraction (direkt umsetzbar)
```bash
# Content Extraction Light: .doc-Inhalte extrahieren → danach KI möglich
docker compose run --rm worker --mode classify --prefix "_root_part000/" --max-files 10 --dry-run
```

### Prio 2 – AI Dry Run
```bash
# KI Dry Run mit 5 Dateien – kein Azure-Write, KI-Aufrufe gegen Foundry
docker compose run --rm worker --mode classify --dry-run \
  --enable-ai --ai-provider foundry --ai-max-calls 5 --max-files 5
```

### Prio 3 – Echter Mini-Run
```bash
# Echter Mini-Run – schreibt Tags an 10 Blobs (reversibel mit --force)
docker compose run --rm worker --mode classify --prefix "_root_part000/" --max-files 10
```
⚠️ **Dieser Run schreibt** `class=unknown, confidence=30, status=classified` als Blob Index Tags.  
Reversibel mit erneutem Run + `--force`.

### Mittelfristig
| Aufgabe | Priorität |
|---|---|
| Content Extraction Light implementieren | Hoch |
| AI-Integration testen (Azure AI Foundry, `--enable-ai`) | Hoch |
| `route_strategy` in classification-details.csv schreiben | Mittel |
| Weitere Prefixes / Container scannen | Mittel |
| Azure Container Apps Deployment (siehe `docs/azure-container-apps-plan.md`) | Mittel |
| AdminLTE Prototyp evaluieren (nach KI-Integration) | Niedrig |
| CI/CD Pipeline (GitHub Actions) | Niedrig |

---

## 13. Wichtige Befehle

```bash
# Verzeichnis wechseln
cd "c:\Users\g103010\Desktop\Worker\storage-classification-pilot"

# Tests ausführen
python -m pytest tests/ -q

# Docker Images bauen
docker compose build

# Scan (read-only, kein Azure-Write)
docker compose run --rm worker --mode scan --prefix "_root_part000/" --max-files 50

# Dry-Run Classify (kein Azure-Write an Blobs, Reports gehen nach Azure)
docker compose run --rm worker --mode classify --prefix "_root_part000/" --max-files 50 --dry-run

# Dashboard starten
docker compose -f docker-compose.yml --project-directory . up dashboard

# Container-Logs
docker logs storage-classification-pilot-dashboard-1 -f
```

---

## 14. Dateistruktur

```
storage-classification-pilot/
├── app/                          # Worker-Logik
│   ├── main.py                   # CLI-Einstiegspunkt
│   ├── config.py                 # Umgebungsvariablen → Config Dataclass
│   ├── worker.py                 # run_scan / run_classify
│   ├── classifier_rules.py       # Pfad-basierte Regeln
│   ├── ai_policy.py              # AI-Aufruf-Entscheidung
│   ├── ai_foundry_client.py      # Azure AI Foundry Client
│   ├── models.py                 # BlobRecord, RuleResult, ClassificationResult, RunSummary
│   ├── reports.py                # 8 Report-Dateien bauen
│   ├── validation.py             # Tag + Metadata Validierung
│   ├── logging_utils.py          # Structured JSON Logging
│   ├── azure_blob_repository.py  # Azure SDK Operationen
│   └── azure_storage.py          # Client-Factory
├── frontend/                     # Streamlit Admin-Cockpit
│   ├── app.py                    # Hauptdatei, 10 Bereiche (Cockpit…Run Commands)
│   ├── config.py                 # Frontend-Config
│   ├── azure_report_repository.py # Read-only Azure Client (6 Methoden)
│   ├── components.py             # UI-Komponenten
│   ├── Dockerfile
│   └── requirements.txt
├── tests/                        # 253 Tests
├── docs/                         # 7 Dokumente
├── Dockerfile                    # Worker Container
├── docker-compose.yml            # worker + dashboard Services
├── .env                          # Lokale Konfiguration (nicht in Git)
├── .env.example                  # Vorlage
└── requirements.txt              # Worker-Abhängigkeiten
```
