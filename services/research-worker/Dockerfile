FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/atlas-research-worker
RUN addgroup --system atlasresearch && adduser --system --ingroup atlasresearch --home /nonexistent atlasresearch \
    && pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1" "httpx>=0.27,<1"
COPY app.py ./app.py
USER atlasresearch
EXPOSE 8093
HEALTHCHECK --interval=15s --timeout=5s --retries=10 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8093/health')"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8093"]
