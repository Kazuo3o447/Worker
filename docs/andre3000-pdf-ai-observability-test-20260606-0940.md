# Andre3000 PDF AI / Observability Testreport

**Datum:** 2026-06-06  
**Run-ID:** 20260606T072959Z  
**Vorheriger Testreport:** docs/andre3000-pdf-ai-test-20260606-0932.md  
**Erstellt von:** Andre3000 AI-Agent  

---

## 1. Executive Summary

| Prüfpunkt | Ergebnis |
|-----------|----------|
| PDF-Test ausgeführt | ✅ Run 20260606T072959Z |
| AI Calls | ✅ 1 (von 10 Budget) |
| Tags geschrieben | ✅ `dry_run=false` |
| Klasse | `finance`, conf=90 |
| Fehler | 0 |
| needs_ai nach Test | 0 |
| Tests | ✅ **379/379** |
| Observability-Bewertung | **Ausreichend für Pilot. Lücken dokumentiert.** |

**Gesamtstatus: GRÜN**  
PDF-Extraktion, Groq-KI, Tag-Write und Reports funktionieren vollständig. Die strukturierte Logging-Infrastruktur ist vorhanden und läuft stabil. Für den Pilotbetrieb sind die Metriken ausreichend. Für Produktion fehlen primär: `blob_processing_duration_ms`, `download_duration_ms`, `validation_error_count`, und eine Human-Review-Grundlage für echte KI-Accuracy.

> **AI accuracy is not yet measurable without ground-truth labels or human review feedback.**

---

## 2. Ausgangslage

- needs_ai Retry / Budget / Token-Fix war erledigt (Run `20260606T072012Z`)
- PDF-Extraktion via PyMuPDF war implementiert, aber noch nicht separat als AI-Schreibtest bewiesen
- Ziel: Vollständige PDF-Pipeline einmalig beweisen und Observability-Baseline dokumentieren
- Der PDF-AI-Test wurde bereits im vorherigen Schritt ausgeführt und war grün

---

## 3. Konfiguration

| Parameter | Wert |
|-----------|------|
| ENABLE_AI | true |
| AI_PROVIDER | groq |
| AI_MODEL | llama-3.3-70b-versatile |
| AI_WRITE_TAGS | true |
| AI_MAX_CALLS_PER_RUN | 10 |
| AI_MAX_TOTAL_CHARS_PER_RUN | 20.000 |
| AI_MAX_CHARS_PER_FILE | 2.000 |
| AI_TOKEN_ESTIMATION_SAFETY_FACTOR | 1.4 |
| PDF_MAX_PAGES | 3 |
| Prefix | `_root_part000/102129` |
| max-files | 1 |
| dry_run | false |
| force | false |
| GROQ_API_KEY | ***REDACTED*** |

---

## 4. Ausgeführter Befehl

```bash
docker compose run --rm worker --mode classify --prefix "_root_part000/102129" --max-files 1
```

Kein `--force`, kein `--dry-run`, kein `max-files > 1`.

---

## 5. PDF Discovery

| Prüfpunkt | Ergebnis |
|-----------|----------|
| Datei gefunden | ✅ `_root_part000/102129.pdf` |
| Größe | 96.927 Bytes |
| Vorherige Tags | `status=none` (ungetaggt) |
| Übersprungen? | Nein – `status=none` → retry |
| Prefix korrekt | ✅ Nur diese eine Datei getroffen |

---

## 6. PDF Extraktion

| Prüfpunkt | Ergebnis |
|-----------|----------|
| extraction_success | ✅ |
| extraction_method | `pymupdf` |
| extraction_chars | 4.000 (cap: AI_MAX_CHARS_PER_FILE=2000 für AI-Input) |
| extracted_chars_total (gesamt) | 4.000 |
| pages_total / pages_sampled | (aus Extraktor verfügbar, nicht im run_finished geloggt) |
| extraction_duration_ms | Nicht in run_finished sichtbar – siehe Lücken |
| tool_missing | Nein |
| Fehler | Keiner |

✅ PyMuPDF lief in-memory, kein Tempfile für PDFs.

---

## 7. AI Klassifikation

