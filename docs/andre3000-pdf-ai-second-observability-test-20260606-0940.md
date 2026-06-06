# Andre3000 PDF AI Second Test / Observability Report

**Datum:** 2026-06-06  
**Run-ID:** 20260606T073808Z  
**Vorgänger-Test:** Run 20260606T072959Z (`102129.pdf`)  
**Erstellt von:** Andre3000 AI-Agent  

---

## 1. Executive Summary

| Prüfpunkt | Ergebnis |
|-----------|----------|
| Gesamtstatus | ✅ **GRÜN** |
| Run-ID | `20260606T073808Z` |
| PDF-Datei | `_root_part000/1133248.pdf` (71.235 Bytes) |
| AI Calls | ✅ 1 (von 10 Budget) |
| Klasse | `finance` |
| Confidence | 90 |
| Tags geschrieben | ✅ `dry_run=false`, `AI_WRITE_TAGS=true` |
| Fehler | ✅ 0 |
| needs_ai nach Test | ✅ 0 |
| Token Safety Factor | ✅ **1.5** (neu) |
| Buffered vs. Real | **+1,5% über Real** → Sicherheitspuffer ausreichend ✅ |
| Tests | ✅ **379/379** |
| Observability | Ausreichend für Pilot. Lücken dokumentiert. |

**Safety Factor 1.5 funktioniert:** Erstmals liegt der Buffered-Estimate (+1,5%) sicher über den realen Tokens. Zweite PDF erfolgreich klassifiziert.

---

## 2. Ausgangslage

- Erster PDF-Test (Run `20260606T072959Z`) war erfolgreich: `102129.pdf` → `finance`, conf=90
- Token Safety Factor 1.4 lag bei PDFs knapp unter real: buffered=1.091 vs. real=1.143 (−4,5%)
- Ziel: Faktor auf 1.5 erhöhen und zweite bekannte PDF (`1133248.pdf`) klassifizieren

---

## 3. Implementierte Änderung

| Datei | Änderung |
|-------|----------|
| `app/config.py` | Default von `"1.4"` auf `"1.5"` geändert |
| `.env` | `AI_TOKEN_ESTIMATION_SAFETY_FACTOR=1.5` |
| `.env.example` | `AI_TOKEN_ESTIMATION_SAFETY_FACTOR=1.5` |

Geänderte Dateien:
- [app/config.py](../app/config.py) — Default-Wert + Kommentar
- [.env](../.env) — Umgebungsvariable
- [.env.example](../.env.example) — Dokumentation

**Tests angepasst:** Nein — alle bestehenden Tests setzen den Faktor explizit auf `1.4` (kein impliziter Default-Test), daher keine Anpassung nötig. 379/379 bestanden.

---

## 4. Testkonfiguration

| Parameter | Wert |
|-----------|------|
| ENABLE_AI | true |
| AI_PROVIDER | groq |
| AI_MODEL | llama-3.3-70b-versatile |
| AI_WRITE_TAGS | true |
| AI_MAX_CALLS_PER_RUN | 10 |
| AI_MAX_TOTAL_CHARS_PER_RUN | 20.000 |
| AI_MAX_CHARS_PER_FILE | 2.000 |
| AI_TOKEN_ESTIMATION_SAFETY_FACTOR | **1.5** |
| PDF_MAX_PAGES | 3 |
| Prefix | `_root_part000/1133248` |
| max-files | 1 |
| dry_run | false |
| force | false |
| GROQ_API_KEY | ***REDACTED*** |

---

## 5. Ausgeführter Befehl

```bash
docker compose run --rm worker --mode classify --prefix "_root_part000/1133248" --max-files 1
```

Kein `--force`. Kein `--dry-run`. `max-files=1`.

---

## 6. PDF Discovery

| Prüfpunkt | Ergebnis |
|-----------|----------|
| Datei gefunden | ✅ `_root_part000/1133248.pdf` |
| Größe | 71.235 Bytes |
| Vorherige Tags | `status=none` (ungetaggt) |
| Blob als ungetaggt erkannt | ✅ `reason: status=none` |
| Fälschlich übersprungen | Nein |
| max-files=1 eingehalten | ✅ genau 1 Datei verarbeitet |

