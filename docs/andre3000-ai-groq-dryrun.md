# Andre3000 Groq AI Dry Run

**Projekt:** GEMA Azure Blob Storage Classification Worker „Andre3000"  
**Stand:** 2026-06-06  
**Status:** Implementiert – bereit für ersten manuellen Test

---

## 1. Ziel

Andre3000 bekommt eine erste echte KI-Klassifikationsschicht mit **Groq (Free Tier)**,
um Dokumente auf Basis extrahierter Textauszüge zu klassifizieren.

Dieser erste Schritt ist ein **AI Dry Run**:
- KI klassifiziert fachlich
- **Keine** Tags/Metadata werden in Azure geschrieben
- **Keine** Massentests
- Vollständiges Token- und Modell-Reporting für spätere Kostenbewertung

---

## 2. Warum Groq

| Kriterium | Groq | Azure AI Foundry |
|---|---|---|
| Kosten erster Test | Free Tier | Azure-Subscription nötig |
| Setup | GROQ_API_KEY genügt | Endpoint + Deployment |
| Latenz | sehr niedrig (LPU) | variabel |
| OpenAI-kompatibel | ja | ja |
| SDK | `groq` (pip) | `openai` (pip) |

Groq ist ideal für den ersten kostengünstigen Test.  
Azure AI Foundry folgt als nächste Stufe (wenn Tagging live geht).

---

## 3. Modell-Empfehlung

### Empfohlen für ersten Test

```
AI_MODEL=llama-3.3-70b-versatile
```

**Begründung:**
- Textklassifikation reicht für ersten Test – kein Vision nötig
- Free-Tier-freundlich
- Kein EU-Lizenzthema im ersten Schritt
- Ausreichend leistungsfähig für Dokumentklassifikation auf Basis von Textauszügen

### Nicht direkt verwenden (derzeit)

```
meta-llama/llama-4-scout-17b-16e-instruct
```

**Grund:**
- Zwar multimodal (Vision + Text)
- **EU-Lizenzhinweis für Llama 4 Multimodal** beachten
- Erst nach rechtlicher/organisatorischer Klärung bei GEMA nutzen
- Vision-Klassifikation separat und später bewerten

---

## 4. Warum zunächst Text-only

- Vision-Modelle bringen einen EU-Lizenzhinweis mit (Llama 4 Multimodal)
- Textklassifikation deckt den Großteil der Pilotdateien ab
- Simpler Test ohne zusätzliche rechtliche Prüfung
- Modell kann später gewechselt werden ohne Architekturänderung

---

## 5. Konfiguration

```env
# .env (local) oder Docker Compose
ENABLE_AI=true
AI_PROVIDER=groq
AI_MODEL=llama-3.3-70b-versatile
AI_PROMPT_VERSION=v1
AI_MAX_CALLS_PER_RUN=3
AI_MAX_CHARS_PER_FILE=2000
AI_MAX_TOTAL_CHARS_PER_RUN=10000
AI_TEMPERATURE=0
AI_MAX_OUTPUT_TOKENS=300
AI_WRITE_TAGS=false
```

**Secret (niemals ins Repo, niemals ins Dashboard):**

```powershell
$env:GROQ_API_KEY="gsk_..."
```

---

## 6. Sicherheit

| Regel | Implementierung |
|---|---|
| GROQ_API_KEY nie loggen | `_try_init()` liest Key, speichert nie im Log |
| GROQ_API_KEY nie in Reports | `_error_resp()` redacted den Key aus Fehlermeldungen |
| GROQ_API_KEY nie im Dashboard | Dashboard zeigt nur ai_provider, ai_model, token counts |
| Fehler bei fehlendem Key | `ai_error=missing_api_key` im Report |
| Kein Content-Upload | Nur Text-Extract (max. 2000 Zeichen), kein Datei-Upload |
| Kein Tool-Use | Nur `json_object` Response Format |

---

## 7. Promptversion v1

