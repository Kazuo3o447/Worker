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
  └─▶ reports-Container in Azure lesen
  └─▶ Nur anzeigen, nichts schreiben
```

**Wichtig**: Der Worker ist die einzige Komponente, die Blob Tags und Metadata schreibt.  
Reports gehen ausschließlich nach Azure – kein lokaler reports-Ordner im produktiven Pfad.  
Das Dashboard ist rein lesend.

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
  [--ai-provider]    KI-Provider: none | foundry
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

- [ ] Office/PDF-Textextraktion (nur Metadaten, kein vollständiger Download)
- [ ] LLM-Klassifikation (Azure OpenAI) für `class=unknown` oder `confidence < 60`
- [ ] Lifecycle-Regel (automatisches Archivieren/Löschen nach Klassifikation)
- [ ] Review-Workflow (Fachbereich bestätigt Klassifikation)
- [ ] Azure Container Apps Job zeitgesteuert (täglich)
- [ ] Dashboard-Zugriff auf Azure `reports`-Container (`ENABLE_AZURE_REPORT_BROWSER=true`)

---

## 1 · Voraussetzungen

| Tool | Mindestversion |
|------|---------------|
| Python | 3.12 |
| pip | aktuell |
| Docker Desktop | optional, für Container-Betrieb |
| Azure CLI (`az`) | optional, für lokalen Login ohne Connection String |

---

## 2 · Lokale Einrichtung

```cmd
cd storage-classification-pilot

:: Virtuelle Umgebung anlegen (empfohlen)
python -m venv .venv
.venv\Scripts\activate

:: Abhängigkeiten installieren
pip install -r requirements.txt

:: .env aus Vorlage erstellen
copy .env.example .env
```

Passe `.env` nach Bedarf an.  
Für den lokalen Betrieb reicht entweder:
- `az login` (DefaultAzureCredential nutzt das CLI-Token), **oder**
- `AZURE_STORAGE_CONNECTION_STRING` in `.env` setzen.

---

## 3 · Lokaler Start mit Python

```cmd
:: Schritt 1: Erst einen Scan machen (read-only)
python -m app.main --mode scan --max-files 50

:: Schritt 2: Dry-run classify (keine Writes nach Azure)
python -m app.main --mode classify --dry-run --max-files 50

:: Schritt 3: Echter classify-Lauf mit 50 Dateien
python -m app.main --mode classify --max-files 50

:: Aggregierten Report erzeugen
python -m app.main --mode report

:: Nur einen bestimmten Ordner verarbeiten
python -m app.main --mode classify --prefix "betriebsrat/" --max-files 20

:: Bereits klassifizierte Dateien neu verarbeiten
python -m app.main --mode classify --force --max-files 50
```

Oder einfach die CMD-Wrapper nutzen:
```cmd
run-local.cmd
run-local.cmd --mode classify --dry-run
run-local.cmd --mode classify --max-files 50
```

---

## 4 · Start mit Docker

```cmd
:: Bauen + Scan starten
run-docker.cmd

:: Classify mit dry-run
run-docker.cmd --mode classify --dry-run --max-files 50

:: Echter classify-Lauf
run-docker.cmd --mode classify --max-files 50
```

Manuell:
```cmd
docker build -t gema-storage-classifier:v0 .

docker run --rm ^
  --env-file .env ^
  -v "%cd%\local-reports:/app/local-reports" ^
  gema-storage-classifier:v0 ^
  --mode classify --dry-run --max-files 50
```

---

## 5 · Modes

| Mode | Beschreibung | Schreibt nach Azure |
|------|-------------|---------------------|
| `scan` | Listet alle Blobs, erkennt ungetaggte Dateien, schreibt Reports | **Nein** |
| `classify` | Klassifiziert bis zu `--max-files` ungetaggte Blobs, setzt Tags und Metadata | Ja (außer `--dry-run`) |
| `report` | Liest vorhandene Tags, erzeugt aggregierten Report | **Nein** |

---

## 6 · Reports

Nach jedem Lauf werden Reports erzeugt:

**Lokal** (Standard):
```
local-reports/<run_id>/
  run-summary.json
  classification-details.csv
  classification-summary.csv
  classification-errors.csv
  untagged-files.csv
  classification-samples.csv
```

**Azure** (Container `reports`):
```
pilot-v0.1/<run_id>/
  run-summary.json
  classification-details.csv
  ...
