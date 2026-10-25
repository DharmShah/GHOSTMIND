import hashlib
import secrets
from typing import Optional, Dict, Any
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from core.config import settings

def generate_session_token() -> str:
    """Generates a cryptographically strong random token for sessions."""
    return secrets.token_urlsafe(32)

def hash_token(raw_token: str) -> str:
    """Hashes a session token using SHA-256 for secure storage at rest."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

def generate_csrf_token() -> str:
    """Generates a secure CSRF token."""
    return secrets.token_hex(16)

def verify_google_id_token(token_str: str) -> Optional[Dict[str, Any]]:
    """
    Validates a Google ID token server-side:
    - Signature validation against Google's public keys
    - Audience check against GOOGLE_CLIENT_ID
    - Issuer check (accounts.google.com)
    - Expiration check
    """
    if not token_str:
        return None
    
    # Handle development bypass/mock if credentials are explicitly unset and token is a dev token
    if not settings.GOOGLE_CLIENT_ID and token_str.startswith("dev_mock_"):
        return {
            "sub": "dev_google_sub_123456789",
            "email": "developer@ghostmind.local",
            "name": "Local Developer",
            "picture": "https://api.dicebear.com/7.x/bottts/svg?seed=GhostMind"
        }

    try:
        request = google_requests.Request()
        id_info = id_token.verify_oauth2_token(
            token_str,
            request,
            audience=settings.GOOGLE_CLIENT_ID if settings.GOOGLE_CLIENT_ID else None
        )

        # Enforce valid issuer
        if id_info.get("iss") not in ["accounts.google.com", "https://accounts.google.com"]:
            return None

        # Return verified identity dictionary
        return {
            "sub": str(id_info.get("sub")),
            "email": str(id_info.get("email")),
            "name": str(id_info.get("name", "GHOSTMIND User")),
            "picture": id_info.get("picture")
        }
    except Exception as e:
        # Never log raw tokens
        return None