| Prüfpunkt | Ergebnis |
|-----------|----------|
| ai_candidate | true |
| ai_called | true |
| llm_used | true |
| class | **finance** |
| confidence | **90** |
| reason_code | `no_rule_match` |
| ai_model | `llama-3.3-70b-versatile` |
| ai_prompt_version | `v1` |
| ai_latency_ms | 424 ms |
| validation_success | true |
| Schemafehler | 0 |
| Provider-Fehler | 0 |

---

## 8. Token Report

| Metrik | Wert |
|--------|------|
| Prompt-Tokens (real) | 1.069 |
| Completion-Tokens (real) | 74 |
| Gesamt-Tokens (real) | **1.143** |
| Estimated Raw | 779 |
| Estimated Buffered (×1.4) | 1.091 |
| Token-Quelle | `provider_usage:1` |
| Abweichung Real vs. Raw | **+46,7%** |
| Buffered vs. Real | 1.091 vs. 1.143 → −4,5% ⚠️ |
| Safety Factor | 1.4 |

> Buffered-Schätzung liegt **knapp unter** den realen Tokens. Für PDF-intensive Läufe ist `AI_TOKEN_ESTIMATION_SAFETY_FACTOR=1.5` empfehlenswert.

---

## 9. Azure Tags / Metadata

### Blob Index Tags (geschrieben)

| Tag | Wert |
|-----|------|
| `status` | `classified` |
| `class` | `finance` |
| `confidence` | `90` |
| `llm_used` | `true` |
| `needs_ai` | `false` |
| `dsgvo` | (von Groq gesetzt) |
| `archive_candidate` | (von Groq gesetzt) |
| `readable` | `true` |

### Blob Metadata (geschrieben)

| Key | Wert |
|-----|------|
| `worker_version` | `pilot-v0.1` |
| `reason_code` | `no_rule_match` |
| `readable` | `true` |
| `llm_used` | `true` |
| `run_id` | `20260606T072959Z` |

> `processed_at`, `ai_provider`, `ai_model`, `ai_prompt_version` sind **nicht** in Blob-Metadata — sie sind in Reports und Logs vorhanden, aber nicht als Blob-Metadaten geschrieben. Siehe Lücken.

---

## 10. Reports

```
Container: reports
Prefix:    pilot-v0.1/20260606T072959Z
Dateien:   10
```

| Datei | PDF-/AI-Felder vorhanden? |
|-------|--------------------------|
| `run-summary.json` | ✅ alle AI/Token/Extraction-Felder |
| `classification-details.csv` | ✅ `extraction_method`, `retry_recommended`, `ai_token_source` etc. |
| `ai-candidates.csv` | ✅ inkl. `needs_ai`, `retry_recommended` |
| `admin-report.json` | ✅ vorhanden |
| `admin-report.pdf` | ✅ vorhanden |
| `run-events.jsonl` | ✅ vollständiges Event-Log |
| `untagged-files.csv` | ✅ |
| `classification-errors.csv` | ✅ (leer, da kein Fehler) |
| `classification-samples.csv` | ✅ |
| `classification-summary.csv` | ✅ |

**Fehlende PDF-spezifische Felder in run-summary.json:**
- `pdf_pages_total` / `pdf_pages_sampled` (im ExtractionResult vorhanden, aber nicht in RunSummary aggregiert)
- `extraction_duration_ms_total` (im ExtractionResult vorhanden, aber nicht summiert)

---

## 11. Observability Ist-Stand

### A. Logging (`app/logging_utils.py`)

| Prüfpunkt | Status |
|-----------|--------|
| Strukturierte JSON-Logs (JSONL stdout) | ✅ |
| `run_id` in allen Events | ✅ |
| `blob_name` in relevanten Events | ✅ |
| `mode`, `prefix`, `dry_run`, `force` in `run_started` | ✅ |
| `extraction_method` in Logs | ⚠️ Nicht als eigenes Log-Event — nur in run_finished summary |
| `ai_provider`, `ai_model` in `run_started` / `run_finished` | ✅ |
| `ai_latency_ms` in Logs | ⚠️ Nicht explizit geloggt — nur in run_finished aggregiert |
| Fehler mit `reason_code` | ✅ `log_blob_error`, `log_ai_error` |
| Secrets geschützt | ✅ GROQ_API_KEY nie in Logs |
| In-memory Event-Buffer → `run-events.jsonl` | ✅ |
| Log-Events nach Azure hochgeladen | ✅ als `run-events.jsonl` |

