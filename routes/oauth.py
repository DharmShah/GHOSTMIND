import os
import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from core.database import get_db
from core.user import get_local_user
from models import User
from services.oauth_service import oauth_manager, PROVIDER_ADAPTERS
from services.credential_service import credential_service

router = APIRouter(prefix="/api/oauth", tags=["Universal OAuth 2.0"])

@router.get("/{provider}/authorize")
def get_authorization_url(
    provider: str,
    request: Request,
    current_user: User = Depends(get_local_user)
):
    """
    Generates a secure OAuth 2.0 authorization URL for any supported provider
    (Google, GitHub, Figma, Slack, Notion) with CSRF state and PKCE parameters.
    """
    clean_provider = provider.lower()
    if clean_provider not in PROVIDER_ADAPTERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported OAuth provider '{provider}'. Supported: {list(PROVIDER_ADAPTERS.keys())}"
        )

    # Use loopback callback
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/oauth/callback"

    # Support configured redirect URI in .env if present
    if clean_provider == "google":
        env_redirect = os.getenv("GOOGLE_REDIRECT_URI")
        if env_redirect:
            redirect_uri = env_redirect

    try:
        auth_data = oauth_manager.generate_authorization_url(
            provider_name=clean_provider,
            user_id=current_user.id,
            redirect_uri=redirect_uri
        )
        auth_data["url"] = auth_data.get("authorization_url")
        return auth_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/callback")
async def oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Unified OAuth 2.0 loopback callback handler.
    Validates CSRF state parameter, exchanges code for access & refresh tokens,
    encrypts tokens with Fernet, and redirects back to the main UI.
    """
    if error:
        err_msg = error_description or error
        return RedirectResponse(url=f"/?oauth_error={err_msg}")

    if not code or not state:
        return RedirectResponse(url="/?oauth_error=Missing+authorization+code+or+state")

    try:
        result = await oauth_manager.handle_callback(db=db, code=code, state=state)
        provider = result.get("provider", "service")
        return RedirectResponse(url=f"/?oauth_success=1&provider={provider}")
    except ValueError as e:
        return RedirectResponse(url=f"/?oauth_error={str(e)}")
    except Exception as e:
        return RedirectResponse(url=f"/?oauth_error=OAuth+exchange+failed:+{str(e)}")

@router.delete("/{provider}")
def revoke_provider_oauth(
    provider: str,
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Revokes and permanently removes stored OAuth tokens for a provider."""
    success = credential_service.revoke_credentials(db, current_user.id, provider)
    return {
        "success": success,
        "provider": provider,
        "message": f"OAuth tokens revoked for {provider}"
    }

@router.get("/credentials")
def list_credentials(
    current_user: User = Depends(get_local_user),
    db: Session = Depends(get_db)
):
    """Lists connected OAuth credentials without leaking sensitive tokens."""
    return credential_service.list_safe_credentials(db, current_user.id)

