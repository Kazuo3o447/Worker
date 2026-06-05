@echo off
REM Build the Docker image and run a scan (read-only, no writes to Azure tags).
REM Reports are written to .\local-reports\ via volume mount.
REM
REM Usage:
REM   run-docker.cmd                         -> scan, max 50 files
REM   run-docker.cmd --mode classify --dry-run --max-files 10

docker build -t gema-storage-classifier:v0 .

docker run --rm ^
  --env-file .env ^
  -v "%cd%\local-reports:/app/local-reports" ^
  gema-storage-classifier:v0 ^
  --mode scan --max-files 50 %*
