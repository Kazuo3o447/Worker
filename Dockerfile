FROM python:3.12-slim

# Security: run as non-root
RUN addgroup --system worker && adduser --system --ingroup worker --home /home/worker worker \
  && mkdir -p /home/worker && chown -R worker:worker /home/worker

# Token cache needs a writable home directory
ENV HOME=/home/worker

WORKDIR /app

# Install system tools for extraction
RUN apt-get update && apt-get install -y --no-install-recommends \
    antiword \
  && rm -rf /var/lib/apt/lists/*

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/

RUN chown -R worker:worker /app

USER worker

ENTRYPOINT ["python", "-m", "app.main"]
