FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/models/huggingface
WORKDIR /service
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng libsndfile1 \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir fastapi uvicorn[standard] python-multipart \
    faster-whisper kokoro piper-tts==1.4.2 soundfile numpy
COPY app.py ./app.py
RUN useradd --system --create-home --uid 10001 speech && mkdir -p /models /tmp/atlas-speech \
    && chown -R speech:speech /models /tmp/atlas-speech
USER speech
EXPOSE 8091
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8091"]
