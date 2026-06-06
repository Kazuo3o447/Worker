# Projektstatus – GEMA Storage Classification Pilot

> **Stand:** 2026-06-06  
> **Worker-Name:** Andre3000  
> **Phase:** 6 – Extraction (antiword/PyMuPDF) + Groq AI Live + needs_ai Retry-Logik  
> **Session-Ergebnis:** Vollständige End-to-End-Pipeline getestet. 379 Tests grün ✅  

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
| `config.py` | 23-Felder-Dataclass aus Umgebungsvariablen; inkl. `ai_token_estimation_safety_factor`, `pdf_max_pages` | ✅ |
| `worker.py` | Orchestriert `run_scan` und `run_classify`; zählt nur verarbeitete Blobs für `max_files`; `retry_recommended`-Tracking | ✅ |
| `classifier_rules.py` | Pfad-basierte Regeln + **needs_ai Retry**: `status=classified + needs_ai=true` → erneut verarbeiten | ✅ |
| `ai_policy.py` | Konservative Policy: blockiert AI wenn Regel ausreicht; Budget-Check; Extension-Blocklist | ✅ |
| `models.py` | `BlobRecord`, `RuleResult`, `ClassificationResult` (35+ Felder), `RunSummary` (40+ Felder inkl. Retry/Token-Felder) | ✅ |
| `app/reports.py` | Baut 10 Report-Dateien als `bytes`; inkl. `retry_recommended`, Token Raw/Buffered, `needs_ai_count` | ✅ |
| `app/file_type_router.py` | Dateityp-Router: route_strategy (text/legacy_office/pdf_text/ocr/vision/archive/binary); ai_allowed; extraction_required | ✅ |
| `app/validation.py` | Validiert 8 Tags (inkl. `needs_ai`) + Metadaten vor jedem Azure-Schreibzugriff | ✅ |
| `logging_utils.py` | Strukturiertes JSON-Logging; Events nach Azure | ✅ |
| `azure_blob_repository.py` | Blob-Listing, Tag-Schreiben, Metadata-Schreiben, Report-Upload; `allow_unencrypted_storage=True` | ✅ |
| `azure_storage.py` | Azure SDK Client-Factory; Token-Cache mit `msal-extensions` | ✅ |
| `app/ai/providers/groq_client.py` | Groq-Provider (llama-3.3-70b-versatile); Token-Tracking (raw+provider_usage); Safety Factor | ✅ |
| `app/ai/providers/base.py` | Provider-Protocol; `estimate_tokens()`; `AiClassificationRequest/Response` | ✅ |
| `app/extraction/legacy_office.py` | `.docx` (python-docx) + **`.doc` (antiword via subprocess)** | ✅ |
| `app/extraction/pdf_extractor.py` | **PDF (PyMuPDF/fitz)** in-memory; verschlüsselt-Check; max_pages konfigurierbar | ✅ |
| `app/extraction/router.py` | Dispatch nach strategy; PDF-Stub ersetzt durch echten Extraktor | ✅ |

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
| `test_classifier_rules.py` | Regellogik, Pfad-Matching, Extension-Erkennung, **needs_ai Retry** | ✅ |
| `test_ai_policy.py` | Policy-Entscheidungen, Budget, Blocklist, **budget_exhausted Retry**, **Token-Schätzung** | ✅ |
| `test_reports.py` | Report-Generierung, CSV-Struktur, JSON-Inhalt, **neue Retry/Token-Felder** | ✅ |
| `test_validation.py` | Tag-Validierung, Metadaten-Validierung | ✅ |
| `test_untagged_detection.py` | Ungetaggte-Datei-Erkennung | ✅ |
| `test_file_type_router.py` | Dateityp-Router: route_strategy, ai_allowed, extraction_required, 60 Fälle | ✅ |
| `test_extraction.py` | antiword (`.doc`), PyMuPDF (`.pdf`), Timeouts, tool_missing | ✅ |
| `test_extraction_safety.py` | Sicherheitsregeln Extraction (kein shell=True, tempfile cleanup) | ✅ |
| `test_ai_providers.py` | Groq-Provider Mocks, Schema-Validierung, Token-Felder | ✅ |
| `test_ai_dryrun.py` | AI in dry_run: Ergebnis in Report, kein Tag-Write | ✅ |

