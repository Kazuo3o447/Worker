@echo off
REM Run the worker locally using Python.
REM Requires: pip install -r requirements.txt
REM Requires: az login  (or AZURE_STORAGE_CONNECTION_STRING in .env)
REM
REM Usage:
REM   run-local.cmd                                     -> scan, max 50 files
REM   run-local.cmd --mode classify --dry-run           -> dry-run classify
REM   run-local.cmd --mode classify --max-files 50      -> real classify
REM   run-local.cmd --mode report                       -> aggregate report

python -m app.main --mode scan --max-files 50 %*
