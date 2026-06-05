# Operating Model – GEMA Storage Classification Pilot v0

## Testphasen und empfohlene Reihenfolge

### Phase 1 – Scan (read-only)

```cmd
docker compose run --rm worker --mode scan --max-files 50
```

**Zweck**: Überblick verschaffen, bevor irgendetwas geschrieben wird.  
**Prüfe im Dashboard oder direkt in Azure** (Container `reports`, Pfad `pilot-v0.1/<run_id>/`):
- `untagged-files.csv` → welche Dateien sind ungetaggt?
- `run-summary.json` → `files_seen`, `files_untagged`
- Dashboard → 🏠 Übersicht und 🔍 Ungetaggte Dateien

### Phase 2 – Dry Run Classify

```cmd
docker compose run --rm worker --mode classify --dry-run --max-files 50
```

**Zweck**: Klassifikationslogik prüfen, ohne in Azure zu schreiben.  
**Prüfe im Dashboard** (Reports werden auch im Dry-Run nach Azure hochgeladen):
- `classification-details.csv` → welche Klassen werden vergeben?
- `classification-samples.csv` → stimmen die Stichproben fachlich?
- `dry_run: true` in `run-summary.json`
- Dashboard → 📊 Klassenverteilung und 🧪 Stichproben

### Phase 3 – Echter Testlauf

```cmd
docker compose run --rm worker --mode classify --max-files 50
```

**Zweck**: Erste echte Klassifizierung mit 50 Dateien.  
**Prüfe**:
- Blob Index Tags in Azure Storage (Azure Portal → Storage Account → Container → Blob Properties)
- `classification-errors.csv` im Reports-Container → Fehlerrate
- Dashboard → ❌ Fehler

### Phase 4 – Wiederholung und Skalierung

```cmd
docker compose run --rm worker --mode classify --max-files 500
```

Wiederhole mit mehr Dateien, bis alle Blobs klassifiziert sind.

---

## Fehleranalyse

### Wo Fehler finden

| Report | Inhalt |
|--------|--------|
| `classification-errors.csv` | Fehler pro Blob mit Stufe und Meldung |
| `run-events.jsonl` | Timeline aller Events, Level=ERROR herausfiltern |
| Dashboard → ❌ Fehler | Visuelle Auflistung mit Filtermöglichkeit |
| Dashboard → 📝 Logs | Alle Events, nach ERROR/WARNING filtern |

### Häufige Fehlerursachen

| Fehler | Ursache | Lösung |
|--------|---------|--------|
| `tags_write_failed: 403` | Fehlende RBAC-Berechtigung | `Storage Blob Data Contributor` vergeben |
| `Cannot connect to Azure Storage` | Auth fehlgeschlagen | `az login` oder `AUTH_MODE` prüfen |
| `DeviceCodeCredential` Timeout | Kein Login im Browser | Login-URL im Log aufrufen |
| `metadata_write_failed` | Metadata-Key ungültig | `validation.py` prüfen |

### Blobs mit Fehler erneut verarbeiten

Blobs mit `status=error` werden beim nächsten Lauf **automatisch** erneut verarbeitet (Retry-Logik).  
Mit `--force` werden auch `classified`/`skipped`/`unreadable` neu verarbeitet.

---

### Monitoring-Kennzahlen

Diese Metriken sollten nach jedem Lauf überwacht werden:

| Metrik | Quelle | Schwellwert |
|--------|--------|-------------|
| `files_error` | run-summary.json | > 5% → Ursache untersuchen |
| `files_unknown` | run-summary.json | > 40% → Regeln erweitern oder KI planen |
| `files_untagged` | run-summary.json | sinkend → Fortschritt |
| `throughput_gb_per_hour` | run-summary.json | < 0.1 → Performance prüfen |
| `throughput_files_per_hour` | run-summary.json | Referenzwert für Planung |
| `llm_used_count` | run-summary.json | KI-Aufrufe dieses Laufs |
| `rules_only_count` | run-summary.json | Rein regelbasiert klassifiziert |
| `reports_uploaded` | run-summary.json | `false` → Azure-Upload prüfen |

### KI-Readiness-Metriken

| Metrik | Bedeutung |
|--------|-----------|
| `class_unknown` | Dateien ohne Regeltreff → KI-Kandidaten |
| `confidence < 60` | Unsichere Klassifikationen → manuelle Prüfung oder KI |
| `ai_candidates` | Blobs, die KI-Kandidaten waren (auch wenn KI deaktiviert) |
| `ai_calls_used` | Tatsächliche KI-Aufrufe (0 wenn `ENABLE_AI=false`) |

### Dashboard-Indikatoren (täglich prüfen)

- 🔴 `files_error > 0` → sofort untersuchen
- 🟡 `files_unknown / files_processed > 0.3` → Regeln nachjustieren
- 🟢 `files_untagged → 0` → Pilot abgeschlossen

---

## Reports und ihre Bedeutung

| Datei | Wann wichtig |
|-------|-------------|
| `run-summary.json` | Erster Überblick nach jedem Lauf (35 Felder, inkl. timing + KI-Stats) |
| `classification-details.csv` | Detailanalyse, Stichprobenprüfung |
| `classification-summary.csv` | Aggregierte Kennzahlen für Reporting |
| `classification-errors.csv` | Fehleranalyse und Retry-Planung |
| `untagged-files.csv` | Fortschrittsübersicht |
| `classification-samples.csv` | Fachliche Prüfung der Klassifikationsqualität |
| `ai-candidates.csv` | KI-Kandidaten (auch wenn KI deaktiviert, für Planung) |
| `run-events.jsonl` | Technisches Debugging |

---

## Nützliche Befehle

```cmd
:: Nur einen Ordner verarbeiten
docker compose run --rm worker --mode classify --prefix "_root_part000/" --max-files 50

:: Fehlerhafte Blobs erneut verarbeiten (retry)
:: Passiert automatisch, da status=error erneut verarbeitet wird
docker compose run --rm worker --mode classify --max-files 50

:: Alle Blobs neu klassifizieren (force reset)
docker compose run --rm worker --mode classify --force --max-files 50

:: Mit KI-Klassifizierung (AI Foundry muss konfiguriert sein)
docker compose run --rm worker --mode classify --enable-ai --ai-provider foundry --ai-max-calls 20

:: Tests lokal ausführen
python -m pytest tests/ -v
```
