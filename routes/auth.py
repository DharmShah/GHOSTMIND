import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from core.security import verify_google_id_token
from models import User
from schemas.auth import GoogleAuthRequest, UserProfileSchema, SessionResponse
from services import auth_service

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

def get_session_token_from_request(request: Request) -> str | None:
    """Extracts session token from HttpOnly cookie or Authorization Bearer header."""
    cookie_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None

def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User:
    """FastAPI dependency: enforces valid authenticated user."""
    token = get_session_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in with Google."
        )
    user = auth_service.authenticate_session(db, token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please sign in again."
        )
    return user

def get_optional_user(
    request: Request,
    db: Session = Depends(get_db)
) -> User | None:
    """FastAPI dependency: retrieves user if authenticated, otherwise returns None."""
    token = get_session_token_from_request(request)
    if not token:
        return None
    return auth_service.authenticate_session(db, token)


@router.get("/config")
def get_auth_config():
    """Returns public Google OAuth client configuration for the frontend."""
    return {
        "google_client_id": settings.GOOGLE_CLIENT_ID or "",
        "google_configured": bool(settings.GOOGLE_CLIENT_ID),
        "redirect_uri": settings.GOOGLE_REDIRECT_URI
    }


@router.get("/google/url")
def get_google_auth_url():
    """Builds the official Google OAuth 2.0 authorization URL."""
    if not settings.GOOGLE_CLIENT_ID:
        return {
            "configured": False,
            "message": "Google Client ID is not configured in .env. Configure GOOGLE_CLIENT_ID to enable live OAuth."
        }

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account consent",
    }
    url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {
        "configured": True,
        "url": url
    }


@router.post("/google/callback", response_model=SessionResponse)
def google_callback(
    payload: GoogleAuthRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Validates Google identity, auto-creates or updates account in PostgreSQL,
    and issues an HttpOnly SameSite cookie session.
    """
    id_data = None
    if payload.credential:
        id_data = verify_google_id_token(payload.credential)

    if not id_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or unverified Google identity credentials."
        )

    # Auto-provision or update user
    user = auth_service.get_or_create_user(
        db=db,
        google_sub=id_data["sub"],
        email=id_data["email"],
        display_name=id_data.get("name", "GHOSTMIND User"),
        avatar_url=id_data.get("picture")
    )

    # Create session record
    raw_session_token = auth_service.create_session(db, user.id)

    # Set secure HttpOnly cookie
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=raw_session_token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,  # False for local desktop loopback, True in HTTPS production
        path="/"
    )

    return SessionResponse(
        authenticated=True,
        user=UserProfileSchema.from_orm(user),
        message="Successfully authenticated with Google."
    )


@router.get("/me", response_model=SessionResponse)
def get_current_profile(
    user: User | None = Depends(get_optional_user)
):
    """Checks the active session and returns user profile if logged in."""
    if not user:
        return SessionResponse(authenticated=False, user=None)
    return SessionResponse(authenticated=True, user=UserProfileSchema.from_orm(user))


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """Revokes session and clears the session cookie."""
    token = get_session_token_from_request(request)
    if token:
        auth_service.revoke_session(db, token)

    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/"
    )
    return {"message": "Logged out successfully."}
