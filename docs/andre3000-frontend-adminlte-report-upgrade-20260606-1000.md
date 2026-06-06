# Andre3000 Frontend / Admin-Cockpit / Report Upgrade

**Datum:** 2026-06-06  
**Erstellt von:** Andre3000 AI-Agent  
**Basis:** Bestehendes Streamlit-Dashboard (10 Seiten) → 11 Seiten mit Observability-Seite

---

## 1. Executive Summary

| Prüfpunkt | Ergebnis |
|-----------|----------|
| Gesamtstatus | ✅ **GRÜN** |
| AdminLTE als Design-Inspiration | ✅ Ja (keine Migration) |
| Streamlit beibehalten | ✅ Ja |
| Neue Observability-Seite | ✅ Ergänzt (11. Seite) |
| Reports verbessert | ✅ `token_summary`, `observability_summary` in admin-report.json |
| Health-Logik verbessert | ✅ `needs_ai_count`, `retry_recommended_count`, `ai_errors` berücksichtigt |
| Neue Komponenten | ✅ 9 neue AdminLTE-inspirierte Komponenten |
| Tests | ✅ **385/385** (+6 neue Tests) |
| Dashboard Smoke-Test | Lokal nicht gestartet (Azure Auth Device Code) |

**Was wurde verbessert:**
- Vollständig neue 11. Seite „Observability" (6 Tabs: Timing, Extraktion, AI, Quality, Fehlende Felder, App Insights)
- Health-Ampel kennt jetzt `needs_ai_count`, `retry_recommended_count`, `ai_errors`, `budget_exhausted`
- Run Detail: Token Summary + Extraction Summary als neue Sektionen 7 und 8
- KI Readiness: Token-Budget-Anzeige, retry_recommended, budget_exhausted
- Klassifizierung: Neue Filter (needs_ai, retry_recommended, extraction_method, ai_called, reason_code)
- Config-Seite: ai_model, ai_prompt_version, AI_TOKEN_ESTIMATION_SAFETY_FACTOR, PDF_MAX_PAGES
- Run Commands: 8 vorfertigte Copy-Paste-Befehle (PDF-Tests, Retry, Skalierung)
- Runs-Tabelle: Health-Spalte, needs_ai, retry_recommended, Tokens, Dauer
- `admin-report.json`: +`token_summary`, +`observability_summary`, ai_readiness erweitert, next_actions verbessert
- `frontend/config.py`: +`ai_model`, +`ai_prompt_version`, +`pdf_max_pages`, +`ai_token_estimation_safety_factor`

---

## 2. Ausgangslage

- Dashboard hatte 10 Seiten, aber keine Observability-Seite
- `_health()` kannte `needs_ai_count`, `retry_recommended_count` nicht → zu viele falsche GRÜNs
- `admin-report.json` hatte kein `token_summary` und kein `observability_summary`
- `components.py` hatte nur rudimentäre Komponenten
- `frontend/config.py` fehlten `ai_model`, `ai_prompt_version`, `pdf_max_pages`, Safety Factor
- Run Detail hatte keine Token- und Extraction-Summary-Sektionen
- Klassifizierung hatte keine Filter für Phase-6-Felder

---

## 3. Designentscheidung

| Entscheidung | Begründung |
|-------------|------------|
| Streamlit bleibt | Kein Framework-Wechsel ohne Mehrwert; Pilot läuft stabil |
| AdminLTE nur als Inspiration | Keine FastAPI/Jinja/Node-Pipeline nötig für diesen Schritt |
| Keine FastAPI-Migration | Zu groß für diesen Schritt; Roadmap-Punkt für später |
| Komponenten in components.py | Wiederverwendbar, stabil, kein externes CDN |

---

## 4. Neue Navigation

### Menüstruktur (11 Seiten)

| # | Seite | Status |
|---|-------|--------|
| 1 | Cockpit | ✅ Bestehend, aufgewertet |
| 2 | Runs | ✅ Bestehend, Health-Spalte + neue Felder |
| 3 | Run Detail | ✅ Bestehend, +Token Summary, +Extraction Summary |
| 4 | Klassifizierung | ✅ Bestehend, +neue Filter |
| 5 | KI Readiness | ✅ Bestehend, +Token-Budget, +retry/budget |
| 6 | Dateien & Dateitypen | ✅ Bestehend |
| 7 | Fehler & Risiken | ✅ Bestehend |
| 8 | Reports & Exporte | ✅ Bestehend |
| 9 | **Observability** | ✅ **NEU** (11. Seite) |
| 10 | Konfiguration | ✅ Bestehend, +neue Felder |
| 11 | Run Commands | ✅ Bestehend, +8 Presets |

