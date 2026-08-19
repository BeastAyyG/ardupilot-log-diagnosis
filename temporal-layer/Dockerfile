FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

RUN addgroup --system app && adduser --system --ingroup app app \
    && chown -R app:app /app
USER app

# Expose API port
EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=3).read()"

# Start the FastAPI service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
