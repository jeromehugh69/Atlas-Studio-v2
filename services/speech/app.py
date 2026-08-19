"""Local Whisper STT with Kokoro, Piper, and espeak-ng TTS for Atlas Studio."""

from __future__ import annotations

import os
import logging
import re
import subprocess
import sys
import tempfile
import unicodedata
import wave
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from faster_whisper import WhisperModel
from kokoro import KPipeline
from piper import PiperVoice
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask


WHISPER_MODEL = os.getenv("ATLAS_SPEECH_WHISPER_MODEL", "base.en")
KOKORO_VOICE = os.getenv("ATLAS_SPEECH_KOKORO_VOICE", "af_bella")
KOKORO_SPEED = float(os.getenv("ATLAS_SPEECH_KOKORO_SPEED", "0.94"))
PIPER_VOICE = os.getenv("ATLAS_SPEECH_PIPER_VOICE", "en_US-kristin-medium")
PIPER_DIR = Path(os.getenv("ATLAS_SPEECH_PIPER_DIR", "/models/piper"))
TTS_PRIMARY = os.getenv("ATLAS_SPEECH_TTS_PRIMARY", "kokoro").strip().lower()
if TTS_PRIMARY not in {"kokoro", "piper"}:
    TTS_PRIMARY = "piper"
OUTPUT = Path("/tmp/atlas-speech")
OUTPUT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Atlas Local Speech", version="0.1.0")
whisper: WhisperModel | None = None
kokoro: KPipeline | None = None
kokoro_failed = False
piper: PiperVoice | None = None
piper_failed = False
logger = logging.getLogger("atlas-speech")


class SpeechRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)


def clean_for_speech(value: str) -> str:
    """Last-line defense against vocalizing code, errors, or interface glyphs."""
    text = unicodedata.normalize("NFKC", value or "")
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`\n]+`", " ", text)
    text = re.sub(r"\b(?:https?://|www\.)\S+", " ", text, flags=re.IGNORECASE)
    fragments = [fragment.strip() for line in text.splitlines() for fragment in re.split(r"(?<=[.!?])\s+", line)]
    text = " ".join(
        fragment
        for fragment in fragments
        if fragment
        and not re.match(
            r"^(?:traceback|caused by:|file [\"']|(?:[\w.]+(?:error|exception)):|(?:error|fatal|failed):|local model unavailable:|http/\d|ps [a-z]:\\|docker |exit code|errno)",
            fragment,
            flags=re.IGNORECASE,
        )
        and not re.search(r"\b(?:http(?:\s+status)?\s*[45]\d{2}|errno\s*\d+|exit\s+code\s+\d+|connection\s+refused|stack\s+trace|ollama\s+timed\s+out)\b", fragment, flags=re.IGNORECASE)
    )
    text = re.sub(r"\s*(?:→|➜|➡|->|=>)\s*", " then ", text)
    text = text.replace("&", " and ").replace("%", " percent ")
    text = re.sub(r"[_|\\/^#@+$*=<>\[\]{}]", " ", text)
    text = "".join(" " if unicodedata.category(char).startswith("S") else char for char in text)
    return re.sub(r"\s+", " ", text).strip(" ,;:-")


def get_whisper() -> WhisperModel:
    global whisper
    if whisper is None:
        whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    return whisper


def get_kokoro() -> KPipeline:
    global kokoro
    if kokoro is None:
        kokoro = KPipeline(lang_code="a")
    return kokoro


def get_piper() -> PiperVoice:
    global piper
    if piper is not None:
        return piper
    PIPER_DIR.mkdir(parents=True, exist_ok=True)
    model_path = PIPER_DIR / f"{PIPER_VOICE}.onnx"
    config_path = PIPER_DIR / f"{PIPER_VOICE}.onnx.json"
    if not model_path.is_file() or not config_path.is_file():
        logger.info("Downloading the local Piper voice %s", PIPER_VOICE)
        subprocess.run(
            [sys.executable, "-m", "piper.download_voices", PIPER_VOICE, "--data-dir", str(PIPER_DIR)],
            check=True,
            timeout=900,
        )
    piper = PiperVoice.load(str(model_path))
    return piper


@app.get("/health")
def health():
    return {
        "status": "ok",
        "stt": WHISPER_MODEL,
        "tts": f"piper:{PIPER_VOICE}" if TTS_PRIMARY == "piper" else f"kokoro:{KOKORO_VOICE}",
        "tts_primary": f"piper:{PIPER_VOICE}" if TTS_PRIMARY == "piper" else f"kokoro:{KOKORO_VOICE}",
        "tts_secondary": f"kokoro:{KOKORO_VOICE}" if TTS_PRIMARY == "piper" else f"piper:{PIPER_VOICE}",
        "tts_fallback": "espeak-ng:en-us+f3",
        "tts_speed": KOKORO_SPEED,
        "accent": "American English",
    }


@app.post("/stt")
async def transcribe(audio: UploadFile = File(...)):
    suffix = Path(audio.filename or "speech.wav").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as incoming:
        incoming.write(await audio.read())
        source = Path(incoming.name)
    try:
        segments, info = get_whisper().transcribe(str(source), vad_filter=True, beam_size=1)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return {"text": text, "language": info.language}
    finally:
        source.unlink(missing_ok=True)


@app.post("/tts")
def synthesize(body: SpeechRequest):
    global kokoro_failed, piper_failed
    speech_text = clean_for_speech(body.text)
    if not speech_text:
        raise HTTPException(422, "No natural-language content is available to speak")
    with tempfile.NamedTemporaryFile(dir=OUTPUT, suffix=".wav", delete=False) as target:
        path = Path(target.name)
    backend = ""
    generated = False
    engine_order = ("piper", "kokoro") if TTS_PRIMARY == "piper" else ("kokoro", "piper")
    for engine in engine_order:
        if engine == "kokoro" and not kokoro_failed:
            try:
                chunks = [
                    np.asarray(audio, dtype=np.float32)
                    for _, _, audio in get_kokoro()(speech_text, voice=KOKORO_VOICE, speed=KOKORO_SPEED)
                ]
                if not chunks:
                    raise RuntimeError("Kokoro returned no audio")
                sf.write(path, np.concatenate(chunks), 24000)
                backend = f"kokoro:{KOKORO_VOICE}"
                generated = True
            except Exception:
                kokoro_failed = True
                logger.exception("Kokoro synthesis failed; trying the next local voice engine")
        elif engine == "piper" and not piper_failed:
            try:
                with wave.open(str(path), "wb") as wav_file:
                    get_piper().synthesize_wav(speech_text, wav_file)
                backend = f"piper:{PIPER_VOICE}"
                generated = True
            except Exception:
                piper_failed = True
                logger.exception("Piper synthesis failed; trying the next local voice engine")
        if generated:
            break

    if not generated:
        backend = "espeak-ng"
        try:
            subprocess.run(
                ["espeak-ng", "-v", "en-us+f3", "-s", "158", "-w", str(path), speech_text],
                check=True,
                timeout=60,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(500, "All local speech engines failed") from exc
    return FileResponse(
        path,
        media_type="audio/wav",
        filename="atlas-response.wav",
        headers={"X-Atlas-Voice-Backend": backend},
        background=BackgroundTask(path.unlink, missing_ok=True),
    )
