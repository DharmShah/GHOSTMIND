import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select

from models import User, UserPreference, SessionRecord
from core.security import generate_session_token, hash_token
from core.config import settings

def get_or_create_user(
    db: Session,
    google_sub: str,
    email: str,
    display_name: str,
    avatar_url: Optional[str] = None
) -> User:
    """Finds user by Google subject ID or email, or registers a new user with default preferences."""
    clean_email = email.strip().lower() if email else ""
    now = datetime.now(timezone.utc)

    # 1. Look up by verified Google subject ID
    user = db.scalar(select(User).where(User.google_sub == google_sub))

    # 2. Fallback: look up by verified email to link account and prevent duplicate key violations
    if not user and clean_email:
        user = db.scalar(select(User).where(User.email == clean_email))

    if user:
        # Link verified Google subject ID and update profile
        user.google_sub = google_sub
        if clean_email:
            user.email = clean_email
        if display_name:
            user.display_name = display_name
        if avatar_url:
            user.avatar_url = avatar_url
        user.last_login_at = now
        db.commit()
        db.refresh(user)
        return user

    # Create new user
    new_user = User(
        id=uuid.uuid4(),
        google_sub=google_sub,
        email=email,
        display_name=display_name,
        avatar_url=avatar_url,
        created_at=now,
        last_login_at=now
    )
    db.add(new_user)
    db.flush()

    # Create default preferences
    pref = UserPreference(
        id=uuid.uuid4(),
        user_id=new_user.id,
        theme="pastel",
        selected_model=settings.OLLAMA_MODEL,
        voice_model_size=settings.WHISPER_MODEL_SIZE,
        language="en",
        memory_enabled=True,
        created_at=now,
        updated_at=now
    )
    db.add(pref)
    db.commit()
    db.refresh(new_user)
    return new_user

def create_session(db: Session, user_id: uuid.UUID) -> str:
    """Creates a new session record and returns the raw session token for the cookie."""
    raw_token = generate_session_token()
    hashed = hash_token(raw_token)
    expires = datetime.now(timezone.utc) + timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS)

    record = SessionRecord(
        id=uuid.uuid4(),
        user_id=user_id,
        session_token=hashed,
        expires_at=expires,
        is_revoked=False
    )
    db.add(record)
    db.commit()
    return raw_token

def authenticate_session(db: Session, raw_token: Optional[str]) -> Optional[User]:
    """Validates session token and returns active User or None."""
    if not raw_token:
        return None

    hashed = hash_token(raw_token)
    now = datetime.now(timezone.utc)

    session_record = db.scalar(
        select(SessionRecord)
        .where(
            SessionRecord.session_token == hashed,
            SessionRecord.expires_at > now,
            SessionRecord.is_revoked == False
        )
    )

    if not session_record:
        return None

    user = db.scalar(select(User).where(User.id == session_record.user_id))
    return user

def revoke_session(db: Session, raw_token: Optional[str]) -> bool:
    """Revokes active session record."""
    if not raw_token:
        return False
    hashed = hash_token(raw_token)
    session_record = db.scalar(
        select(SessionRecord).where(SessionRecord.session_token == hashed)
    )
    if session_record:
        session_record.is_revoked = True
        db.commit()
        return True
    return False
