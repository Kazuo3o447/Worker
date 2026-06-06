# GEMA Storage Classification Pilot – Worker: Andre3000

Regelbasierter Python-Worker zur Klassifizierung von Blobs im Azure Blob Storage, plus Streamlit **Admin-Cockpit** zur Auswertung der Ergebnisse.

**Worker-Name:** Andre3000  
**Version:** pilot-v0.1  
**Tests:** 253 ✅

---

## 1 · Zweck

Pilot zur Klassifizierung von Fileserver-Altbeständen in Azure Blob Storage.  
Der Worker liest Blobs aus `cool-stage-test`, klassifiziert regelbasiert anhand von Pfad und Dateiendung und schreibt Blob Index Tags sowie Metadata zurück.

Das **Admin-Cockpit** (10 Bereiche: Cockpit, Runs, Run Detail, Klassifizierung, KI Readiness, Dateien & Dateitypen, Fehler & Risiken, Reports & Exporte, Konfiguration, Run Commands) zeigt Ergebnisse, Health-Status und Handlungsempfehlungen an.  
Beides läuft Docker-first und kann später als Azure Container Apps Job bzw. Container App betrieben werden.

---

## 2 · Architektur

```
Worker (Batch-Job)
  └─▶ Azure Blob Storage (cool-stage-test)
      └─▶ Blobs lesen, Tags/Metadata schreiben
  └─▶ reports-Container in Azure (pilot-v0.1/<run_id>/)
      └─▶ run-summary.json, classification-details.csv, run-events.jsonl, ...

Dashboard (Dauerläufer, Port 8501)
  └─▶ reports-Container in Azure lesen & schreiben
  └─▶ Auswertung & Anpassung von Reports/Ergebnissen
```

**Wichtig**: Reports gehen nach Azure – kein lokaler reports-Ordner im produktiven Pfad.  
Das Dashboard ermöglicht auch Anpassungen und die Erstellung von Reports.

Siehe auch: [docs/architecture.md](docs/architecture.md)

---

## 3 · Voraussetzungen

| Anforderung | Details |
|-------------|--------|
| Docker Desktop | aktuelle Version |
| Zugriff auf Azure Storage | `stgemaclasspilot001` |
| Azure-Berechtigungen | `Storage Blob Data Contributor` auf `cool-stage-test` und `reports` |

Für lokale Python-Nutzung (ohne Docker) zusätzlich:
- Python 3.12+
- `pip install -r requirements.txt`

---

## 4 · Einrichtung

### .env erstellen

```cmd
copy .env.example .env
```

Für lokalen Docker-Test mit Device-Code-Login (Standard):
```
AUTH_MODE=device_code
```

Für lokale Python-Nutzung mit `az login`:
```
AUTH_MODE=default
```

### Docker-Images bauen

```cmd
docker compose build
```

---

## 5 · Erster Scan (read-only)

```cmd
docker compose run --rm worker --mode scan --max-files 50
```

Oder:
```cmd
run-worker-scan.cmd
```

Prüfe danach im Dashboard oder direkt in Azure (Container `reports`):
- `pilot-v0.1/<run_id>/run-summary.json`
- `pilot-v0.1/<run_id>/untagged-files.csv`

---

## 6 · Dashboard starten

```cmd
docker compose up dashboard
```

Oder:
```cmd
run-dashboard.cmd
```

Browser: **http://localhost:8501**

---

## 7 · Dry-Run (simuliert, kein Write nach Azure)

```cmd
docker compose run --rm worker --mode classify --dry-run --max-files 50
```

Oder:
```cmd
run-worker-classify-dry-run.cmd
```

Im Report `run-summary.json` (in Azure) ist `dry_run: true` gesetzt.  
Im Dashboard erscheint ein blauer Hinweis.

---

## 8 · Echter Testlauf mit 50 Dateien

```cmd
docker compose run --rm worker --mode classify --max-files 50
```

Oder:
```cmd
run-worker-classify.cmd
```

Danach im Admin-Cockpit prüfen:
- Cockpit → Health-Ampel, KPIs
- Klassifizierung → Klassen-Verteilung
- Fehler & Risiken → Fehlertabelle

---

## 9 · Modes im Detail

| Mode | Beschreibung | Schreibt Blob Tags | Schreibt Metadata | Lädt Reports hoch |
|------|-------------|-------------------|-------------------|--------------------|
| `scan` | Listet Blobs, erkennt Ungetaggte, lädt Scan-Reports nach Azure | **Nein** | **Nein** | Ja (wenn `UPLOAD_REPORTS=true`) |
| `classify` | Klassifiziert bis zu `--max-files` Blobs, lädt Reports nach Azure | Ja (ohne `--dry-run`) | Ja (ohne `--dry-run`) | Ja (wenn `UPLOAD_REPORTS=true`) |

**Dry-Run:** `--dry-run` verhindert das Schreiben von Blob Tags und Metadata. Reports werden trotzdem nach Azure hochgeladen, sofern `UPLOAD_REPORTS=true`.

---

## 10 · CLI-Referenz

```
python -m app.main --mode {scan|classify}
  [--max-files N]    Standard: DEFAULT_MAX_FILES aus .env (50)
  [--force]          Auch bereits klassifizierte Blobs neu verarbeiten
  [--dry-run]        Tags/Metadata NICHT schreiben; Reports trotzdem hochladen
  [--prefix PATH]    Nur Blobs mit diesem Prefix verarbeiten
  [--enable-ai]      KI-Klassifizierung aktivieren (überschreibt ENABLE_AI=false)
  [--ai-provider]    KI-Provider: none | groq | foundry
  [--ai-max-calls N] Max. KI-Aufrufe pro Lauf
```

