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

    # Local Ollama AI Engine (Qwen 2.5 3B)
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

    # Model & Token Generation Parameters (CPU-Optimized)
    DEFAULT_TEMPERATURE: float = float(os.getenv("DEFAULT_TEMPERATURE", "0.7"))
    MAX_OUTPUT_TOKENS: int = int(os.getenv("MAX_OUTPUT_TOKENS", "1024"))
    OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
    OLLAMA_TOP_K: int = int(os.getenv("OLLAMA_TOP_K", "40"))
    OLLAMA_TOP_P: float = float(os.getenv("OLLAMA_TOP_P", "0.9"))
    OLLAMA_TIMEOUT_SECONDS: float = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60.0"))

    # Context & Token Bounds (Intelligent Token Optimization)
    MAX_RECENT_MESSAGES: int = int(os.getenv("MAX_RECENT_MESSAGES", "6"))
    MAX_RAG_CHUNKS: int = int(os.getenv("MAX_RAG_CHUNKS", "3"))
    MAX_MEMORIES: int = int(os.getenv("MAX_MEMORIES", "3"))
    RAG_SIMILARITY_THRESHOLD: float = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.45"))

    # Live Web Search
    WEB_SEARCH_ENABLED: bool = os.getenv("WEB_SEARCH_ENABLED", "true").lower() in ("true", "1", "yes")
    WEB_SEARCH_MAX_RESULTS: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "3"))

    # Local Whisper Speech Recognition (CPU int8)
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")

    # Local Storage
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

    def ensure_directories(self):
        self.APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()
settings.ensure_directories()
