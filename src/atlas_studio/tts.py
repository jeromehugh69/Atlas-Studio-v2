"""ChatterboxTTS wrapper — CPU-only TTS with lazy model loading."""
import io
import logging
import threading
from typing import Optional

import numpy as np
import soundfile as sf

logger = logging.getLogger("atlas_studio.tts")

_model = None
_model_lock = threading.Lock()


def _load_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from chatterbox import ChatterboxTTS
            logger.info("Loading ChatterboxTTS model on CPU...")
            _model = ChatterboxTTS.from_pretrained(device="cpu")
            logger.info("ChatterboxTTS model loaded")
        except Exception:
            logger.exception("Failed to load ChatterboxTTS")
            raise
    return _model


def synthesize_speech(text: str, exaggeration: float = 0.5, cfg_weight: float = 0.5) -> bytes:
    """Synthesize text to WAV bytes using ChatterboxTTS."""
    model = _load_model()
    wav = model.generate(text, exaggeration=exaggeration, cfg_weight=cfg_weight)
    audio_np = wav.squeeze(0).cpu().numpy()
    buf = io.BytesIO()
    sf.write(buf, audio_np, 22050, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def preload_model():
    """Pre-load model in background thread at startup."""
    t = threading.Thread(target=_load_model, daemon=True)
    t.start()
