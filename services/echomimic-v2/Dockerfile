FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 FFMPEG_PATH=/usr/bin
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip python3.10-dev git git-lfs ffmpeg build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /opt
RUN git clone --depth 1 https://github.com/antgroup/echomimic_v2.git echomimic_v2
WORKDIR /opt/echomimic_v2
RUN python3.10 -m pip install --no-cache-dir --upgrade pip \
    && python3.10 -m pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124 \
    && python3.10 -m pip install --no-cache-dir -r requirements.txt \
    && python3.10 -m pip install --no-cache-dir --no-deps facenet_pytorch==2.6.0 \
    && sed -i 's/demo.launch(inbrowser=True)/demo.launch(server_name="0.0.0.0", server_port=7860)/' app.py
EXPOSE 7860
CMD ["python3.10", "app.py"]
