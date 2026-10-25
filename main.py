import os
import sys
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

import ollama_service
from core.database import init_db, check_db_health, get_db
from routes.auth import router as auth_router, get_optional_user
from routes.conversations import router as conversations_router
from routes.chat import router as chat_router
from routes.documents import router as documents_router
from routes.memories import router as memories_router
from routes.voice import router as voice_router
from routes.health import router as health_router
from services import chat_service, auth_service
from models import User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ghostmind")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables and extensions on startup
    logger.info("Initializing GHOSTMIND database schema...")
    try:
        init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.warning(f"Database initialization notice: {e}")
    yield
    logger.info("GHOSTMIND server shutting down.")

app = FastAPI(
    title="GHOSTMIND - Autonomous AI Operating System",
    description="Local-first AI platform with PostgreSQL memory, RAG, voice, and Google authentication.",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for local desktop webview and browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_resource_path(relative_path: str) -> str:
    """Robust multi-tier resource path finder for frozen and source execution."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        p = os.path.join(exe_dir, relative_path)
        if os.path.exists(p):
            return p
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            p = os.path.join(meipass, relative_path)
            if os.path.exists(p):
                return p

    script_dir = os.path.dirname(os.path.abspath(__file__))
    p = os.path.join(script_dir, relative_path)
    if os.path.exists(p):
        return p
    return os.path.abspath(relative_path)

def make_no_cache_response(filepath: str, media_type: str = None) -> FileResponse:
    resp = FileResponse(filepath, media_type=media_type)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# Mount API Routers
app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(memories_router)
app.include_router(voice_router)
app.include_router(health_router)

# Static and Webview Endpoints
@app.get("/")
def home():
    html_path = get_resource_path("index.html")
    if os.path.exists(html_path):
        return make_no_cache_response(html_path, media_type="text/html; charset=utf-8")
    raise HTTPException(status_code=404, detail="index.html not found")

@app.get("/app_icon.png")
def get_app_icon_png():
    img_path = get_resource_path("app_icon.png")
    if os.path.exists(img_path):
        return make_no_cache_response(img_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Icon not found")

@app.get("/app_icon.ico")
def get_app_icon_ico():
    ico_path = get_resource_path("app_icon.ico")
    if os.path.exists(ico_path):
        return make_no_cache_response(ico_path, media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Icon not found")

@app.get("/style.css")
def get_style_css():
    css_path = get_resource_path("style.css")
    if os.path.exists(css_path):
        return make_no_cache_response(css_path, media_type="text/css; charset=utf-8")
    raise HTTPException(status_code=404, detail="CSS not found")

@app.get("/status")
@app.get("/api/status")
def status():
    """Diagnostic endpoint checking Ollama and PostgreSQL readiness."""
    ollama_ready = ollama_service.check_system_readiness()
    db_health = check_db_health()
    return {
        **ollama_ready,
        "database": db_health
    }

class LegacyChatRequest(BaseModel):
    message: str

@app.post("/chat")
def legacy_chat(
    request: LegacyChatRequest,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db)
):
    """Backwards-compatible chat endpoint executing full RAG and memory pipeline."""
    if not current_user:
        current_user = auth_service.get_or_create_user(
            db=db,
            google_sub="local_legacy_user_sub",
            email="local@ghostmind.local",
            display_name="GHOSTMIND User"
        )
    result = chat_service.execute_chat_turn(
        db=db,
        user=current_user,
        message=request.message
    )
    return {
        "response": result["response"],
        "conversation_id": result["conversation_id"],
        "sources": result["sources"]
    }
