import uuid
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select
from fastapi import Depends

from core.database import get_db
from models import User

logger = logging.getLogger("ghostmind.user")

LOCAL_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
LOCAL_USER_EMAIL = "local@ghostmind.ai"
LOCAL_USER_NAME = "GHOSTMIND User"

def get_local_user(db: Session = Depends(get_db)) -> User:
    """
    Provides the local GHOSTMIND user in a zero-auth, single-user desktop architecture.
    Preserves existing PostgreSQL conversations, memories, and documents by reusing
    any existing user record, or automatically provisioning the default local user.
    """
    # 1. Look for existing user record in database
    user = db.scalar(select(User).order_by(User.created_at))
    if user:
        return user

    # 2. If database is completely fresh, provision the default local user
    try:
        user = User(
            id=LOCAL_USER_ID,
            google_sub="local_ghostmind_desktop_user",
            email=LOCAL_USER_EMAIL,
            display_name=LOCAL_USER_NAME
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Provisioned default local user: {user.id}")
        return user
    except Exception:
        db.rollback()
        # Fallback query if concurrent insert occurred
        user = db.scalar(select(User).order_by(User.created_at))
        if user:
            return user
        raise

