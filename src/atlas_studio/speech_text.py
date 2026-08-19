"""Convert technical Atlas responses into safe, natural speech text."""

from __future__ import annotations

import re
import unicodedata


_FENCED_CODE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)]\([^\s)]+(?:\s+\"[^\"]*\")?\)")
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE)
_PATH = re.compile(r"(?<!\w)(?:[A-Za-z]:\\|/)(?:[^\s,;:]+[/\\])*[^\s,;:]+")
_TECHNICAL_LINE = re.compile(
    r"^\s*(?:"
    r"traceback\b|caused by\s*:|during handling of the above exception|"
    r"file\s+[\"'].*[\"']\s*,\s*line\s+\d+|at\s+\S+\s*\(|"
    r"(?:[\w.]+(?:error|exception))\s*:|(?:error|exception|fatal|failed)\s*:|"
    r"local model unavailable\s*:|local task failed\b|"
    r"http/\d(?:\.\d)?\s+\d{3}|(?:http|status)\s+\d{3}\b|"
    r"ps\s+[A-Za-z]:\\|docker(?:\.exe)?\s+|npm\s+err!|exit\s+code\s+\d+|"
    r"errno\s*\d+|connection(?:refused|error)\b"
    r")",
    re.IGNORECASE,
)
_TECHNICAL_FRAGMENT = re.compile(
    r"(?:\b(?:http(?:\s+status)?\s*[45]\d{2}|errno\s*\d+|exit\s+code\s+\d+|"
    r"connection\s+refused|stack\s+trace|ollama\s+timed\s+out)\b|"
    r"\b[\w.]+(?:error|exception)\s*:)",
    re.IGNORECASE,
)


def _remove_unicode_symbols(text: str) -> str:
    kept: list[str] = []
    for character in text:
        category = unicodedata.category(character)
        if category.startswith("S") or category in {"Cc", "Cf", "Cs", "Co"}:
            kept.append(" ")
        else:
            kept.append(character)
    return "".join(kept)


def prepare_speech_text(value: str, max_characters: int = 4_000) -> str:
    """Return natural prose and omit code, traces, identifiers, and UI symbols.

    The original response remains available to the visual transcript. This
    function only controls the text sent to a local speech engine.
    """
    text = unicodedata.normalize("NFKC", value or "").replace("\r\n", "\n")
    text = _FENCED_CODE.sub(" ", text)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _INLINE_CODE.sub(" ", text)
    text = _URL.sub(" ", text)
    text = _EMAIL.sub(" ", text)
    text = _UUID.sub(" ", text)
    text = _PATH.sub(" ", text)

    natural_lines: list[str] = []
    for line in text.splitlines():
        line = re.sub(r"^\s{0,3}(?:#{1,6}|>|[-*+]\s+|\d+[.)]\s+)", "", line).strip()
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            if not sentence or _TECHNICAL_LINE.match(sentence) or _TECHNICAL_FRAGMENT.search(sentence):
                continue
            if re.search(r"(?:\{.*:.*}|\w+\([^)]*\)\s*(?:\{|=>)|[=<>]{2,}|::)", sentence):
                continue
            natural_lines.append(sentence)

    text = " ".join(natural_lines)
    text = re.sub(r"(?:-{2,}|={2,}|_{2,}|\*{2,}|~{2,})", " ", text)
    text = re.sub(r"\s*(?:→|➜|➡|->|=>)\s*", " then ", text)
    text = text.replace("&", " and ").replace("%", " percent ")
    text = re.sub(r"[_|\\/^#@+$*=<>\[\]{}]", " ", text)
    text = _remove_unicode_symbols(text)
    text = re.sub(r"\.{2,}|!{2,}|\?{2,}", ".", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?=[A-Za-z])", r"\1 ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;:-")
    if text and text[-1] not in ".!?":
        text += "."
    if len(text) > max_characters:
        truncated = text[:max_characters]
        if " " in truncated:
            truncated = truncated.rsplit(" ", 1)[0]
        text = truncated.rstrip(" ,;:-.!") + "."
    return text
