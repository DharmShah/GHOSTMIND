import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

class Settings:
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/ghostmind"
    )

    # Google OAuth 2.0
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI: str = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://127.0.0.1:8000/auth/google/callback"
    )

    # Session Security
    SESSION_SECRET: str = os.getenv(
        "SESSION_SECRET",
        "ghostmind-super-secure-session-secret-change-in-prod-xyz789"
    )
    SESSION_COOKIE_NAME: str = "ghostmind_session"
    SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 24 * 7  # 7 days

    # Ollama
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

    # Whisper
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")

    # Storage
    _app_data_dir = os.getenv("APP_DATA_DIR")
    if _app_data_dir:
        APP_DATA_DIR: Path = Path(_app_data_dir)
    else:
        APP_DATA_DIR: Path = Path(os.path.expanduser("~")) / ".ghostmind"
    
    UPLOADS_DIR: Path = APP_DATA_DIR / "uploads"
    MODELS_DIR: Path = APP_DATA_DIR / "models"
    MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "25"))
    ALLOWED_EXTENSIONS: set[str] = {
        "pdf", "txt", "md", "docx", "csv", "json", "xlsx"
    }

    # Context Bounds
    MAX_RECENT_MESSAGES: int = 10
    MAX_RAG_CHUNKS: int = 5
    MAX_MEMORIES: int = 5

    def ensure_directories(self):
        self.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.ensure_directories()