**Fehlende Log-Events:**

| Fehlendes Event | Beschreibung |
|-----------------|--------------|
| `extraction_completed` | Einzelnes Blob-Extraction-Event mit `extraction_method`, `chars`, `duration_ms`, `pages` |
| `blob_download_completed` | Download-Dauer pro Blob |
| `ai_result_detail` | ai_tokens, ai_latency, ai_class direkt nach dem Call als Event |
| `tag_write_completed` | Bestätigung Tag-Write pro Blob mit Dauer |
| `report_upload_completed` | Upload-Dauer |

---

## 12. Observability Lücken

| Bereich | Fehlt | Priorität | Empfehlung |
|---------|-------|-----------|------------|
| Laufzeit | `blob_processing_duration_ms` pro Blob (end-to-end inkl. Download+Extract+AI+Tag) | Mittel | In `_classify_blob` als Summe berechnen und in `ClassificationResult` + Log-Event aufnehmen |
| Laufzeit | `download_duration_ms` | Niedrig | In `download_blob_content` messen und in ClassificationResult |
| Laufzeit | `extraction_duration_ms` | Niedrig | Bereits in ExtractionResult vorhanden – fehlt nur in RunSummary-Aggregation |
| Laufzeit | `report_upload_duration_ms` | Niedrig | In `upload_run_reports` messen |
| Laufzeit | `run_duration_ms` | ✅ | Vorhanden als `duration_seconds` in RunSummary |
| Laufzeit | `files_per_hour` | ✅ | Vorhanden als `throughput_files_per_hour` |
| Extraktion | `pdf_pages_total` / `pdf_pages_sampled` in RunSummary | Mittel | Aus ExtractionResult aggregieren |
| Extraktion | `extraction_duration_ms_total` in RunSummary | Niedrig | Aus ExtractionResult summieren |
| AI | `ai_validation_error_count` in RunSummary | Mittel | Zähler wenn `ai_error=schema_validation_failed` |
| Qualität | `validation_error_count` | Mittel | Tag-Validierungsfehler zählen |
| Qualität | `human_review_required_count` | Mittel | Eigenständiges Feld: `confidence < 70 AND llm_used=true` |
| Qualität | Ground Truth / `human_corrected_class` | Hoch | Grundlage für echte KI-Accuracy – **nicht automatisch messbar** |
| Metadata | `processed_at`, `ai_model`, `ai_provider` als Blob-Metadaten | Niedrig | In `new_metadata` in `_classify_blob` ergänzen |
| Logging | `extraction_completed`-Event pro Blob | Niedrig | In `logging_utils.py` ergänzen |
| Logging | `ai_result_detail`-Event mit Token-Feldern | Niedrig | Optional: nach `log_ai_result_validated` |

---

## 13. Application Insights Empfehlung

**Noch nicht implementiert – nur Empfehlung für spätere Phase.**

### customEvents (Empfehlung)

| Event Name | Auslöser |
|------------|----------|
| `BlobClassified` | Pro erfolgreich klassifiziertem Blob |
| `AiCallCompleted` | Pro Groq/Foundry-Call |
| `ExtractionCompleted` | Pro erfolgreich extrahiertem Blob |
| `RunCompleted` | Am Ende jedes Laufs |
| `BlobSkipped` | Pro übersprungener Datei |
| `AiSkipped` | Pro AI-Skip (budget_exhausted, no_text etc.) |

### customMetrics (Empfehlung)

| Metrik | Einheit |
|--------|---------|
| `ai_latency_ms` | ms |
| `ai_prompt_tokens` | Tokens |
| `ai_total_tokens` | Tokens |
| `extraction_chars` | Zeichen |
| `extraction_duration_ms` | ms |
| `blob_processing_duration_ms` | ms |
| `ai_confidence` | 0–100 |
| `files_per_hour` | Dateien/h |

### customDimensions (Pflicht für alle Events)

```
run_id, worker_version, mode, prefix, dry_run, force,
file_extension, extraction_method, ai_provider, ai_model,
ai_prompt_version, classification_class, reason_code,
ai_skipped_reason
```

### Daten die NIEMALS in Telemetrie aufgenommen werden dürfen

