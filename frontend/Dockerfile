FROM python:3.12-slim

# Security: run as non-root
RUN addgroup --system dashboard && adduser --system --ingroup dashboard dashboard

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy frontend source
COPY . .

RUN chown -R dashboard:dashboard /app

USER dashboard

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
