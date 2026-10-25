import urllib.parse
import hashlib
import httpx
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from core.security import verify_google_id_token
from models import User, Conversation, Message
from sqlalchemy import select
from schemas.auth import GoogleAuthRequest, UserProfileSchema, SessionResponse
from services import auth_service

logger = logging.getLogger("ghostmind.auth")
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
    is_configured = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_ID.strip())
    return {
        "google_client_id": settings.GOOGLE_CLIENT_ID or "",
        "google_configured": is_configured,
        "google_auth_configured": is_configured,
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


@router.get("/google/callback")
async def google_oauth_redirect_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Handles browser loopback redirect from Google OAuth consent screen.
    Exchanges authorization code for tokens, provisions user, and redirects to dashboard.
    """
    if error:
        logger.warning(f"Google OAuth redirected with error: {error}")
        return RedirectResponse(url=f"/?auth_error={error}", status_code=302)

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code from Google.")

    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google credentials not configured on server.")

    # Exchange authorization code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code"
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(token_url, data=data)
            if resp.status_code != 200:
                logger.error(f"Google token exchange failed: {resp.text}")
                return RedirectResponse(url="/?auth_error=exchange_failed", status_code=302)
            token_data = resp.json()

        id_token = token_data.get("id_token")
        if not id_token:
            return RedirectResponse(url="/?auth_error=missing_id_token", status_code=302)

        id_data = verify_google_id_token(id_token)
        if not id_data:
            return RedirectResponse(url="/?auth_error=invalid_token", status_code=302)

        # Provision user
        user = auth_service.get_or_create_user(
            db=db,
            google_sub=id_data["sub"],
            email=id_data["email"],
            display_name=id_data.get("name", "GHOSTMIND User"),
            avatar_url=id_data.get("picture")
        )

        # Migrate guest conversations to this Google user
        try:
            guest_users = db.scalars(select(User).where(User.google_sub == "local_guest_offline_sub")).all()
            for g in guest_users:
                if g.id != user.id:
                    db.query(Conversation).filter(Conversation.user_id == g.id).update({Conversation.user_id: user.id}, synchronize_session=False)
                    db.query(Message).filter(Message.user_id == g.id).update({Message.user_id: user.id}, synchronize_session=False)
            db.commit()
        except Exception as e:
            logger.warning(f"Notice during OAuth conversation migration: {e}")
            db.rollback()

        raw_session_token = auth_service.create_session(db, user.id)

        redirect = RedirectResponse(url="/", status_code=302)
        redirect.set_cookie(
            key=settings.SESSION_COOKIE_NAME,
            value=raw_session_token,
            max_age=settings.SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/"
        )
        return redirect

    except Exception as e:
        logger.error(f"Error handling Google OAuth callback: {e}")
        return RedirectResponse(url=f"/?auth_error={urllib.parse.quote(str(e))}", status_code=302)


class GoogleSignInPayload(BaseModel):
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None


@router.post("/google/signin", response_model=SessionResponse)
def signin_with_google_account(
    payload: GoogleSignInPayload,
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Signs in or registers with Google account details.
    Establishes a persistent session cookie and saves user in PostgreSQL.
    Seamlessly migrates any prior guest conversations to this Google user.
    """
    clean_email = payload.email.strip().lower()
    if not clean_email or "@" not in clean_email:
        raise HTTPException(status_code=400, detail="A valid Google email address is required.")

    display_name = payload.name.strip() if payload.name else clean_email.split("@")[0].capitalize()
    
    # Deterministic Google subject ID
    sub_hash = hashlib.sha256(f"google_oauth_{clean_email}".encode()).hexdigest()[:24]
    google_sub = f"10{int(sub_hash, 16) % 10**19}"

    # Google/Gravatar styled avatar
    gravatar_hash = hashlib.md5(clean_email.encode()).hexdigest()
    avatar_url = payload.picture or f"https://www.gravatar.com/avatar/{gravatar_hash}?d=identicon&s=128"

    user = auth_service.get_or_create_user(
        db=db,
        google_sub=google_sub,
        email=clean_email,
        display_name=display_name,
        avatar_url=avatar_url
    )

    # Migrate any guest conversations and messages to this Google user so history is preserved
    try:
        prev_token = get_session_token_from_request(request)
        prev_user = auth_service.authenticate_session(db, prev_token) if prev_token else None
        guest_sub = "local_guest_offline_sub"
        
        target_ids = []
        if prev_user and prev_user.google_sub == guest_sub and prev_user.id != user.id:
            target_ids.append(prev_user.id)
            
        guest_users = db.scalars(select(User).where(User.google_sub == guest_sub)).all()
        for g in guest_users:
            if g.id != user.id and g.id not in target_ids:
                target_ids.append(g.id)
                
        for gid in target_ids:
            db.query(Conversation).filter(Conversation.user_id == gid).update({Conversation.user_id: user.id}, synchronize_session=False)
            db.query(Message).filter(Message.user_id == gid).update({Message.user_id: user.id}, synchronize_session=False)
        db.commit()
    except Exception as e:
        logger.warning(f"Notice during guest conversation migration: {e}")
        db.rollback()

    raw_session_token = auth_service.create_session(db, user.id)

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=raw_session_token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/"
    )

    return SessionResponse(
        authenticated=True,
        user=UserProfileSchema.from_orm(user),
        message=f"Signed in successfully as {display_name}."
    )



@router.post("/google/callback", response_model=SessionResponse)
def google_callback(
    payload: GoogleAuthRequest,
    response: Response,
    db: Session = Depends(get_db)
):
    """
    Validates Google identity token from client-side Google Identity Services.
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

    raw_session_token = auth_service.create_session(db, user.id)

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=raw_session_token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
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
