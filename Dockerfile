FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system atlasstudio && adduser --system --ingroup atlasstudio --home /nonexistent atlasstudio
COPY pyproject.toml README.md IMPLEMENTATION.md SECURITY.md ./
COPY src ./src
COPY tests ./tests
COPY skills ./skills
# Keep the verification runner in the app image so the documented
# `python -m pytest` command works in a clean, one-command deployment.
RUN pip install --no-cache-dir --retries 10 --timeout 120 ".[test]"
RUN mkdir -p /var/lib/atlas-studio/artifacts && chown -R atlasstudio:atlasstudio /var/lib/atlas-studio
USER atlasstudio
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=5s --retries=5 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health/live')"]
CMD ["uvicorn", "atlas_studio.main:app", "--host", "0.0.0.0", "--port", "8080"]
