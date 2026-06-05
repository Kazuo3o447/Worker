FROM python:3.12-slim

# Security: run as non-root
RUN addgroup --system worker && adduser --system --ingroup worker worker

WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/

RUN chown -R worker:worker /app

USER worker

ENTRYPOINT ["python", "-m", "app.main"]