### System Prompt

```
Du klassifizierst Dokumente für einen Azure Blob Storage Archivierungspiloten.
Du gibst ausschließlich valides JSON gemäß Schema zurück.
Du darfst nur erlaubte Klassen verwenden.
Wenn der Inhalt nicht reicht, nutze class=unknown und niedrige confidence.
Du entscheidest nicht über Löschen, Verschieben oder Archivierung.
Du setzt keine Tags. Du klassifizierst nur.
```

### User Payload (JSON)

```json
{
  "blob_name": "docs/Vertrag_2024.docx",
  "extension": ".docx",
  "size_bytes": 24576,
  "route_strategy": "office_text",
  "rule_result": {
    "class": "unknown",
    "confidence": 30,
    "reason_code": "no_rule_match"
  },
  "text_extract": "...max 2000 Zeichen...",
  "allowed_classes": ["br","contract","dsgvo","finance","hr","technical","unknown","unreadable"]
}
```

---

## 8. JSON-Schema

Die KI darf **ausschließlich** dieses JSON zurückgeben:

```json
{
  "status": "classified|unknown|unreadable",
  "class": "br|dsgvo|hr|finance|contract|technical|unknown|unreadable",
  "dsgvo": true,
  "archive_candidate": true,
  "confidence": 0,
  "readable": true,
  "reason_code": "ai_content_match",
  "explanation_short": "max 200 Zeichen"
}
```

**Validierungsregeln:**

| Feld | Regel |
|---|---|
| `class` | Muss in `allowed_classes` sein |
| `status` | `classified`, `unknown` oder `unreadable` |
| `confidence` | Integer 0–100 |
| `dsgvo` | Boolean |
| `archive_candidate` | Boolean |
| `readable` | Boolean |
| `explanation_short` | max. 200 Zeichen |
| `reason_code` | `lowercase_snake_case`, kein Leerzeichen |

**Fehlercodes bei Validierungsproblemen:**

| Fehler | `ai_error` Code |
|---|---|
| Kein API Key | `missing_api_key` |
| Kein valides JSON | `invalid_json` |
| Schemafehler | `schema_validation_failed` |
| Rate Limit | `rate_limited` |
| API-Fehler | `provider_error` |

---

## 9. Tokenzählung

Vor dem API-Call:
- `ai_prompt_chars` – Gesamtlänge System + User Prompt (Zeichen)
- `ai_text_extract_chars` – Länge des Text-Extracts
- `ai_estimated_prompt_tokens` – Schätzung: `ceil(chars / 4)`

> **Hinweis:** Die Schätzung `ceil(chars / 4)` ist eine einfache Heuristik.
> Sie ist **nicht exakt** – verwende `provider_usage` wenn verfügbar.

Nach dem API-Call (aus `response.usage`):
- `ai_prompt_tokens` – tatsächliche Prompt-Token (Provider)
- `ai_completion_tokens` – tatsächliche Completion-Token
- `ai_total_tokens` – Summe
- `ai_token_source` – `provider_usage` | `estimated`

---

## 10. Reporting-Felder

### classification-details.csv (pro Datei)

| Feld | Beschreibung |
|---|---|
| `ai_called` | War AI aktiv? |
| `ai_success` | Valides Ergebnis? |
| `ai_error` | Fehlercode |
| `ai_model` | Genutztes Modell |
| `ai_prompt_version` | Promptversion |
| `ai_prompt_chars` | Prompt-Zeichen gesamt |
| `ai_text_extract_chars` | Text-Extract-Zeichen |
| `ai_estimated_prompt_tokens` | Geschätzte Tokens |
| `ai_prompt_tokens` | Tokens laut Provider |
| `ai_completion_tokens` | Completion-Tokens |
| `ai_total_tokens` | Gesamt-Tokens |
| `ai_token_source` | `provider_usage` / `estimated` |
| `ai_latency_ms` | Antwortzeit in ms |
| `ai_class` | KI-Klassifikation |
| `ai_confidence_ai` | KI-Konfidenz |
| `ai_reason_code_ai` | KI-Reason-Code |
| `ai_explanation_short` | KI-Erklärung |

