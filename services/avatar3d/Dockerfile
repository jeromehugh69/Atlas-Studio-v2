FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git build-essential libgl1 libglib2.0-0 blender && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR.git /opt/TripoSR
WORKDIR /opt/TripoSR
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.2.1 torchvision==0.17.1
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn python-multipart rembg onnxruntime
COPY app.py /opt/avatar-worker/app.py
COPY blender_cleanup.py /opt/avatar-worker/blender_cleanup.py
RUN useradd --system --create-home --home-dir /home/avatar avatar && mkdir -p /data/jobs /models && chown -R avatar:avatar /data /models /home/avatar
USER avatar
ENV PYTHONPATH=/opt/TripoSR
WORKDIR /opt/avatar-worker
EXPOSE 8090
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
