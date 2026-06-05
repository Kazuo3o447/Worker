@echo off
REM Tests lokal ausfuehren (aus dem Projektverzeichnis)
cd /d "%~dp0"
set PYTHONPATH=%~dp0
python -m pytest tests/ -q
