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
from core.config import settings
from core.database import init_db, check_db_health, get_db
from core.user import get_local_user
from routes.conversations import router as conversations_router
from routes.chat import router as chat_router
from routes.documents import router as documents_router
from routes.memories import router as memories_router
from routes.voice import router as voice_router
from routes.health import router as health_router
from routes.integrations import router as integrations_router
from routes.oauth import router as oauth_router
from routes.mcp import router as mcp_router
from routes.pending_actions import router as pending_actions_router
from services import chat_service, web_search_service
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

    # Ensure Ollama service is running when backend starts
    try:
        ollama_running, msg = ollama_service.ensure_ollama_running(max_wait_seconds=20.0)
        logger.info(f"Ollama startup check: {msg}")
    except Exception as e:
        logger.warning(f"Ollama startup check notice: {e}")

    yield
    logger.info("Disconnecting active MCP connections...")
    try:
        from mcp.connection_manager import connection_manager
        await connection_manager.disconnect_all()
    except Exception as e:
        logger.warning(f"MCP shutdown notice: {e}")
    logger.info("GHOSTMIND server shutting down.")

app = FastAPI(
    title="GHOSTMIND - Autonomous AI Operating System",
    description="Local-first AI platform with PostgreSQL memory, RAG, voice, and live web search.",
    version="2.1.0",
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

# Mount API Routers (Zero-Auth, Single-User Architecture)
app.include_router(conversations_router)
app.include_router(chat_router)
app.include_router(documents_router)
app.include_router(memories_router)
app.include_router(voice_router)
app.include_router(health_router)
app.include_router(integrations_router)
app.include_router(oauth_router)
app.include_router(mcp_router)
app.include_router(pending_actions_router)

# Google OAuth loopback compatibility redirect
@app.get("/auth/google/callback")
async def google_oauth_redirect_compat(request: Request):
    from fastapi.responses import RedirectResponse
    query_str = str(request.url.query)
    target = f"/api/oauth/callback?{query_str}" if query_str else "/api/oauth/callback"
    return RedirectResponse(url=target)

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
    """Diagnostic endpoint checking Ollama, PostgreSQL, and internet readiness."""
    ollama_ready = ollama_service.check_system_readiness()
    db_health = check_db_health()
    internet_online = web_search_service.is_internet_available()
    return {
        **ollama_ready,
        "database": db_health,
        "internet_connected": internet_online
    }

@app.get("/api/settings")
def get_platform_settings():
    """Returns current active platform generation parameters."""
    return {
        "model": settings.OLLAMA_MODEL,
        "temperature": settings.DEFAULT_TEMPERATURE,
        "max_output_tokens": settings.MAX_OUTPUT_TOKENS,
        "context_window": settings.OLLAMA_NUM_CTX,
        "max_recent_messages": settings.MAX_RECENT_MESSAGES,
        "web_search_enabled": settings.WEB_SEARCH_ENABLED,
        "rag_similarity_threshold": settings.RAG_SIMILARITY_THRESHOLD,
        "whisper_model_size": settings.WHISPER_MODEL_SIZE
    }

@app.post("/api/ollama/start")
def start_ollama():
    """Endpoint to explicitly trigger Ollama startup if requested by frontend."""
    running, msg = ollama_service.ensure_ollama_running(max_wait_seconds=25.0)
    return {"running": running, "message": msg}

class LegacyChatRequest(BaseModel):
    message: str

@app.post("/chat")
def legacy_chat(
    request: LegacyChatRequest,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Backwards-compatible chat endpoint executing full RAG, Web Search, and memory pipeline."""
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
