# Backend FastAPI — image produksi, berjalan sebagai user NON-ROOT (anti-root).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Anti-root: buat user dengan hak akses sangat terbatas, lalu jalankan aplikasi sebagai user itu.
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
# Runtime server for container execution; production readiness is gated separately.
CMD ["gunicorn", "api:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "120"]
