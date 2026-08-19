FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system dependencies (e.g. for building packages if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and pyproject
COPY pyproject.toml .
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -e .

# Copy application code
COPY src/ /app/src/
COPY models/ /app/models/

# The API does not need root privileges.  Keeping the runtime user unprivileged
# limits the impact of a parser/dependency vulnerability in an uploaded log.
RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

# Expose the API port
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"

# Run the FastAPI server
CMD ["python", "-m", "uvicorn", "src.web.app:app", "--host", "0.0.0.0", "--port", "8000"]
