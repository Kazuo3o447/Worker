@echo off
REM Echter Classify-Lauf: schreibt Blob Index Tags und Blob Metadata.
REM Verarbeitet maximal 50 Dateien (aenderbar per --max-files).
docker compose run --rm worker --mode classify --max-files 50 %*