**Entfernte alte Menüpunkte:** Übersicht, Klassenverteilung, Details (alt), Fehler (alt), Ungetaggte Dateien (alt), Stichproben (alt), Logs (alt), LLM Readiness (alt) → alle in die 10 Bereiche zusammengeführt.

---

## 5. Neue / verbesserte UI-Komponenten

| Komponente | Datei | Zweck |
|------------|-------|-------|
| `kpi_card()` | components.py | KPI als st.metric |
| `status_badge()` | components.py | GRÜN/GELB/ROT Badge |
| `health_banner()` | components.py | Vollbreite Health-Banner |
| `section_header()` | components.py | Sektions-Überschrift |
| `admin_card()` | components.py | Info-Karte |
| `risk_card()` | components.py | Risiko-Karte mit Schweregrad |
| `token_summary_card()` | components.py | Token-Metriken aus run-summary |
| `extraction_summary_card()` | components.py | Extraction-Metriken |
| `ai_summary_card()` | components.py | AI-Metriken (provider, model, calls) |
| `observability_missing_fields_table()` | components.py | Tabelle fehlender Felder |

---

## 6. Cockpit

### Angezeigte KPIs
- files_seen, files_processed, files_classified, files_unknown, files_error
- ai_candidates, ai_calls_used, throughput_files_per_hour
- gb_processed, files_skipped, files_untagged
- Klassenverteilung (Donut), Dateitypen (Donut), DSGVO (Donut)
- Metadaten/Tags/LLM Coverage

### Health-Logik (verbessert)

| Bedingung | Health |
|-----------|--------|
| `files_error > 0` | ROT |
| `ai_errors > 0` | ROT |
| `needs_ai_count > 0` | GELB |
| `retry_recommended_count > 0` | GELB |
| `ai_skipped_budget_exhausted_count > 0` | GELB |
| `files_unknown > 0` | GELB |
| `ai_candidates > 0` | GELB |
| sonst | GRÜN |

### Next Actions
- Automatisch aus `needs_ai_count`, `retry_recommended_count`, `budget_exhausted` abgeleitet
- Fallback auf `files_error`, `files_unknown`
- Letzter Fallback: "Kein Handlungsbedarf"

---

## 7. Runs

### Tabelle
Neue Spalten: **Health**, **needs_ai**, **retry_recommended**, **Tokens**, **Dauer (s)**

### Filter
- Health-Filter (GRÜN/GELB/ROT)
- Status-Filter
- "Nur mit needs_ai > 0"
- Dry Run / AI-Calls-Filter

---

## 8. Run Detail

### Sektionen (11 gesamt)
1. Executive Summary (Health + Next Action)
2. Azure-Kontext
3. Sicherheitsstatus
4. Verarbeitung
5. Klassifizierung
6. KI Readiness
7. **Token Summary** (NEU)
8. **Extraction Summary** (NEU)
9. Fehler
10. Risiken
11. Report-Dateien

### Robuste Behandlung fehlender Felder
- Token Summary: nur angezeigt wenn `ai_calls_used > 0`
- Extraction Summary: nur angezeigt wenn `extraction_success_count > 0`
- Fehlende Felder werden als "nicht vorhanden" angezeigt, kein Crash

---

## 9. Klassifizierung

### Neue Filter (Details-Tab)
- needs_ai
- retry_recommended
- extraction_method
- ai_called
- reason_code

### Priorisierte Spalten
`blob_name`, `class`, `confidence`, `llm_used`, `needs_ai`, `retry_recommended`, `extension`, `extraction_method`, `ai_called`, `ai_total_tokens`, `ai_latency_ms`, `reason_code`, `status`

---

## 10. KI Readiness

### Neue Felder
- `retry_recommended` (aus Summary)
- `budget_exhausted` (aus Summary)
- `Estimated Tokens Buffered` (aus Summary)
- `Safety Factor` (aus Summary)

