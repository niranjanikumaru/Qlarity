# ==========================================
# Qlarity-Yield: Semiconductor Leakage Workbench
# Subfolder Dockerfile
# ==========================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALLOW_REMOTE=true \
    HOST=0.0.0.0 \
    PORT=8000 \
    ALLOWED_HOSTS="*"

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt

COPY backend/ ./backend/
COPY web/ ./web/
COPY evidence/ ./evidence/
COPY docs/ ./docs/
COPY pytest.ini .
COPY README.md .

RUN useradd -m -u 1001 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/model || exit 1

ENTRYPOINT ["python", "-m", "uvicorn", "backend.serve:app"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