```json
{"event": "blob_seen", "blob_name": "_root_part000/1133248.pdf", "size_bytes": 71235}
{"event": "blob_detected_untagged", "reason": "status=none"}
```

---

## 7. PDF Extraktion

| Prüfpunkt | Ergebnis |
|-----------|----------|
| extraction_success | ✅ |
| extraction_method | `pymupdf` |
| extraction_chars (total) | 1.354 |
| AI input chars | 1.354 (unter cap von 2.000) |
| pdf_pages_processed | Nicht in run_finished — nur intern in ExtractionResult |
| extraction_duration_ms | Nicht in run_finished aggregiert — intern vorhanden |
| extraction_error | Keiner |
| tool_missing | Nein |
| In-memory (kein Tempfile) | ✅ |

> `1133248.pdf` (71 KB) hat weniger extrahierbare Zeichen als `102129.pdf` (97 KB, 4.000 chars). PDF-Inhaltsdichte variiert je nach Dokumentstruktur.

---

## 8. AI Klassifikation

| Prüfpunkt | Ergebnis |
|-----------|----------|
| ai_called | ✅ true |
| llm_used | ✅ true |
| class | **finance** |
| confidence | **90** |
| reason_code | `no_rule_match` |
| validation_success | ✅ true |
| ai_latency_ms | 424 ms |
| ai_model | `llama-3.3-70b-versatile` |
| ai_prompt_version | `v1` |

```json
{"event": "ai_result_validated", "class_label": "finance", "confidence": "90"}
{"event": "blob_classified", "class_label": "finance", "confidence": "90",
 "reason_code": "no_rule_match", "dry_run": false, "duration_ms": 752}
```

---

## 9. Token Report

| Metrik | Wert |
|--------|------|
| Prompt-Tokens (real) | **839** |
| Completion-Tokens (real) | 74 |
| Gesamt-Tokens (real) | **913** |
| Estimated Raw | 618 |
| Estimated Buffered (×1.5) | **927** |
| Token-Quelle | `provider_usage:1` |
| ai_token_estimation_safety_factor | **1.5** |
| Abweichung Real vs. Raw | **+47,7%** |
| Buffered vs. Real | 927 vs. 913 → **+1,5% über Real ✅** |

### Vergleich Safety Factor

| PDF | Raw | Real | Faktor | Buffered | Buffered vs. Real |
|-----|-----|------|--------|----------|-------------------|
| 102129.pdf (vorher, ×1.4) | 779 | 1.143 | 1.4 | 1.091 | −4,5% ⚠️ |
| 1133248.pdf (jetzt, ×1.5) | 618 | 913 | 1.5 | **927** | **+1,5% ✅** |

> **Safety Factor 1.5 ist ausreichend.** Erstmals liegt die Buffered-Schätzung sicher über dem realen Token-Verbrauch. Faktor 1.5 bleibt empfohlen für PDF-Läufe.

---

## 10. Azure Tags / Metadata

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
| `run_id` | `20260606T073808Z` |
| `llm_used` | `true` |
| `readable` | `true` |

> `processed_at`, `ai_model`, `ai_provider` sind **nicht** als Blob-Metadaten geschrieben — sie sind in run_finished-Log und Reports vorhanden. Siehe Observability-Lücken.

---

## 11. Reports

```
Container: reports
Prefix:    pilot-v0.1/20260606T073808Z
Dateien:   10
```

| Datei | PDF-/AI-/Token-Felder vorhanden? |
|-------|----------------------------------|
| `run-summary.json` | ✅ alle AI/Token/Extraction-Felder inkl. `ai_token_estimation_safety_factor=1.5` |
| `classification-details.csv` | ✅ `extraction_method`, `retry_recommended`, `ai_estimated_tokens_raw/buffered` etc. |
| `ai-candidates.csv` | ✅ inkl. `needs_ai`, `retry_recommended` |
| `admin-report.json` | ✅ vorhanden |
| `admin-report.pdf` | ✅ vorhanden |
| `run-events.jsonl` | ✅ vollständiges Event-Log |
| `untagged-files.csv` | ✅ |
| `classification-errors.csv` | ✅ (leer) |
| `classification-samples.csv` | ✅ |
| `classification-summary.csv` | ✅ |

