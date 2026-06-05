# Architektur – GEMA Storage Classification Pilot v0 (Phase 4)

## Überblick

```
┌────────────────────────────────────────────────────────────────────┐
│  GEMA Azure Blob Storage Classification Pilot                      │
│                                                                    │
│  ┌──────────────┐   Tags +    ┌──────────────────────────────┐    │
│  │   Worker     │──Metadata──▶│  Azure Blob Storage           │    │
│  │ (Batch Job)  │             │  stgemaclasspilot001          │    │
│  │              │─Reports────▶│  ├── cool-stage-test (source) │    │
│  └──────────────┘             │  ├── reports (output)         │    │
│                               │  │   pilot-v0.1/<run_id>/    │    │
│  ┌──────────────┐             │  └── quarantine-test          │    │
│  │  Dashboard   │──liest─────▶└──────────────────────────────┘    │
│  │  (read-only) │                                                  │
│  │  Port 8501   │                                                  │
│  └──────────────┘                                                  │
└────────────────────────────────────────────────────────────────────┘
```

**Kein lokaler reports-Ordner.** Reports werden ausschließlich nach Azure hochgeladen.

## Komponenten

### Worker (app/)

- **Sprache**: Python 3.12+
- **Ausführung**: Docker-Container, manuell gestartet (kein Dauerläufer)
- **Aufgaben**:
  - Blobs in `cool-stage-test` auflisten
  - Blob Index Tags lesen (aktuellen Status ermitteln)
  - Ungetaggte / retry-fähige Blobs erkennen
  - **Dateityp-Router** ausführen (`app/file_type_router.py`): Extraktionsstrategie bestimmen, ai_allowed/ocr_required/vision_required setzen
  - Regelbasiert klassifizieren (Pfad + Extension, kein Dateiinhalt)
  - Optional: KI-Klassifizierung via Azure AI Foundry (`ENABLE_AI=true`)
  - Blob Index Tags schreiben (7 Tags: class, dsgvo, archive_candidate, confidence, readable, llm_used, status)
  - Blob Metadata schreiben (worker_version, run_id, original_path, reason_code, model_name, processed_at, …)
  - Reports direkt in `reports`-Container hochladen (`pilot-v0.1/<run_id>/`)
  - Strukturierte JSON-Events in Speicher puffern → als `run-events.jsonl` hochladen

### Dashboard (frontend/)

- **Framework**: Streamlit
- **Port**: 8501
- **Dauerläufer**: ja (`docker compose up dashboard`)
- **Aufgaben (nur lesen)**:
  - Reports aus `reports`-Container in Azure laden
  - Runs, Kennzahlen, Klassenverteilung, Fehler, Logs anzeigen
  - KI-Readiness-Analyse
  - Keine Schreiboperationen, kein Blob-Tagging

### Trennungsprinzip

Der Worker ist die **einzige Komponente**, die:
- Blob Index Tags schreibt
- Blob Metadata schreibt
- klassifiziert

Das Dashboard ist **rein lesend** und hat keinen Azure-Schreibzugriff.

## Datenfluss

```
1. Worker startet
   └─▶ enable_event_buffering()  ← Events in Speicher puffern
   └─▶ list_blobs(cool-stage-test) mit Tags
       └─▶ für jeden Blob: should_process_blob(existing_tags)
           ├─ skip → log_blob_skipped
           └─ process → file_type_router.route_blob()  ← Dateityp-Router
               └─▶ FileTypeRoute (strategy, ai_allowed, extraction_required, …)
                   └─▶ classify_blob(blob_name)  ← Regelbasiert
                       └─▶ RuleResult (class, dsgvo, confidence, readable, llm_used)
                           └─▶ ai_policy.should_call_ai()  ← optional (nur wenn ai_allowed=True)
                               └─▶ ai_foundry_client.classify()  ← wenn Kandidat + Budget
                   ├─▶ set_blob_tags(7 Tags)        ← nicht in --dry-run
                   ├─▶ set_blob_metadata(8+ Felder) ← nicht in --dry-run
                   └─▶ ClassificationResult gespeichert

2. Nach Verarbeitung:
   └─▶ ReportWriter.build_all_reports(...)
       ├─▶ run-summary.json          (35 Felder inkl. worker_version, timing)
       ├─▶ classification-details.csv
       ├─▶ classification-summary.csv
       ├─▶ classification-errors.csv
       ├─▶ untagged-files.csv
       ├─▶ classification-samples.csv
       └─▶ ai-candidates.csv
   
   └─▶ run-events.jsonl aus Puffer holen
   └─▶ repo.upload_run_reports() → reports/pilot-v0.1/<run_id>/ in Azure

3. Dashboard liest reports/pilot-v0.1/<run_id>/* aus Azure und zeigt alles an
```

## Authentifizierung

| AUTH_MODE | Mechanismus | Einsatz |
|-----------|------------|---------|
| `connection_string` | `BlobServiceClient.from_connection_string()` | Lokal, Notfall |
| `default` | `DefaultAzureCredential` | Lokal (az login), Azure Managed Identity |
| `device_code` | `DeviceCodeCredential` | Lokal Docker ohne Azure CLI |

## Spätere Azure-Zielarchitektur (v1+)

```
┌─────────────────────────────────────────────────────────────────┐
│  Azure (Subscription: Data Archiv)                              │
│  Resource Group: rg-gema-storage-classification-pilot           │
│                                                                 │
│  ┌────────────────────────────────┐                             │
│  │  Azure Container Apps Job      │ ← Worker (scheduled)        │
│  │  gema-classifier-job           │   Managed Identity           │
│  └────────────────────────────────┘                             │
│                                                                 │
│  ┌────────────────────────────────┐                             │
│  │  Azure Container App           │ ← Dashboard (always-on)     │
│  │  gema-classifier-dashboard     │   Port 8501 / HTTPS          │
│  └────────────────────────────────┘                             │
│                                                                 │
│  ┌────────────────────────────────┐                             │
│  │  Azure Blob Storage            │                              │
│  │  stgemaclasspilot001           │                              │
│  │  ├── cool-stage-test (source)  │                              │
│  │  ├── reports (output)          │                              │
│  │  └── quarantine-test           │                              │
│  └────────────────────────────────┘                             │
│                                                                 │
│  ┌────────────────────────────────┐                             │
│  │  Azure Log Analytics           │ ← stdout → Log Analytics    │
│  │  (Container Apps Logs)         │   via OTLP/Azure Monitor     │
│  └────────────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────┘
```

## Erweiterungen (Roadmap)

| Stufe | Feature |
|-------|---------|
| v0 (jetzt) | Regelbasierte + optionale KI-Klassifikation, Reports nach Azure, Dashboard, **Dateityp-Router** (`file_type_router.py`) |
| v0.5 | Extraction-Router Light (Text aus .docx, .pdf, .txt), needs_ai-Tag, Content-basierte Klassifikation |
| v1 | OCR (Azure Document Intelligence), Vision (GPT-4o), Legacy-Office (.doc via LibreOffice/Tika) |
| v2 | Erweiterte KI-Modelle, Batch-Calls, Konfidenz-Cache, automatischer Trigger (Azure Function) |
| v3 | Lifecycle-Regeln (automatisches Archivieren/Löschen) |
| v4 | Review-Workflow (Fachbereich bestätigt Klassifikation) |
| v5 | Automatischer Azure Container Apps Job (täglich) |
