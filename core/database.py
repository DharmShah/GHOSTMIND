import logging
import time
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from core.config import settings

logger = logging.getLogger("ghostmind.database")

# Database engine with connection pooling and health pre-ping
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a transactional database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_db_health() -> dict:
    """Performs a live health check on the database connection and vector support."""
    start_time = time.time()
    result = {
        "connected": False,
        "database": None,
        "pgvector_enabled": False,
        "latency_ms": 0,
        "error": None
    }
    try:
        with engine.connect() as conn:
            db_name = conn.execute(text("SELECT current_database()")).scalar()
            has_vector = conn.execute(text(
                "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
            )).scalar() is not None

            result["connected"] = True
            result["database"] = db_name
            result["pgvector_enabled"] = bool(has_vector)
            result["latency_ms"] = round((time.time() - start_time) * 1000, 2)
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Database health check failed: {e}")
    return result

def init_db():
    """Initializes database extensions and tables safely without wiping data."""
    try:
        with engine.connect() as conn:
            # Attempt to enable pgvector if available
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                conn.commit()
                logger.info("pgvector extension verified.")
            except Exception as e:
                logger.warning(
                    f"pgvector extension not installed in PostgreSQL instance ({e}). "
                    "Vector operations will use fallback mode."
                )

        # Create all registered model tables
        import models # noqa: F401
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        # We do not crash the entire app here so non-DB checks can still report