```

Upload deaktivieren: `--upload-reports false`  
Lokale Reports deaktivieren: `--write-local-reports false`

---

## 7 · Empfohlene Startreihenfolge

### Schritt 1 – Scan (read-only)
```cmd
python -m app.main --mode scan --max-files 50
```
Prüfe `local-reports/<run_id>/untagged-files.csv` und `run-summary.json`.

### Schritt 2 – Dry-run classify
```cmd
python -m app.main --mode classify --dry-run --max-files 50
```
Keine Writes nach Azure. Reports zeigen was klassifiziert _würde_.

### Schritt 3 – Echter classify-Lauf
```cmd
python -m app.main --mode classify --max-files 50
```
Klassifiziert 50 Blobs, schreibt Blob Index Tags und Metadata.

### Schritt 4 – Report
```cmd
python -m app.main --mode report
```
Aggregiert alle vorhandenen Tags zum Gesamtbericht.

---

## 8 · CLI-Referenz

```
python -m app.main --mode {scan|classify|report}
  [--max-files N]            Default: aus .env DEFAULT_MAX_FILES (50)
  [--force]                  Auch bereits klassifizierte Blobs neu verarbeiten
  [--dry-run]                Keine Writes nach Azure (Tags, Metadata, Reports)
  [--prefix PATH]            Nur Blobs mit diesem Prefix verarbeiten
  [--upload-reports true|false]      Default: true
  [--write-local-reports true|false] Default: true
```

---

## 9 · Deployment als Azure Container Apps Job

1. Docker-Image in **Azure Container Registry** pushen:
   ```bash
   az acr build --registry <acr-name> --image gema-classifier:v0 .
   ```

2. **Container Apps Job** anlegen:
   ```bash
   az containerapp job create \
     --name gema-classifier-job \
     --resource-group rg-gema-storage-classification-pilot \
     --environment <env-name> \
     --image <acr-name>.azurecr.io/gema-classifier:v0 \
     --trigger-type Manual \
     --replica-timeout 1800 \
     --env-vars \
       STORAGE_ACCOUNT=stgemaclasspilot001 \
       SOURCE_CONTAINER=cool-stage-test \
       REPORT_CONTAINER=reports \
       WORKER_VERSION=pilot-v0.1 \
       DEFAULT_MAX_FILES=500
   ```

3. Job manuell starten:
   ```bash
   az containerapp job start \
     --name gema-classifier-job \
     --resource-group rg-gema-storage-classification-pilot \
     -- --mode classify --max-files 500
   ```

**Kein `AZURE_STORAGE_CONNECTION_STRING` nötig** – in Azure nutzt der Container die **Managed Identity** über `DefaultAzureCredential`.

---

## 10 · Benötigte Azure-Berechtigungen

Die **Managed Identity** des Container Apps Jobs benötigt auf dem Storage Account `stgemaclasspilot001`:

| Rolle | Zweck |
|-------|-------|
| `Storage Blob Data Reader` | Blobs listen, Tags und Metadata lesen |
| `Storage Blob Data Contributor` | Tags und Metadata schreiben |
| `Storage Blob Index Tags Contributor` | Blob Index Tags schreiben (falls separate Rolle nötig) |

Für den **reports-Container** zusätzlich:
| Rolle | Zweck |
|-------|-------|
| `Storage Blob Data Contributor` | Report-Dateien hochladen |

RBAC-Zuweisung (Beispiel):
```bash
az role assignment create \
  --assignee <managed-identity-principal-id> \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/<sub-id>/resourceGroups/rg-gema-storage-classification-pilot/providers/Microsoft.Storage/storageAccounts/stgemaclasspilot001
```

---

## 11 · Klassifikationsregeln (v0)

| Pfad/Dateiname enthält | Klasse | DSGVO | Archiv | Confidence |
|-----------------------|--------|-------|--------|-----------|
| betriebsrat, br_, /br/ | br | true | true | 90 |
| personal, /hr/, human resources | hr | true | true | 80 |
| rechnung, finanz, buchhaltung, invoice | finance | false | true | 80 |
| vertrag, vereinbarung, contract | contract | false | true | 75 |
| .ps1, .json, .xml, .config, .sql, .log | technical | false | true | 70 |
| sonst | unknown | false | false | 30 |

Regeln werden in Prioritätsreihenfolge ausgewertet (erste Übereinstimmung gewinnt).

---

## 12 · Tests ausführen

```cmd
pytest tests/ -v
```

---

## 13 · Erweiterungen (geplant)

- [ ] LLM-Klassifikation (Azure OpenAI) für `class=unknown`
- [ ] Office/PDF-Textextraktion (nur Metadaten, kein vollständiger Download)
- [ ] Frontend/Dashboard auf Basis der Reports
- [ ] Scheduled Container Apps Job (täglich)
- [ ] Quarantäne-Logik für `dsgvo=true` Dateien