---

## 11 · Reports

Nach jedem Lauf werden Reports automatisch nach Azure hochgeladen (wenn `UPLOAD_REPORTS=true`):

**Azure** (Container `reports`, Pfad: `pilot-v0.1/<run_id>/`):
```
run-summary.json             – Kennzahlen des Laufs (inkl. worker_name)
classification-details.csv   – Eine Zeile pro verarbeiteter Datei (inkl. needs_ai)
classification-summary.csv   – Aggregierte Key-Value-Metriken
classification-errors.csv    – Nur Fehlerfälle
untagged-files.csv           – Alle ungetaggten/retry-fähigen Dateien
classification-samples.csv   – Stichproben je Klasse
ai-candidates.csv            – KI-Kandidaten (auch wenn KI deaktiviert)
run-events.jsonl             – Strukturierter Event-Log (JSON Lines)
admin-report.json            – Konsolidierter Admin-Report inkl. risk_assessment, file_type_distribution
admin-report.pdf             – Lesbarer Admin-Report für Menschen (ReportLab, best-effort)
```

---

## 12 · Auth-Modi

| AUTH_MODE | Beschreibung | Empfehlung |
|-----------|-------------|------------|
| `device_code` | Browser-Login via Device-Code-URL | Lokaler Docker-Test |
| `default` | DefaultAzureCredential (`az login` / Managed Identity) | Lokal oder Azure |
| `connection_string` | Direkte Connection String | Nur Notfall, kein Secret ins Repo! |

### Erster Login mit device_code

1. `AUTH_MODE=device_code` in `.env` setzen
2. Worker starten
3. Im Log erscheint eine URL + Code:
   ```
   To sign in, use a web browser to open the page https://microsoft.com/devicelogin and enter the code ABCDEFGH
   ```
4. Browser öffnen, Code eingeben, anmelden
5. Worker läuft weiter

---

## 13 · Klassifikationsregeln (v0)

| Pfad/Dateiname enthält | Klasse | DSGVO | Archiv | Confidence |
|-----------------------|--------|-------|--------|------------|
| betriebsrat, br_, /br/ | br | true | true | 90 |
| dsgvo, datenschutz | dsgvo | true | true | 85 |
| personal, /hr/, human resources | hr | true | true | 80 |
| rechnung, finanz, buchhaltung, invoice | finance | false | true | 80 |
| vertrag, vereinbarung, contract | contract | false | true | 75 |
| .ps1, .json, .xml, .config, .sql, .log, .ini, .yaml, .yml | technical | false | true | 70 |
| sonst | unknown | false | false | 30 |

Regeln werden in Prioritätsreihenfolge ausgewertet (erste Übereinstimmung gewinnt).

---

## 14 · Tests ausführen

```cmd
run-tests.cmd
```

Oder lokal (aus dem Projektverzeichnis):
```cmd
set PYTHONPATH=.
python -m pytest tests/ -q
```

---

## 15 · Späterer Azure-Betrieb

### Worker als Azure Container Apps Job

```bash
az containerapp job create \
  --name gema-classifier-job \
  --resource-group rg-gema-storage-classification-pilot \
  --environment gema-classifier-env \
  --image acrgemaclassifier.azurecr.io/gema-classifier-worker:v0 \
  --trigger-type Manual \
  --env-vars AUTH_MODE=default STORAGE_ACCOUNT=stgemaclasspilot001 ...
```

### Dashboard als Azure Container App

```bash
az containerapp create \
  --name gema-classifier-dashboard \
  --resource-group rg-gema-storage-classification-pilot \
  --image acrgemaclassifier.azurecr.io/gema-classifier-dashboard:v0 \
  --target-port 8501 --ingress external ...
```

Detaillierter Plan: [docs/azure-container-apps-plan.md](docs/azure-container-apps-plan.md)

---

## 16 · Benötigte Azure-Berechtigungen

Die Managed Identity des Workers braucht auf `stgemaclasspilot001`:

| Rolle | Container | Zweck |
|-------|-----------|-------|
| `Storage Blob Data Contributor` | `cool-stage-test` | Tags + Metadata schreiben, lesen |
| `Storage Blob Data Contributor` | `reports` | Reports hochladen |

---

## 17 · Nächste Ausbaustufen

- [x] Office/PDF-Textextraktion (antiword für .doc, PyMuPDF für .pdf)
- [x] LLM-Klassifikation (Groq/llama-3.3-70b-versatile) für `class=unknown` oder `confidence < 60`
- [x] Worker als unabhängiger Subprocess (Frontend-Absturz beendet nicht den Lauf)
- [x] AuthenticationRecord-Persistenz (kein erneutes Device-Code-Login nach Restart)
- [x] Timezone-korrekte Anzeige (UTC → Europe/Berlin)
- [ ] Lifecycle-Regel (automatisches Archivieren/Löschen nach Klassifikation)
- [ ] Review-Workflow (Fachbereich bestätigt Klassifikation)
- [ ] Azure Container Apps Job zeitgesteuert (täglich)
- [ ] CI/CD Pipeline (GitHub Actions)

