# Azure Container Apps Deployment Plan

## Ziel

Worker und Dashboard als getrennte Container in Azure betreiben:
- **Worker**: Azure Container Apps Job (manuell oder zeitgesteuert)
- **Dashboard**: Azure Container App (Dauerläufer, Port 8501)

---

## Voraussetzungen

```bash
# Azure CLI
az extension add --name containerapp
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
```

---

## 1 · Container Registry

```bash
# Azure Container Registry erstellen
az acr create \
  --name acrgemaclassifier \
  --resource-group rg-gema-storage-classification-pilot \
  --sku Basic

# Images bauen und pushen
az acr build \
  --registry acrgemaclassifier \
  --image gema-classifier-worker:v0 \
  --file Dockerfile \
  .

az acr build \
  --registry acrgemaclassifier \
  --image gema-classifier-dashboard:v0 \
  --file frontend/Dockerfile \
  ./frontend
```

---

## 2 · Container Apps Environment

```bash
az containerapp env create \
  --name gema-classifier-env \
  --resource-group rg-gema-storage-classification-pilot \
  --location westeurope
```

---

## 3 · Managed Identity

```bash
# User-Assigned Managed Identity erstellen
az identity create \
  --name gema-classifier-identity \
  --resource-group rg-gema-storage-classification-pilot

# Principal ID für RBAC
PRINCIPAL_ID=$(az identity show \
  --name gema-classifier-identity \
  --resource-group rg-gema-storage-classification-pilot \
  --query principalId -o tsv)

STORAGE_ID=$(az storage account show \
  --name stgemaclasspilot001 \
  --resource-group rg-gema-storage-classification-pilot \
  --query id -o tsv)
```

### Benötigte RBAC-Berechtigungen

| Rolle | Scope | Zweck |
|-------|-------|-------|
| `Storage Blob Data Reader` | `cool-stage-test` Container | Blobs listen, Tags lesen |
| `Storage Blob Data Contributor` | `cool-stage-test` Container | Tags + Metadata schreiben |
| `Storage Blob Data Contributor` | `reports` Container | Reports hochladen |

```bash
# Berechtigungen zuweisen
COOL_STAGE_ID="$STORAGE_ID/blobServices/default/containers/cool-stage-test"
REPORTS_ID="$STORAGE_ID/blobServices/default/containers/reports"

az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$COOL_STAGE_ID"

az role assignment create \
  --assignee-object-id "$PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope "$REPORTS_ID"
```

---

## 4 · Worker als Azure Container Apps Job

```bash
IDENTITY_ID=$(az identity show \
  --name gema-classifier-identity \
  --resource-group rg-gema-storage-classification-pilot \
  --query id -o tsv)

az containerapp job create \
  --name gema-classifier-job \
  --resource-group rg-gema-storage-classification-pilot \
  --environment gema-classifier-env \
  --image acrgemaclassifier.azurecr.io/gema-classifier-worker:v0 \
  --trigger-type Manual \
  --replica-timeout 3600 \
  --registry-server acrgemaclassifier.azurecr.io \
  --user-assigned "$IDENTITY_ID" \
  --env-vars \
    AUTH_MODE=default \
    AZURE_STORAGE_ACCOUNT=stgemaclasspilot001 \
    SOURCE_CONTAINER=cool-stage-test \
    REPORT_CONTAINER=reports \
    WORKER_VERSION=pilot-v0.1 \
    DEFAULT_MAX_FILES=500 \
    UPLOAD_REPORTS=true \
    ENABLE_AI=false \
    AI_PROVIDER=none
```

### Job manuell starten

```bash
az containerapp job start \
  --name gema-classifier-job \
  --resource-group rg-gema-storage-classification-pilot \
  -- --mode classify --max-files 500

az containerapp job start \
  --name gema-classifier-job \
  --resource-group rg-gema-storage-classification-pilot \
  -- --mode scan --max-files 1000
```

### Job zeitgesteuert (täglich)

```bash
az containerapp job update \
  --name gema-classifier-job \
  --resource-group rg-gema-storage-classification-pilot \
  --trigger-type Schedule \
  --cron-expression "0 2 * * *" \
  -- --mode classify --max-files 1000
```

---

## 5 · Dashboard als Azure Container App

```bash
az containerapp create \
  --name gema-classifier-dashboard \
  --resource-group rg-gema-storage-classification-pilot \
  --environment gema-classifier-env \
  --image acrgemaclassifier.azurecr.io/gema-classifier-dashboard:v0 \
  --target-port 8501 \
  --ingress external \
  --registry-server acrgemaclassifier.azurecr.io \
  --user-assigned "$IDENTITY_ID" \
  --env-vars \
    AUTH_MODE=default \
    AZURE_STORAGE_ACCOUNT=stgemaclasspilot001 \
    REPORT_CONTAINER=reports \
    WORKER_VERSION=pilot-v0.1
```

> Das Dashboard liest Reports direkt aus dem Azure `reports`-Container via `AzureReportRepository`.
> Kein lokaler Volume-Mount erforderlich.

---

## 6 · Logs in Azure Log Analytics

Container Apps schreiben stdout automatisch nach Log Analytics.  
Alle Worker-Events (JSON Lines) sind sofort durchsuchbar:

```kql
// Alle Fehler des letzten Laufs
ContainerAppConsoleLogs
| where ContainerAppName == "gema-classifier-job"
| where Log contains '"level": "ERROR"'
| project TimeGenerated, Log
| order by TimeGenerated desc
```

```kql
// Klassifizierungsstatistik
ContainerAppConsoleLogs
| where Log contains '"event": "run_finished"'
| extend parsed = parse_json(Log)
| project
    run_id = parsed.run_id,
    files_processed = parsed.files_processed,
    files_error = parsed.files_error,
    gb_processed = parsed.gb_processed
```

---

## 7 · Sicherheitshinweise

- **Keine Secrets im Container**: `AZURE_STORAGE_CONNECTION_STRING` wird in Azure NICHT gesetzt.
- **Managed Identity**: `AUTH_MODE=default` nutzt automatisch die zugewiesene Managed Identity.
- **Minimale Berechtigungen**: Nur `Storage Blob Data Contributor` auf die beiden Container, nicht auf den gesamten Storage Account.
- **Ingress**: Dashboard-Ingress kann auf internes Netz beschränkt werden falls gewünscht.

---

## 8 · Kostenübersicht (Schätzung Pilot)

| Ressource | SKU | Schätzung |
|-----------|-----|-----------|
| Container Apps Environment | Consumption | ~0 (Idle) |
| Container Apps Job | Consumption | ~0,01–0,10 €/Lauf |
| Container App Dashboard | Consumption | ~5–15 €/Monat |
| Container Registry | Basic | ~5 €/Monat |
| Blob Storage Transaktionen | Standard | < 1 €/Monat (Pilot) |
