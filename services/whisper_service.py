import os
import logging
from pathlib import Path
from typing import Optional, Tuple
from core.config import settings

logger = logging.getLogger("ghostmind.whisper")

_whisper_model = None
_current_model_size = None

def get_whisper_model(model_size: Optional[str] = None):
    """Lazy-loads and caches the local faster-whisper model."""
    global _whisper_model, _current_model_size
    target_size = model_size or settings.WHISPER_MODEL_SIZE or "base"

    if _whisper_model is not None and _current_model_size == target_size:
        return _whisper_model

    from faster_whisper import WhisperModel

    models_dir = settings.MODELS_DIR / "whisper"
    models_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading local Whisper model '{target_size}' on CPU (int8)...")
    _whisper_model = WhisperModel(
        model_size_or_path=target_size,
        device="cpu",
        compute_type="int8",
        download_root=str(models_dir)
    )
    _current_model_size = target_size
    logger.info(f"Local Whisper model '{target_size}' loaded successfully.")
    return _whisper_model

def transcribe_audio(file_path: Path, language: Optional[str] = None) -> Tuple[str, Optional[str]]:
    """
    Transcribes a local audio file (webm, wav, mp3, ogg, etc.) using faster-whisper.
    Returns (transcription_text, detected_language).
    """
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise ValueError("Audio recording file is empty or missing.")

    model = get_whisper_model()

    segments, info = model.transcribe(
        str(file_path),
        beam_size=5,
        language=language if language and language != "auto" else None
    )

    text_parts = []
    for segment in segments:
        text_parts.append(segment.text.strip())

    transcription = " ".join(text_parts).strip()
    detected_lang = info.language if info else None
    return transcription, detected_lang