**Gesamt: 379 Tests – alle grün ✅**

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
| `status` | `new` \| `classified` \| `error` \| `unreadable` \| `skipped` \| `pending_ai` |
| `class` | `br` \| `dsgvo` \| `hr` \| `finance` \| `contract` \| `technical` \| `unknown` \| `unreadable` |
| `dsgvo` | `true` \| `false` |
| `archive_candidate` | `true` \| `false` |
| `confidence` | `0`..`100` |
| `readable` | `true` \| `false` |
| `llm_used` | `true` \| `false` – `true` wenn Groq/Foundry verwendet |
| `needs_ai` | `true` \| `false` – `true` wenn class=unknown oder confidence < threshold. **Bei `needs_ai=true` wird die Datei beim nächsten Lauf erneut verarbeitet (ohne `--force`)** |

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
- 8 Report-Dateien nach Azure hochgeladen; keine Writes an Blobs

### Run 2 – Dry-Run Classify (`20260605T091356Z`)
```
--mode classify --prefix "_root_part000/" --max-files 50 --dry-run
```
- 50 Blobs verarbeitet, alle `class=unknown`, `confidence=30`
- `dry_run=true` → 0 Azure-Schreiboperationen an Blobs

### Run 3 – Extraction Dry-Run (`20260606T065736Z`)
```
--mode classify --prefix "_root_part000/" --max-files 5 --dry-run
```
- `extraction_method_counts: antiword:5` bestätigt
- antiword und PyMuPDF in Docker verfügbar

### Run 4 – Erster Groq AI Write Test (`20260606T070804Z`)
```
--mode classify --prefix "_root_part000/" --max-files 10
```
- `ai_calls_used=3` (Limit: `AI_MAX_CALLS_PER_RUN=3`)
- Klassifikationen: **finance×2, contract×1** (conf=90)
- 7 Dateien `budget_exhausted` → `class=unknown, needs_ai=true, llm_used=false`
- `extraction_method_counts: antiword:3`; `ai_total_tokens=2532`

### Run 5 – AI Retry Test (`20260606T072012Z`)
```
--mode classify --prefix "_root_part000/" --max-files 10
```
- Limit erhöht auf `AI_MAX_CALLS_PER_RUN=10`
- Alle 10 `needs_ai=true`-Dateien wurden erkannt und erneut verarbeitet
- `ai_calls_used=10`, `ai_calls_skipped=0`, `budget_exhausted=0`
- `files_unknown=0`, `needs_ai_count=0` nach Retry
- Klassifikationen: **finance×4, hr×4, contract×2** (conf 80–90)
- `ai_total_tokens=7972`; `ai_estimated_tokens_buffered=8295` (Safety Factor 1.4 hält)

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

## 11. Behobene Bugs – Phase 6 (2026-06-06)

| # | Datei | Problem | Fix |
|---|---|---|---|
| 1 | `azure_blob_repository.py` + `azure_storage.py` | Docker: `libsecret`-Fehler → 9× Login pro Session | `allow_unencrypted_storage=True` in `TokenCachePersistenceOptions`; `msal-extensions>=1.0.0` |
| 2 | `Dockerfile` | `/nonexistent` Permission Error (kein Home-Dir für `worker`-User) | `--home /home/worker`, `mkdir -p`, `ENV HOME=/home/worker` |
| 3 | `app/extraction/legacy_office.py` | `.doc`-Dateien hatten keinen Extraktor → `ai_calls_used=0` immer | antiword via `subprocess.run` (kein `shell=True`); tempfile in `finally` gelöscht |
| 4 | `app/extraction/` | PDF hatte Stub `not_implemented` | `pdf_extractor.py` mit PyMuPDF/fitz (in-memory) |
| 5 | `app/classifier_rules.py` | `status=classified + needs_ai=true` → silent skip → KI nie nachgeholt | Neue Prüfung: `needs_ai=true` erlaubt Retry ohne `--force` |
| 6 | `app/worker.py` | `needs_ai_val` nach `retry_recommended_val` berechnet → `UnboundLocalError` | Reihenfolge getauscht |
| 7 | `app/worker.py` | Token-Schätzung ohne Sicherheitspuffer: +36% Abweichung zu echten Tokens | Safety Factor 1.4; neue Felder `ai_estimated_prompt_tokens_raw/buffered` |

## 11b. Behobene Bugs – Phase 1–5 (historisch)

| # | Datei | Problem | Fix |
|---|---|---|---|
| 1 | `app/config.py` | Duplicate Phase-2-Config-Klasse | Alte Klasse entfernt |
| 2 | `app/config.py` | `STORAGE_ACCOUNT` statt `AZURE_STORAGE_ACCOUNT` | Env-Var korrigiert |
| 3 | `app/worker.py` | `classify_blob` mit 3 statt 1 Argument | Signatur korrigiert |
| 4 | `app/worker.py` | `max_files` zählte alle gesehenen Blobs | Zählt jetzt nur verarbeitete |
| 5 | `app/worker.py` | Tags `readable`, `llm_used` fehlten | Hinzugefügt |
| 6 | `app/models.py` | `RunSummary` hatte 13 Felder zu wenig | Alle Felder ergänzt |
| 7 | `frontend/app.py` | `from frontend.config import ...` schlägt im Container fehl | `try/except ModuleNotFoundError` |
| 8 | `frontend/app.py` | `DeviceCodeCredential` blockiert Streamlit-Script-Runner | Background-Thread + Polling |

