# Azure AI Foundry Integration – Leitfaden

## Status: v0 (vorbereitet, standardmäßig deaktiviert)

Die KI-Integration ist vollständig vorbereitet und kann per Umgebungsvariablen aktiviert werden.
Im Produktionsbetrieb empfehlen wir den Start mit `AI_MAX_CALLS_PER_RUN=20` und schrittweiser Erhöhung.

---

## Aktivierung

### Schritt 1: Azure AI Foundry Ressource anlegen

Im Azure Portal:
1. "Azure AI Services" oder "Azure OpenAI Service" erstellen
2. Deployment anlegen (z.B. `gpt-4o`)
3. Endpoint-URL und Deployment-Name notieren

### Schritt 2: Umgebungsvariablen setzen

```ini
# .env oder Azure Container Apps Secrets
ENABLE_AI=true
AI_PROVIDER=foundry
AI_FOUNDRY_ENDPOINT=https://<resource-name>.openai.azure.com/
AI_FOUNDRY_MODEL_DEPLOYMENT=gpt-4o
AI_FOUNDRY_API_VERSION=2024-02-01

# Lokale Tests mit API Key (nicht ins Repo!):
# AI_FOUNDRY_API_KEY=<api-key>

# Managed Identity in Azure (empfohlen für Produktion):
# AUTH_MODE=default  (verwendet DefaultAzureCredential)
```

### Schritt 3: KI-Kandidaten prüfen (ohne echte Aufrufe)

```bash
# Dry Run mit KI aktiviert: zeigt welche Blobs KI-Kandidaten wären
docker compose run --rm worker --mode classify --dry-run --enable-ai --ai-provider foundry
```

### Schritt 4: Echter Lauf mit KI

```bash
# Mit Budget-Limit
docker compose run --rm worker --mode classify --enable-ai --ai-provider foundry --ai-max-calls 10
```

---

## Architektur

```
Blob
  ↓
classifier_rules.classify_blob()
  ↓
ai_policy.should_call_ai()
  ↓ (nur wenn Kandidat + Budget + kein Block)
ai_foundry_client.AIFoundryClient.classify()
  → AzureOpenAI Chat Completions API
  → Response Validierung (class, status, confidence, booleans)
  ↓
ClassificationResult (mit ai_candidate=True, llm_used="true")
  ↓
AzureBlobRepository.set_blob_tags() + set_blob_metadata()
  ↓
Reports → Azure reports container
```

---

## Response-Format

Der AI-Client erwartet von Azure AI Foundry ein JSON-Objekt:

```json
{
  "status": "classified",
  "class": "hr",
  "dsgvo": "false",
  "archive_candidate": "true",
  "confidence": "78",
  "readable": "true",
  "reason_code": "llm_path_match",
  "explanation_short": "Dateiname enthält HR-Bezug"
}
```

Erlaubte Werte:
- `class`: br, dsgvo, hr, finance, contract, technical, unknown, unreadable
- `status`: classified, skipped, error, unreadable
- `confidence`: "0" bis "100"
- `dsgvo`, `archive_candidate`, `readable`: "true" oder "false"

Bei ungültigen Werten wird der AI-Aufruf als Fehler gezählt und die Regel-Klassifikation beibehalten.

---

## Authentifizierung

| Umgebung | AUTH_MODE | Credential |
|----------|-----------|-----------|
| Lokal (mit .env + API Key) | device_code | API Key via `AI_FOUNDRY_API_KEY` |
| Lokal (az login) | default | `DefaultAzureCredential` |
| Azure Container Apps | default | Managed Identity + `DefaultAzureCredential` |

Für Managed Identity muss die Container Apps Managed Identity die Rolle  
**"Cognitive Services OpenAI User"** auf der Azure OpenAI Ressource haben.

---

## Monitoring

Im `run-summary.json` nach jedem Lauf:

```json
{
  "enable_ai": true,
  "ai_provider": "foundry",
  "ai_max_calls_per_run": 20,
  "ai_calls_used": 12,
  "ai_calls_skipped": 8,
  "ai_errors": 0,
  "ai_candidates": 20,
  "llm_used_count": 12,
  "rules_only_count": 38
}
```

Im Dashboard: **🤖 KI-Analyse** Seite zeigt Kandidaten, Aufrufe und Ergebnisse.

---

## Fehlerbehandlung

- Netzwerkfehler → `ai_error` Event im run-events.jsonl, Regel-Klassifikation bleibt
- Ungültige JSON-Response → als Fehler gezählt
- Budget erschöpft → restliche Blobs ohne KI klassifiziert (Kandidaten weiter gezählt)
- Fehlende Konfiguration → Worker startet ohne KI (Non-fatal), Warnung im Log
