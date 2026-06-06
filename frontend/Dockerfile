FROM python:3.12-slim

# Security: run as non-root
# --home /home/dashboard ensures the token cache (msal-extensions) has a writable location
RUN addgroup --system dashboard \
  && adduser --system --ingroup dashboard --home /home/dashboard dashboard \
  && mkdir -p /home/dashboard \
  && chown -R dashboard:dashboard /home/dashboard

# Required so msal-extensions finds a writable home for the persistent token cache
ENV HOME=/home/dashboard

WORKDIR /app

# Install system tools (antiword for .doc extraction – same as worker container)
RUN apt-get update && apt-get install -y --no-install-recommends antiword \
  && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt ./
COPY frontend/requirements.txt ./frontend/
RUN pip install --no-cache-dir -r requirements.txt -r frontend/requirements.txt

# Copy frontend source and app source
COPY frontend/ ./frontend/
COPY app/ ./app/

RUN chown -R dashboard:dashboard /app

USER dashboard

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

WORKDIR /app/frontend

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
