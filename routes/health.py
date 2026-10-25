from fastapi import APIRouter
from core.database import check_db_health
import ollama_service

router = APIRouter(prefix="/api/health", tags=["Health & Diagnostics"])

@router.get("")
@router.get("/status")
def health_check():
    """Live diagnostic check of PostgreSQL, pgvector, and local Ollama engine."""
    db_status = check_db_health()
    ollama_status = ollama_service.check_system_readiness()

    overall_ready = db_status.get("connected", False) and ollama_status.get("ready", False)

    return {
        "status": "online" if overall_ready else "degraded",
        "ready": overall_ready,
        "database": db_status,
        "ollama": ollama_status,
        "version": "2.0.0"
    }