---

## 12. Nächste Schritte

### Prio 1 – PDF-Test (sofort umsetzbar)
```bash
docker compose run --rm worker --mode classify --prefix "_root_part000/102129" --max-files 1
```
Die 3 PDFs in `_root_part000/` (`102129.pdf`, `1133248.pdf`, `1235690.pdf`) haben noch `status=NO_STATUS`.

### Prio 2 – Größerer Lauf
```bash
docker compose run --rm worker --mode classify --prefix "_root_part000/" --max-files 50
```
Bereits klassifizierte Dateien (`needs_ai=false`) werden korrekt übersprungen.

### Prio 3 – AI_MAX_CALLS_PER_RUN erhöhen
Für Batch-Klassifizierung: `AI_MAX_CALLS_PER_RUN=20` in `.env` setzen.

### Mittelfristig
| Aufgabe | Priorität |
|---|---|
| PDF-Test (PyMuPDF live) | Hoch |
| AI_MAX_CALLS_PER_RUN auf 20–50 erhöhen | Hoch |
| Azure Container Apps Deployment | Mittel |
| Dashboard: Retry/needs_ai-Spalten anzeigen | Mittel |
| CI/CD Pipeline (GitHub Actions) | Niedrig |

---

## 13. Wichtige Befehle

```bash
# Tests ausführen
python -m pytest tests/ -q

# Docker Image bauen (nach Code-Änderungen)
docker compose build worker

# Scan (read-only, kein Azure-Write)
docker compose run --rm worker --mode scan --prefix "_root_part000/" --max-files 50

# Dry-Run Classify (kein Azure-Write an Blobs)
docker compose run --rm worker --mode classify --prefix "_root_part000/" --max-files 10 --dry-run

# Echter Classify (schreibt Tags + Metadata)
docker compose run --rm worker --mode classify --prefix "_root_part000/" --max-files 10

# Gezielter PDF-Test
docker compose run --rm worker --mode classify --prefix "_root_part000/102129" --max-files 1

# Dashboard starten
docker compose up dashboard
```

---

## 14. Dateistruktur

```
storage-classification-pilot/
├── app/                          # Worker-Logik
│   ├── main.py                   # CLI-Einstiegspunkt
│   ├── config.py                 # Umgebungsvariablen → Config Dataclass (23 Felder)
│   ├── worker.py                 # run_scan / run_classify; retry_recommended-Tracking
│   ├── classifier_rules.py       # Pfad-basierte Regeln + needs_ai Retry
│   ├── ai_policy.py              # AI-Aufruf-Entscheidung
│   ├── models.py                 # BlobRecord, RuleResult, ClassificationResult, RunSummary
│   ├── reports.py                # 10 Report-Dateien bauen; retry/token Felder
│   ├── validation.py             # Tag + Metadata Validierung
│   ├── logging_utils.py          # Structured JSON Logging
│   ├── azure_blob_repository.py  # Azure SDK Operationen
│   ├── azure_storage.py          # Client-Factory; msal-extensions Token-Cache
│   ├── file_type_router.py       # Dateityp-Router
│   ├── ai/
│   │   └── providers/
│   │       ├── base.py           # AiProvider Protocol; estimate_tokens()
│   │       ├── groq_client.py    # Groq-Provider (llama-3.3-70b-versatile)
│   │       └── azure_foundry_client.py  # Azure AI Foundry (konfigurierbar)
│   └── extraction/
│       ├── router.py             # Dispatch nach strategy
│       ├── legacy_office.py      # .docx (python-docx) + .doc (antiword)
│       ├── pdf_extractor.py      # PDF (PyMuPDF/fitz) in-memory
│       ├── direct_text.py        # .txt/.csv direkt
│       ├── safety.py             # Sicherheitsregeln für Extraction
│       └── models.py             # ExtractionResult Dataclass
├── frontend/                     # Streamlit Admin-Cockpit
│   ├── app.py                    # 10 Bereiche
│   ├── config.py
│   ├── azure_report_repository.py
│   ├── components.py
│   ├── Dockerfile
│   └── requirements.txt
├── tests/                        # 379 Tests
├── docs/                         # Testberichte + Architektur
├── Dockerfile                    # Worker Container (antiword + PyMuPDF)
├── docker-compose.yml
├── .env                          # Lokale Konfiguration (nicht in Git)
├── .env.example
└── requirements.txt
```