**Wichtige run-summary.json Felder (bestätigt aus run_finished-Log):**

```json
{
  "ai_token_estimation_safety_factor": 1.5,
  "ai_estimated_tokens_raw_total": 618,
  "ai_estimated_tokens_buffered_total": 927,
  "ai_prompt_tokens_total": 839,
  "ai_completion_tokens_total": 74,
  "ai_total_tokens": 913,
  "ai_calls_used": 1,
  "ai_errors": 0,
  "extraction_method_counts": "pymupdf:1",
  "extracted_chars_total": 1354,
  "needs_ai_count": 0,
  "retry_recommended_count": 0,
  "duration_seconds": 0.85795
}
```

---

## 12. Observability Ist-Stand

| Prüfpunkt | Status |
|-----------|--------|
| `logging_utils.py` geprüft | ✅ (vollständig in Phase 6 analysiert) |
| Strukturierte JSON-Logs (JSONL stdout) | ✅ |
| `run_id` in allen Events | ✅ |
| `mode`, `prefix`, `dry_run`, `force` in `run_started` | ✅ |
| `blob_name` in relevanten Events | ✅ |
| `reason_code` in Blob-Events | ✅ |
| `extraction_method` | ⚠️ Nur in `run_finished`, kein separates `extraction_completed`-Event |
| `ai_provider`, `ai_model` | ✅ In `run_started` und `run_finished` |
| `ai_latency_ms` | ✅ Aggregiert in `run_finished` (`ai_latency_ms_avg`, `_max`) |
| `ai_total_tokens` | ✅ In `run_finished` |
| `needs_ai`, `retry_recommended` | ✅ In `run_finished` + Reports |
| `ai_token_estimation_safety_factor` | ✅ In `run_finished` |
| Laufzeit gesamt (`duration_seconds`) | ✅ In `run_finished` |
| `files_per_hour` (`throughput_files_per_hour`) | ✅ In `run_finished` |
| Secrets geschützt | ✅ GROQ_API_KEY nie in Logs |
| Event-Buffer → `run-events.jsonl` nach Azure | ✅ |

---

## 13. Observability Lücken

| Bereich | Fehlt | Priorität | Empfehlung |
|---------|-------|-----------|------------|
| Laufzeit | `blob_processing_duration_ms` pro Blob (end-to-end: Download+Extract+AI+Tag) | Mittel | In `_classify_blob` berechnen, in `ClassificationResult` + `blob_classified`-Event |
| Laufzeit | `download_duration_ms` | Niedrig | In `download_blob_content` messen |
| Laufzeit | `extraction_duration_ms` (Aggregat) | Niedrig | In `ExtractionResult` vorhanden – fehlt in `RunSummary` |
| Laufzeit | `report_upload_duration_ms` | Niedrig | In `upload_run_reports` messen |
| Extraktion | `pdf_pages_total` / `pdf_pages_sampled` in `RunSummary` | Mittel | Aus `ExtractionResult` aggregieren |
| Extraktion | `extraction_completed`-Event pro Blob | Niedrig | In `logging_utils.py` ergänzen |
| AI | `ai_validation_error_count` in `RunSummary` | Mittel | Zähler wenn `ai_error=schema_validation_failed` |
| Qualität | `validation_error_count` | Mittel | Tag-Validierungsfehler zählen |
| Qualität | `human_review_required_count` | Mittel | `confidence < 70 AND llm_used=true` |
| Qualität | Ground Truth / `human_corrected_class` | Hoch | Grundlage für echte KI-Accuracy — nicht automatisch messbar |
| Metadata | `processed_at`, `ai_model`, `ai_provider` als Blob-Metadaten | Niedrig | In `new_metadata` in `_classify_blob` ergänzen |
| AI Accuracy | Echte Accuracy messbar? | **Noch nicht** | Proxy-Metriken vorhanden (confidence, unknown_count). Echter Wert nur mit Ground-Truth-Labels. |

