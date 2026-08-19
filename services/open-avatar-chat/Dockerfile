FROM python:3.11-slim

ARG OPEN_AVATAR_CHAT_REF=main
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential ca-certificates curl ffmpeg g++ gcc git git-lfs libgl1 libglib2.0-0 \
      libgomp1 libsndfile1 libsm6 libsox-dev libxext6 sox \
    && rm -rf /var/lib/apt/lists/* \
    && git lfs install

WORKDIR /opt/open-avatar-chat
RUN git clone --branch "${OPEN_AVATAR_CHAT_REF}" --depth 1 \
      --recurse-submodules --shallow-submodules \
      https://github.com/HumanAIGC-Engineering/OpenAvatarChat.git .

RUN pip install --no-cache-dir uv \
    && uv venv --python /usr/local/bin/python --seed

COPY atlas-local.yaml /opt/open-avatar-chat/config/atlas-local.yaml
RUN uv run install.py --config config/atlas-local.yaml \
    && uv pip uninstall onnxruntime-gpu \
    && uv pip install --no-cache-dir onnxruntime~=1.20.1

COPY inject_atlas_widget.py /tmp/inject_atlas_widget.py
RUN python /tmp/inject_atlas_widget.py && rm /tmp/inject_atlas_widget.py

COPY entrypoint.sh /usr/local/bin/atlas-open-avatar-chat
RUN chmod 0555 /usr/local/bin/atlas-open-avatar-chat

EXPOSE 8282
ENTRYPOINT ["/usr/local/bin/atlas-open-avatar-chat"]
