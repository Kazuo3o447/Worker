@echo off
REM Scan-Lauf: listet Blobs, erkennt ungetaggte Dateien.
REM Schreibt KEINE Blob Tags und KEINE Blob Metadata.
docker compose run --rm worker --mode scan --max-files 50 %*