### AI Accuracy — Stand

**Echte AI Accuracy ist noch nicht messbar**, solange keine Ground-Truth-Labels oder Human-Review-Ergebnisse vorliegen.

Bereits verfügbare Proxy-Metriken:
- `confidence` (Selbsteinschätzung des Modells)
- `files_unknown` (Anzahl unklassifizierter Dateien)
- `needs_ai_count`
- `retry_recommended_count`
- `ai_errors` (Validierungsfehler + Provider-Fehler)

Für echte Accuracy später nötig:
- `ground_truth_class`
- `human_corrected_class`
- `ai_was_correct` (bool)
- `review_status`, `reviewer`, `reviewed_at`

---

## 14. Application Insights Empfehlung

**Noch nicht implementiert. Nur Dokumentation.**

### customEvents (Empfehlung)

| Event | Auslöser |
|-------|----------|
| `worker_run_started` | Beginn jedes Laufs |
| `worker_run_finished` | Ende jedes Laufs |
| `blob_processing_started` | Pro Blob vor Download |
| `blob_processing_finished` | Pro Blob nach Tag-Write |
| `extraction_finished` | Nach PyMuPDF/antiword |
| `ai_call_finished` | Nach Groq/Foundry-Call |
| `ai_validation_failed` | Wenn Schema-Validierung schlägt fehl |
| `blob_tag_write_finished` | Nach Azure Tag-Write |
| `report_upload_finished` | Nach Report-Upload |

### customMetrics (Empfehlung)

| Metrik | Einheit |
|--------|---------|
| `run_duration_ms` | ms |
| `blob_processing_duration_ms` | ms |
| `download_duration_ms` | ms |
| `extraction_duration_ms` | ms |
| `ai_latency_ms` | ms |
| `report_upload_duration_ms` | ms |
| `files_processed` | Anzahl |
| `files_error` | Anzahl |
| `extraction_success_count` | Anzahl |
| `extraction_error_count` | Anzahl |
| `ai_calls_used` | Anzahl |
| `ai_errors` | Anzahl |
| `ai_total_tokens` | Tokens |
| `needs_ai_count` | Anzahl |
| `retry_recommended_count` | Anzahl |

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
- Vollständige Blob-Namen mit sensitiven Pfaden (nur anonymisierte IDs)

---

## 15. Tests

```bash
python -m pytest tests/ -q
```

```
379 passed in 0.63s
```

Keine Fehler. Alle 379 Tests grün inkl. der neuen AI/Retry/Token/PDF-Tests aus Phase 6.

**Hinweis Docker-Container-Tests:** Vor dem Docker-Rebuild liefen in einem alten Image 4 Tests mit `UnboundLocalError: needs_ai_val` (Test-Isolation in Docker-Image veraltet). Nach Rebuild der Docker-Image mit aktuellem Code kein Problem. Lokale Tests waren durchgehend grün.

---

## 16. Bewertung

| Frage | Antwort |
|-------|---------|
| Ist zweiter PDF-Test erfolgreich? | ✅ Ja – PyMuPDF + Groq + Tag-Write vollständig |
| Reicht Safety Factor 1.5 für diesen Test? | ✅ Ja – Buffered +1,5% über Real |
| Ist PDF-Verarbeitung bereit für dritte PDF? | ✅ Ja |
| Ist Observability ausreichend für Pilot? | ✅ Ja – JSONL-Logs, run_id, Token-Felder, Reports vollständig |
| Was fehlt für Produktion? | `blob_processing_duration_ms`, Ground-Truth für KI-Accuracy, Application Insights, `human_review_required_count` |

---

## 17. Empfehlung nächster Schritt

