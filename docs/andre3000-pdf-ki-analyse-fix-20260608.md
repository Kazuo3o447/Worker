# PDF Admin-Report: KI-Analyse Felder Fix

**Datum:** 2026-06-08  
**Worker:** Andre3000  
**Typ:** Bugfix  
**Komponente:** Frontend PDF-Report-Generator

---

## Problem

Im Admin-Report PDF (Abschnitt "KI-Analyse") wurden folgende Informationen nicht angezeigt:
- **KI-Modell**: Zeigte "-" statt dem tatsächlichen Modell (z.B. `llama-3.3-70b-versatile`)
- **Token-Verbrauch**: Alle Token-Metriken zeigten 0
  - Prompt-Tokens gesamt
  - Completion-Tokens gesamt
  - Total Tokens
  - Tokens/Datei Ø
- **Latenz**: Durchschnittliche und maximale Latenz fehlten
- **Token-Schätzungen**: Raw/Buffered-Werte nicht sichtbar

**Nur sichtbar:** AI-Provider (z.B. "groq") und AI-Calls-Budget

---

## Ursache

In `frontend/app.py`, Funktion `compile_pdf_on_the_fly_frontend()` (Zeile ~395):

Die `RunSummary`-Instanz für den PDF-Report wurde mit nur 7 AI-Feldern aus dem `run-summary.json` befüllt:
```python
summary_obj = RunSummary(
    # ... andere Felder ...
    enable_ai=bool(summary_dict.get("enable_ai", False)),
    ai_provider=summary_dict.get("ai_provider", "none"),
    ai_max_calls_per_run=int(summary_dict.get("ai_max_calls_per_run", 0)),
    ai_calls_used=int(summary_dict.get("ai_calls_used", 0)),
    ai_calls_skipped=int(summary_dict.get("ai_calls_skipped", 0)),
    ai_errors=int(summary_dict.get("ai_errors", 0)),
    ai_candidates=int(summary_dict.get("ai_candidates", 0))
    # ❌ Hier fehlten 16 weitere AI-Felder!
)
```

Alle anderen AI-Felder erhielten ihre Default-Werte:
- `ai_model = ""` → PDF zeigt "-"
- `ai_total_tokens_sum = 0` → PDF zeigt "0"
- `ai_prompt_tokens_total = 0`
- `ai_completion_tokens_total = 0`
- usw.

---

## Lösung

**16 fehlende AI-Felder** wurden ergänzt und aus dem `run-summary.json` gelesen:

```python
summary_obj = RunSummary(
    # ... bestehende Felder ...
    enable_ai=bool(summary_dict.get("enable_ai", False)),
    ai_provider=summary_dict.get("ai_provider", "none"),
    ai_max_calls_per_run=int(summary_dict.get("ai_max_calls_per_run", 0)),
    ai_calls_used=int(summary_dict.get("ai_calls_used", 0)),
    ai_calls_skipped=int(summary_dict.get("ai_calls_skipped", 0)),
    ai_errors=int(summary_dict.get("ai_errors", 0)),
    ai_candidates=int(summary_dict.get("ai_candidates", 0)),
    # ✅ NEU: Token- und Modell-Felder
    ai_model=summary_dict.get("ai_model", ""),
    ai_prompt_version=summary_dict.get("ai_prompt_version", ""),
    ai_prompt_tokens_total=int(summary_dict.get("ai_prompt_tokens_total", 0)),
    ai_completion_tokens_total=int(summary_dict.get("ai_completion_tokens_total", 0)),
    ai_total_tokens_sum=int(summary_dict.get("ai_total_tokens", summary_dict.get("ai_total_tokens_sum", 0))),
    ai_estimated_tokens_total=int(summary_dict.get("ai_estimated_tokens_total", 0)),
    ai_estimated_tokens_raw_total=int(summary_dict.get("ai_estimated_tokens_raw_total", 0)),
    ai_estimated_tokens_buffered_total=int(summary_dict.get("ai_estimated_tokens_buffered_total", 0)),
    ai_token_estimation_safety_factor=float(summary_dict.get("ai_token_estimation_safety_factor", 1.4)),
    ai_latency_ms_avg=float(summary_dict.get("ai_latency_ms_avg", 0.0)),
    ai_latency_ms_max=int(summary_dict.get("ai_latency_ms_max", 0)),
    ai_token_source_breakdown=summary_dict.get("ai_token_source_breakdown", ""),
    ai_skipped_budget_exhausted_count=int(summary_dict.get("ai_skipped_budget_exhausted_count", 0)),
    needs_ai_count=int(summary_dict.get("needs_ai_count", 0)),
    retry_recommended_count=int(summary_dict.get("retry_recommended_count", 0)),
)
```

---

## Ergebnis

Nach dem Fix zeigt der PDF-Report im Abschnitt "KI-Analyse" vollständige Informationen:

| Feld | Vorher | Nachher |
|------|--------|---------|
| Modell (LLM) | `-` | `llama-3.3-70b-versatile` |
| Prompt-Tokens gesamt | `0` | Tatsächlicher Wert (z.B. `45.203`) |
| Completion-Tokens gesamt | `0` | Tatsächlicher Wert (z.B. `3.891`) |
| Total Tokens | `0` | Tatsächlicher Wert (z.B. `49.094`) |
| Tokens/Datei Ø | `-` | Berechneter Durchschnitt (z.B. `245.5`) |
| Latenz avg (ms) | `0` | Tatsächlicher Wert (z.B. `1834.2`) |
| Latenz max (ms) | `0` | Tatsächlicher Wert (z.B. `4521`) |

---

## Getestete Komponenten

- ✅ PDF-Download aus Dashboard (Reports & Exporte)
- ✅ On-the-fly PDF-Generierung aus `run-summary.json` + `classification-details.csv`
- ✅ Token-Summary-Anzeige im Dashboard (nutzt direkt `run-summary.json`, war bereits korrekt)
- ✅ admin-report.json (war bereits korrekt, nur PDF betroffen)

---

## Dateien geändert

- `frontend/app.py` (Zeile ~420-430): `compile_pdf_on_the_fly_frontend()`

---

## Rückwärtskompatibilität

✅ **Voll kompatibel**: Ältere Reports ohne diese Felder zeigen weiterhin Default-Werte (0, "-").  
Neue Reports mit allen Feldern profitieren sofort vom Fix.

---

## Weiteres Vorgehen

- PDF-Report für aktuelle Runs herunterladen und validieren
- Bei Bedarf alte Reports neu generieren lassen (über Dashboard "Reports & Exporte")
