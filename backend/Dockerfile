# One image for the API, the workers and the janitor; the command differs per service.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Open-source PDF engines: qpdf (via pikepdf), Ghostscript, Tesseract (+ language packs), unpaper, pngquant.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ghostscript qpdf tesseract-ocr tesseract-ocr-eng tesseract-ocr-spa tesseract-ocr-fra \
        tesseract-ocr-deu tesseract-ocr-hin tesseract-ocr-por tesseract-ocr-ita unpaper pngquant \
        fonts-dejavu-core fonts-noto-core curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 folio
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app

RUN mkdir -p /data/work /data/files && chown -R folio /data
USER folio
ENV STORAGE_DIR=/data/files WORK_DIR=/data/work PYTHONPATH=/app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fs http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
