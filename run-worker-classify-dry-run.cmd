@echo off
REM Dry-Run Classify: simuliert Klassifizierung.
REM Schreibt KEINE Blob Tags und KEINE Blob Metadata nach Azure.
docker compose run --rm worker --mode classify --dry-run --max-files 50 %*
