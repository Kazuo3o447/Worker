@echo off
REM Tests ausfuehren (innerhalb des Worker-Containers)
docker compose build worker
docker compose run --rm worker python -m pytest tests/ -v