### run-summary.json

Enthält AI-Summierung: `ai_model`, `ai_prompt_version`, `ai_prompt_tokens_total`,
`ai_completion_tokens_total`, `ai_total_tokens`, `ai_latency_ms_avg`, etc.

### admin-report.json / admin-report.pdf

Enthält AI-Abschnitt mit: Provider, Modell, Promptversion, Calls, Tokens,
Fehler, Durchschnitt Tokens/Datei, AI-Erfolgsquote, Hinweis Dry Run.

---

## 11. Dry-Run-Testablauf

### Vorbereitung

```powershell
# .env setzen
ENABLE_AI=true
AI_PROVIDER=groq
AI_MODEL=llama-3.3-70b-versatile
AI_MAX_CALLS_PER_RUN=3
AI_MAX_CHARS_PER_FILE=2000
AI_WRITE_TAGS=false

# Secret setzen (nicht ins .env!)
$env:GROQ_API_KEY="gsk_..."
```

### Testbefehl (Docker)

```powershell
docker compose run --rm worker `
  --mode classify `
  --dry-run `
  --prefix "_root_part000/" `
  --max-files 3
```

### Testbefehl (lokal)

```powershell
python -m app.main `
  --mode classify `
  --dry-run `
  --prefix "_root_part000/" `
  --max-files 3
```

---

## 12. Erwartete Ergebnisse

Nach dem Testlauf:

- Max. 3 AI-Calls (limitiert durch `AI_MAX_CALLS_PER_RUN=3`)
- **Keine Tags** in Azure geschrieben (`AI_WRITE_TAGS=false` + `--dry-run`)
- **Keine Metadata** in Azure geschrieben
- Reports lokal oder in Azure (je nach `UPLOAD_REPORTS`):
  - `run-summary.json`: enthält `ai_model`, `ai_prompt_tokens_total`, etc.
  - `classification-details.csv`: enthält pro Datei alle Token-Felder
  - `admin-report.json`: enthält AI-Summary-Block
  - `admin-report.pdf`: enthält KI-Abschnitt

---

## 13. Fehlerfälle

| Situation | Ergebnis |
|---|---|
| GROQ_API_KEY fehlt | `ai_error=missing_api_key`, Datei bleibt `class=unknown` |
| Kein Text-Extract | `ai_called=false`, `ai_skipped_reason=no_text_extract` |
| Rate Limit | `ai_error=rate_limited`, nächste Datei wird versucht |
| Invalides JSON | `ai_error=invalid_json`, class bleibt rule-basiert |
| Schemafehler | `ai_error=schema_validation_failed` |
| Budget erschöpft | `ai_skipped_reason=budget_exhausted` |

---

## 14. Offene Punkte

- [ ] Echter Test mit max. 3 Dateien durchführen
- [ ] Token-Kosten bewerten (Free Tier Limit: 14.400 req/Tag)
- [ ] Latenz-Messung validieren
- [ ] Prompt v1 für spezifischere GEMA-Kategorien optimieren
- [ ] EU-Lizenz Llama 4 Multimodal prüfen (für spätere Vision-Klassifikation)
- [ ] Azure AI Foundry als zweite Stufe evaluieren

---

## 15. Nächste Stufe: echtes Tagging

Wenn der Dry Run erfolgreich ist und die Ergebnisse valide aussehen:

1. `AI_WRITE_TAGS=true` setzen
2. `--dry-run` Flag weglassen
3. Budget erhöhen: `AI_MAX_CALLS_PER_RUN=20` o.ä.
4. Monitoring aufbauen (Token-Kosten, Confidence-Verteilung)
5. Bei niedrigem Vertrauen: manuelle Überprüfung vor Skalierung
