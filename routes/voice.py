import uuid
import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from models import User
from routes.auth import get_current_user
from services import whisper_service

router = APIRouter(prefix="/api/voice", tags=["Voice Assistant"])

@router.get("/status")
def get_voice_status(
    current_user: User = Depends(get_current_user)
):
    """Returns local Whisper speech-to-text engine configuration."""
    return {
        "engine": "faster-whisper",
        "model_size": settings.WHISPER_MODEL_SIZE,
        "device": "cpu",
        "compute_type": "int8",
        "local_only": True
    }

@router.post("/transcribe")
async def transcribe_voice(
    audio: UploadFile = File(...),
    language: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user)
):
    """
    Receives recorded microphone audio from the desktop frontend,
    runs local Whisper transcription, and returns the recognized text.
    """
    temp_dir = settings.APP_DATA_DIR / "temp_audio"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_filename = f"{uuid.uuid4()}_{audio.filename or 'voice.webm'}"
    temp_path = temp_dir / temp_filename

    try:
        content = await audio.read()
        if not content:
            raise HTTPException(status_code=400, detail="Recorded audio was empty.")

        with open(temp_path, "wb") as f:
            f.write(content)

        text, detected_lang = whisper_service.transcribe_audio(temp_path, language=language)

        return {
            "success": True,
            "text": text,
            "detected_language": detected_lang,
            "message": "Transcription successful."
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice transcription failed: {e}")
    finally:
        if temp_path.exists():
            try:
                os.remove(temp_path)
            except Exception:
                pass
