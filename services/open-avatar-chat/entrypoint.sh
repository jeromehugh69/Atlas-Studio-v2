#!/bin/sh
set -eu

mkdir -p /opt/open-avatar-chat/models /opt/open-avatar-chat/.atlas

LITE_ROOT=/opt/open-avatar-chat/src/handlers/avatar/liteavatar/algo/liteavatar
PARAFORMER_ROOT="$LITE_ROOT/weights/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
if [ ! -s "$LITE_ROOT/weights/model_1.onnx" ] || \
   [ ! -s "$PARAFORMER_ROOT/model.pb" ] || \
   [ ! -s "$PARAFORMER_ROOT/lm/lm.pb" ]; then
  echo "Downloading and arranging the official LiteAvatar CPU weights..."
  mkdir -p "$PARAFORMER_ROOT/lm" "$LITE_ROOT/lite_avatar_weights"
  uv run --no-sync modelscope download --model HumanAIGC-Engineering/LiteAvatarGallery \
    lite_avatar_weights/lm.pb lite_avatar_weights/model_1.onnx \
    lite_avatar_weights/model.pb --local_dir "$LITE_ROOT"
  mv -f "$LITE_ROOT/lite_avatar_weights/lm.pb" "$PARAFORMER_ROOT/lm/lm.pb"
  mv -f "$LITE_ROOT/lite_avatar_weights/model.pb" "$PARAFORMER_ROOT/model.pb"
  mv -f "$LITE_ROOT/lite_avatar_weights/model_1.onnx" "$LITE_ROOT/weights/model_1.onnx"
  rmdir "$LITE_ROOT/lite_avatar_weights" 2>/dev/null || true
fi

exec uv run --no-sync src/demo.py --config config/atlas-local.yaml