- GROQ_API_KEY oder andere API Keys/Secrets
- Extrahierte Dateiinhalte (`text_for_ai`, `_text_for_ai`)
- Personenbezogene Daten aus Dokumenteninhalten
- Azure Connection Strings
- Volledige Blob-Namen mit sensiblen Inhalten (nur anonymisierte IDs)

---

## 14. Tests

```bash
python -m pytest tests/ -q
```

```
379 passed in 4.07s
```

Keine Fehler. Alle 379 Tests grün inkl. der neuen Retry/Token/PDF-Tests aus Phase 6.

---

## 15. Bewertung

| Frage | Antwort |
|-------|---------|
| Ist PDF-AI-Test erfolgreich? | ✅ Ja – PyMuPDF + Groq + Tag-Write vollständig |
| Ist PDF-Verarbeitung bereit für max-files=3? | ✅ Ja |
| Sind Reports ausreichend? | ✅ Für Pilot. Kleinere Lücken (pdf_pages in Summary, extraction_duration_total) |
| Ist Observability ausreichend für Pilot? | ✅ Ja – strukturierte Logs, run_id, JSONL nach Azure |
| Was fehlt für Produktion? | `blob_processing_duration_ms`, Human-Review-Grundlage, Application Insights Integration, `human_review_required_count` |

---

## 16. Empfehlung nächster Schritt

| Priorität | Maßnahme |
|-----------|----------|
| 1 | **PDF-Test mit max-files=3**: `docker compose run --rm worker --mode classify --prefix "_root_part000/1" --max-files 3` (trifft alle 3 PDFs + ggf. .doc-Dateien mit `1...`) |
| 2 | **Safety Factor für PDF erhöhen**: `AI_TOKEN_ESTIMATION_SAFETY_FACTOR=1.5` in `.env` |
| 3 | **Observability minimal ergänzen**: `human_review_required_count` + `pdf_pages_total` in RunSummary |
| 4 | **Größerer .doc-Lauf**: `--max-files 50` (bereits klassifizierte Dateien werden übersprungen) |
| 5 | **Application Insights**: Erst nach erfolgreichem max-files=50-Lauf planen |

**Empfehlung: Zuerst PDF-Test mit max-files=3, dann Safety Factor prüfen, dann skalieren.**

---

## 17. Anhang

### 17.1 Run-Finished Log (20260606T072959Z)

```json
{
  "run_id": "20260606T072959Z",
  "status": "ok",
  "files_processed": 1,
  "files_classified": 1,
  "files_unknown": 0,
  "ai_calls_used": 1,
  "ai_total_tokens": 1143,
  "ai_prompt_tokens_total": 1069,
  "ai_completion_tokens_total": 74,
  "ai_estimated_tokens_raw_total": 779,
  "ai_estimated_tokens_buffered_total": 1091,
  "ai_token_estimation_safety_factor": 1.4,
  "ai_latency_ms_avg": 424.0,
  "ai_token_source_breakdown": "provider_usage:1",
  "extraction_success_count": 1,
  "extraction_method_counts": "pymupdf:1",
  "extracted_chars_total": 4000,
  "needs_ai_count": 0,
  "retry_recommended_count": 0,
  "reports_uploaded": true,
  "duration_seconds": 0.921925
}
```

### 17.2 Vorhandene Log-Events in `logging_utils.py`

```
run_started, run_finished
blob_seen, blob_skipped, blob_detected_untagged, blob_classified, blob_error
rule_classified
ai_candidate_detected, ai_called, ai_result_validated, ai_skipped, ai_error
reports_uploaded, report_written
warning, error
```

### 17.3 Offene Punkte

| # | Thema | Priorität |
|---|-------|-----------|
| 1 | Safety Factor 1.4 knapp bei PDFs (+46,7% statt +34%) | Mittel |
| 2 | `pdf_pages_total/sampled` fehlt in RunSummary | Niedrig |
| 3 | `extraction_duration_ms` nicht aggregiert in RunSummary | Niedrig |
| 4 | `processed_at`, `ai_model` fehlen als Blob-Metadata | Niedrig |
| 5 | Kein `human_review_required_count` | Mittel |
| 6 | Keine Ground-Truth für echte KI-Accuracy | Hoch (für Produktion) |
| 7 | Kein Application Insights | Niedrig (für Pilot) |
