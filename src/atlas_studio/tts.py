"""ChatterboxTTS wrapper — CPU-only TTS with lazy model loading."""
import io
import logging
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

logger = logging.getLogger("atlas_studio.tts")

_model = None
_model_lock = threading.Lock()

# Bundled CC0 female reference voice (LJSpeech speaker, ~20s) shipped with the repo.
_BUNDLED_VOICE_CANDIDATES = [
    Path("models/voice/atlas-female-ref.wav"),
    Path(__file__).resolve().parents[2] / "models" / "voice" / "atlas-female-ref.wav",
]


def resolve_audio_prompt(explicit: str = "") -> Optional[str]:
    """Resolve the voice-cloning reference clip.

    Priority: "none"/"default" disables cloning; explicitly configured path next;
    otherwise the bundled female reference is used when present.
    """
    normalized = (explicit or "").strip().lower()
    if normalized in {"none", "default", "off"}:
        return None
    if explicit.strip():
        path = Path(explicit).expanduser()
        if path.is_file():
            return str(path)
        logger.warning("Configured TTS audio prompt not found: %s; falling back", explicit)
    for candidate in _BUNDLED_VOICE_CANDIDATES:
        if candidate.is_file():
            return str(candidate)
    logger.warning("No female reference voice found; ChatterboxTTS will use its default voice")
    return None


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


def synthesize_speech(
    text: str,
    exaggeration: float = 0.5,
    cfg_weight: float = 0.5,
    audio_prompt_path: Optional[str] = None,
) -> bytes:
    """Synthesize text to WAV bytes using ChatterboxTTS.

    When `audio_prompt_path` points to a reference clip, the output adopts that
    speaker's voice (used to give Atlas a consistent female persona).
    """
    model = _load_model()
    wav = model.generate(
        text,
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
        audio_prompt_path=audio_prompt_path,
    )
    audio_np = wav.squeeze(0).cpu().numpy()
    buf = io.BytesIO()
    sf.write(buf, audio_np, 22050, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def preload_model():
    """Pre-load model in background thread at startup."""
    t = threading.Thread(target=_load_model, daemon=True)
    t.start()