| Priorität | Maßnahme |
|-----------|----------|
| 1 | **Dritte PDF testen**: `docker compose run --rm worker --mode classify --prefix "_root_part000/1235690" --max-files 1` |
| 2 | **PDF-Sammelbewertung**: Nach allen 3 PDFs zusammenfassen — Token-Abweichungen, Klassen, Confidence-Verteilung |
| 3 | **Observability Minifix** (optional): `human_review_required_count` + `pdf_pages_total` in RunSummary |
| 4 | **Größerer .doc-Lauf**: `--max-files 50` (bereits klassifizierte Dateien werden übersprungen) |
| 5 | **Application Insights**: Erst nach erfolgreichem max-files=50-Lauf einplanen |

**Empfehlung: Dritte PDF mit max-files=1, dann PDF-Sammelbewertung, dann skalieren.**

---

## 18. Anhang

### 18.1 Run-Finished Log (20260606T073808Z)

```json
{
  "run_id": "20260606T073808Z",
  "mode": "classify",
  "status": "ok",
  "ai_token_estimation_safety_factor": 1.5,
  "ai_estimated_tokens_raw_total": 618,
  "ai_estimated_tokens_buffered_total": 927,
  "ai_prompt_tokens_total": 839,
  "ai_completion_tokens_total": 74,
  "ai_total_tokens": 913,
  "ai_calls_used": 1,
  "ai_errors": 0,
  "ai_candidates": 1,
  "ai_latency_ms_avg": 424.0,
  "ai_latency_ms_max": 424,
  "ai_token_source_breakdown": "provider_usage:1",
  "extraction_method_counts": "pymupdf:1",
  "extracted_chars_total": 1354,
  "extraction_success_count": 1,
  "needs_ai_count": 0,
  "retry_recommended_count": 0,
  "llm_used_count": 1,
  "files_processed": 1,
  "files_classified": 1,
  "files_unknown": 0,
  "files_error": 0,
  "duration_seconds": 0.85795,
  "throughput_files_per_hour": 4196.05,
  "reports_uploaded": true
}
```

### 18.2 Bekannte PDFs – Status nach diesem Test

| Datei | Größe | Status |
|-------|-------|--------|
| `_root_part000/102129.pdf` | 96.927 B | ✅ `classified` – finance, conf=90, Run `20260606T072959Z` |
| `_root_part000/1133248.pdf` | 71.235 B | ✅ `classified` – finance, conf=90, Run `20260606T073808Z` |
| `_root_part000/1235690.pdf` | unbekannt | ⏳ noch ungetaggt |

### 18.3 Token-Vergleich alle PDF-Tests

| Run | PDF | Raw | Real | Faktor | Buffered | Buffered vs. Real |
|-----|-----|-----|------|--------|----------|-------------------|
| 20260606T072959Z | 102129.pdf | 779 | 1.143 | 1.4 | 1.091 | −4,5% ⚠️ |
| 20260606T073808Z | 1133248.pdf | 618 | 913 | **1.5** | 927 | **+1,5% ✅** |

### 18.4 Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `app/config.py` | Default `AI_TOKEN_ESTIMATION_SAFETY_FACTOR` von `1.4` → `1.5` |
| `.env` | `AI_TOKEN_ESTIMATION_SAFETY_FACTOR=1.5` |
| `.env.example` | `AI_TOKEN_ESTIMATION_SAFETY_FACTOR=1.5` |

### 18.5 Offene Punkte

| # | Thema | Priorität |
|---|-------|-----------|
| 1 | `pdf_pages_total/sampled` fehlt in RunSummary | Niedrig |
| 2 | `extraction_duration_ms` nicht aggregiert | Niedrig |
| 3 | `processed_at`, `ai_model` fehlen als Blob-Metadata | Niedrig |
| 4 | Kein `human_review_required_count` | Mittel |
| 5 | Keine Ground-Truth für echte KI-Accuracy | Hoch (für Produktion) |
| 6 | Kein Application Insights | Niedrig (für Pilot) |
| 7 | Dritte PDF (`1235690.pdf`) noch ungetestet | Mittel |