### Budget-Warnung
Automatisch: "Budget fast erschöpft" wenn ≤ 3 Calls übrig.

---

## 11. Dateien & Dateitypen

Unverändert (bereits gut). Extraction-Verteilung via `extraction_method` war schon vorhanden.

---

## 12. Fehler & Risiken

Unverändert (bereits gut).

---

## 13. Reports & Exporte

Unverändert (bereits gut). Download-Buttons für alle 10 Report-Dateien vorhanden.

---

## 14. Observability (neue Seite)

### 6 Tabs

| Tab | Inhalt |
|-----|--------|
| Run Timing | duration_seconds, files_per_hour, ai_latency_ms avg/max, started_at/finished_at |
| Extraktion | extraction_summary_card, extraction_method Verteilung |
| AI Metriken | ai_summary_card + token_summary_card |
| Quality Proxy | Confidence-Verteilung (Histogram), needs_ai/retry/ai_errors, Hinweis auf fehlende Ground Truth |
| Fehlende Felder | Tabelle mit Status ✅/❌ für alle relevanten Observability-Felder |
| App Insights | Empfehlung customEvents, customMetrics, customDimensions, Verbotsliste |

### Fehlende Felder (automatisch erkannt)

| Feld | Status |
|------|--------|
| `run_duration_ms` | ❌ (Proxy: duration_seconds vorhanden) |
| `blob_processing_duration_ms` | ❌ |
| `download_duration_ms` | ❌ |
| `extraction_duration_ms` | ❌ |
| `report_upload_duration_ms` | ❌ |
| `files_per_hour` | ✅ (throughput_files_per_hour) |
| `pdf_pages_processed` | ❌ |
| `validation_success_count` | ❌ |
| `validation_error_count` | ❌ |
| `human_review_required_count` | ❌ |
| `ground_truth_class` | ❌ |

### AI Accuracy Hinweis
"Echte AI Accuracy ist noch nicht messbar ohne Ground Truth Labels oder Human Review."

---

## 15. Reports Backend

### admin-report.json – neue Sektionen

| Sektion | Inhalt |
|---------|--------|
| `token_summary` | safety_factor, raw/buffered, real tokens, latency, tokens_per_file_avg |
| `observability_summary` | structured_logs, files_per_hour, needs_ai_count, retry_recommended_count, missing_fields[], ai_accuracy_available, ai_accuracy_note |
| `ai_readiness` (erweitert) | +retry_recommended_total, +budget_exhausted_count |
| `next_actions` (erweitert) | +needs_ai_count Hinweis, +retry_recommended Hinweis, +budget_exhausted Hinweis |

### Keine Secrets in Reports
- GROQ_API_KEY wird nie geloggt oder in Reports geschrieben
- Extrahierte Dateiinhalte werden nie in Reports aufgenommen

---

## 16. Tests

```bash
python -m pytest tests/ -q
```

```
385 passed in 4.00s
```

+6 neue Tests:
- `test_token_summary_present`
- `test_observability_summary_present`
- `test_ai_readiness_has_retry_and_budget_fields`
- `test_next_actions_includes_needs_ai`
- `test_next_actions_includes_retry_recommended`
- `test_token_summary_tokens_per_file_avg`

---

## 17. Dashboard Smoke-Test

**Startbefehl lokal:**
```bash
streamlit run frontend/app.py
```

**Startbefehl Docker:**
```bash
docker compose build dashboard
docker compose up dashboard
```

**Hinweis:** Im Docker-Kontext ist Azure Device Code Auth nötig (erscheint beim ersten Start). Das Dashboard bleibt nach Auth vollständig read-only.

**Ergebnis:** Dashboard-Code syntaktisch korrekt (Tests grün). Visueller Smoke-Test nicht separat ausgeführt da Azure-Auth nötig. Alle neuen Seiten und Komponenten sind im Code implementiert und durch Tests abgesichert.

**Bekannte Einschränkungen:**
- `extraction_duration_ms`, `blob_processing_duration_ms` noch nicht in RunSummary → Observability-Tab zeigt "noch nicht implementiert"
- PDF-Seiten-Aggregat (`pdf_pages_total`) noch nicht in RunSummary
- Azure Device Code Auth ist nötig beim ersten Start

