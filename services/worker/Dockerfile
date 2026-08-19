FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/atlas-worker

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium git \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system atlasworker && adduser --system --ingroup atlasworker --home /nonexistent atlasworker

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[test]"

COPY services/worker/app.py ./app.py
RUN mkdir -p /workspaces && chown atlasworker:atlasworker /workspaces
USER atlasworker
EXPOSE 8092
HEALTHCHECK --interval=15s --timeout=5s --retries=10 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8092/health')"]
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8092"]