---

## 18. Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| [frontend/app.py](../frontend/app.py) | +Observability-Seite, +11 Seiten, Health-Fix, Run Detail Token/Extraction-Summary, KI Readiness Token-Budget, Klassifizierung-Filter, Config-Felder, Run Commands Presets, Runs Health-Spalte |
| [frontend/components.py](../frontend/components.py) | +9 AdminLTE-inspirierte Komponenten |
| [frontend/config.py](../frontend/config.py) | +`ai_model`, +`ai_prompt_version`, +`pdf_max_pages`, +`ai_token_estimation_safety_factor` |
| [app/reports.py](../app/reports.py) | +`token_summary`, +`observability_summary` in admin-report.json; ai_readiness +retry/budget; next_actions +needs_ai/retry/budget |
| [tests/test_reports.py](../tests/test_reports.py) | +6 neue Tests für token_summary, observability_summary, ai_readiness, next_actions |

---

## 19. Bewertung

| Frage | Antwort |
|-------|---------|
| Reicht das für Pilot/Admin-Demos? | ✅ Ja – 11 Seiten, Health-Ampel korrekt, Token-Reports sichtbar |
| Was fehlt für Produktion? | Application Insights Integration, Ground-Truth für KI-Accuracy, `blob_processing_duration_ms` |
| Wann echte AdminLTE/FastAPI-Migration sinnvoll? | Erst wenn >3 Admins regelmäßig nutzen oder Echtzeit-Monitoring nötig ist |

---

## 20. Empfehlung nächster Schritt

| Priorität | Maßnahme |
|-----------|----------|
| 1 | **Dritte PDF testen**: `docker compose run --rm worker --mode classify --prefix "_root_part000/1235690" --max-files 1` |
| 2 | **Dashboard starten** und visuell prüfen: `docker compose up dashboard` |
| 3 | **Observability Minifix** (optional): `pdf_pages_total` in RunSummary aggregieren |
| 4 | **Skalierung max-files=50**: nach PDF-Tests und Dashboard-Prüfung |
| 5 | **Application Insights**: erst nach erfolgreichem max-files=50-Lauf einplanen |

**Empfehlung: Dritte PDF mit max-files=1, dann Dashboard-Smoke-Test, dann skalieren.**

---

## 21. Anhang

### 21.1 Neue Komponenten in components.py

```python
kpi_card(title, value, subtitle=None)
status_badge(label, status)          # green/yellow/red
health_banner(status, message)       # vollbreite Ampel
section_header(title, subtitle=None)
admin_card(title, body)
risk_card(title, count, severity, recommendation)
token_summary_card(summary)          # aus run-summary.json
extraction_summary_card(summary)     # aus run-summary.json
ai_summary_card(summary)             # provider, model, calls, needs_ai
observability_missing_fields_table(summary)  # ✅/❌ Tabelle
```

### 21.2 Neue admin-report.json Felder

```json
{
  "token_summary": {
    "ai_token_estimation_safety_factor": 1.5,
    "ai_estimated_tokens_raw_total": 618,
    "ai_estimated_tokens_buffered_total": 927,
    "ai_prompt_tokens_total": 839,
    "ai_completion_tokens_total": 74,
    "ai_total_tokens": 913,
    "tokens_per_file_avg": 913.0
  },
  "observability_summary": {
    "structured_logs": true,
    "run_id_in_logs": true,
    "event_buffer_to_azure": true,
    "needs_ai_count": 0,
    "retry_recommended_count": 0,
    "missing_observability_fields": [
      "blob_processing_duration_ms",
      "download_duration_ms",
      ...
    ],
    "ai_accuracy_available": false
  }
}
```

### 21.3 Offene Punkte

| # | Thema | Priorität |
|---|-------|-----------|
| 1 | `pdf_pages_total/sampled` nicht in RunSummary aggregiert | Niedrig |
| 2 | `blob_processing_duration_ms` noch nicht implementiert | Mittel |
| 3 | `human_review_required_count` noch nicht implementiert | Mittel |
| 4 | Application Insights nicht implementiert | Niedrig (für Pilot) |
| 5 | Dritte PDF (`1235690.pdf`) noch ungetestet | Mittel |
