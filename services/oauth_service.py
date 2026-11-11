import os
import time
import json
import base64
import uuid
import secrets
import hashlib
import asyncio
import logging
import urllib.parse
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import httpx
from sqlalchemy.orm import Session

from core.config import settings
from services.credential_service import credential_service

logger = logging.getLogger("ghostmind.services.oauth")

def utc_now():
    return datetime.now(timezone.utc)

class OAuthProviderAdapter:
    """Config and endpoint adapter for an external OAuth 2.0 / 2.1 provider."""

    def __init__(
        self,
        name: str,
        display_name: str,
        auth_url: str,
        token_url: str,
        revoke_url: Optional[str] = None,
        default_scopes: Optional[List[str]] = None,
        supports_pkce: bool = True,
        client_id_env: str = "",
        client_secret_env: str = ""
    ):
        self.name = name.lower()
        self.display_name = display_name
        self.auth_url = auth_url
        self.token_url = token_url
        self.revoke_url = revoke_url
        self.default_scopes = default_scopes or []
        self.supports_pkce = supports_pkce
        self.client_id_env = client_id_env or f"{name.upper()}_CLIENT_ID"
        self.client_secret_env = client_secret_env or f"{name.upper()}_CLIENT_SECRET"

    def get_credentials(self) -> Tuple[str, str]:
        client_id = os.getenv(self.client_id_env, "")
        client_secret = os.getenv(self.client_secret_env, "")
        return client_id, client_secret

# Registry of supported OAuth Provider Adapters
PROVIDER_ADAPTERS: Dict[str, OAuthProviderAdapter] = {
    "google": OAuthProviderAdapter(
        name="google",
        display_name="Google Workspace (Gmail, Calendar, Drive)",
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        revoke_url="https://oauth2.googleapis.com/revoke",
        default_scopes=[
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/drive.readonly"
        ],
        supports_pkce=True,
        client_id_env="GOOGLE_CLIENT_ID",
        client_secret_env="GOOGLE_CLIENT_SECRET"
    ),
    "github": OAuthProviderAdapter(
        name="github",
        display_name="GitHub",
        auth_url="https://github.com/login/oauth/authorize",
        token_url="https://github.com/login/oauth/access_token",
        revoke_url="https://api.github.com/applications",
        default_scopes=["repo", "read:user"],
        supports_pkce=False,
        client_id_env="GITHUB_CLIENT_ID",
        client_secret_env="GITHUB_CLIENT_SECRET"
    ),
    "figma": OAuthProviderAdapter(
        name="figma",
        display_name="Figma",
        auth_url="https://www.figma.com/oauth",
        token_url="https://api.figma.com/v1/oauth/token",
        default_scopes=["file_read", "comments:read", "comments:write"],
        supports_pkce=False,
        client_id_env="FIGMA_CLIENT_ID",
        client_secret_env="FIGMA_CLIENT_SECRET"
    ),
    "slack": OAuthProviderAdapter(
        name="slack",
        display_name="Slack",
        auth_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        default_scopes=["channels:read", "channels:history", "chat:write"],
        supports_pkce=True,
        client_id_env="SLACK_CLIENT_ID",
        client_secret_env="SLACK_CLIENT_SECRET"
    ),
    "notion": OAuthProviderAdapter(
        name="notion",
        display_name="Notion",
        auth_url="https://api.notion.com/v1/oauth/authorize",
        token_url="https://api.notion.com/v1/oauth/token",
        default_scopes=["read", "write"],
        supports_pkce=False,
        client_id_env="NOTION_CLIENT_ID",
        client_secret_env="NOTION_CLIENT_SECRET"
    )
}

class UniversalOAuthManager:
    """
    Manages OAuth 2.0 / 2.1 state generation, PKCE challenges, secure token
    exchanges, refresh synchronization locks, and provider revocations.
    """

    def __init__(self):
        # In-memory transient state map: state -> metadata
        self._states: Dict[str, Dict[str, Any]] = {}
        # Concurrency locks for token refresh: (provider, user_id) -> Lock
        self._refresh_locks: Dict[str, asyncio.Lock] = {}

    def _get_refresh_lock(self, provider: str, user_id: uuid.UUID) -> asyncio.Lock:
        key = f"{provider}:{user_id}"
        if key not in self._refresh_locks:
            self._refresh_locks[key] = asyncio.Lock()
        return self._refresh_locks[key]

    def generate_authorization_url(
        self,
        provider_name: str,
        user_id: uuid.UUID,
        redirect_uri: str,
        custom_scopes: Optional[List[str]] = None,
        custom_client_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates a secure authorization URL with CSRF state and PKCE."""
        adapter = PROVIDER_ADAPTERS.get(provider_name.lower())
        if not adapter:
            raise ValueError(f"Unsupported OAuth provider: '{provider_name}'")

        client_id, _ = adapter.get_credentials()
        if custom_client_id:
            client_id = custom_client_id

        if not client_id:
            return {
                "configured": False,
                "provider": provider_name,
                "message": f"Client ID for {adapter.display_name} is not configured in .env ({adapter.client_id_env})."
            }

        # 1. State token for CSRF defense
        state = secrets.token_urlsafe(32)

        # 2. PKCE code verifier and challenge
        code_verifier = None
        code_challenge = None
        if adapter.supports_pkce:
            code_verifier = secrets.token_urlsafe(64)
            digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
            code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

        # Clean expired states
        now = time.time()
        self._states = {s: v for s, v in self._states.items() if now - v.get("created_at", 0) < 600}

        # Store state metadata (expires in 10 minutes)
        self._states[state] = {
            "provider": provider_name.lower(),
            "user_id": str(user_id),
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "created_at": now
        }

        scopes = custom_scopes or adapter.default_scopes
        scope_str = " ".join(scopes) if provider_name != "google" else " ".join(scopes)

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": scope_str
        }

        # Provider-specific parameters
        if provider_name == "google":
            params["access_type"] = "offline"
            params["prompt"] = "consent"
        elif provider_name == "notion":
            params["owner"] = "user"

        if code_challenge:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"

        auth_url = f"{adapter.auth_url}?{urllib.parse.urlencode(params)}"

        return {
            "configured": True,
            "provider": provider_name,
            "authorization_url": auth_url,
            "state": state,
            "scopes": scopes
        }

    def validate_state(self, state: str) -> Dict[str, Any]:
        """Validates and consumes a CSRF state parameter. Raises ValueError if invalid or expired."""
        state_data = self._states.pop(state, None)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state parameter (potential CSRF).")
        return state_data

    async def handle_callback(
        self,
        db: Session,
        code: str,
        state: str,
        provider_hint: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validates CSRF state and exchanges auth code for encrypted credentials."""
        state_data = self.validate_state(state)

        provider_name = state_data["provider"]
        user_id = uuid.UUID(state_data["user_id"])
        redirect_uri = state_data["redirect_uri"]
        code_verifier = state_data.get("code_verifier")

        adapter = PROVIDER_ADAPTERS.get(provider_name)
        if not adapter:
            raise ValueError(f"Unknown provider: {provider_name}")

        client_id, client_secret = adapter.get_credentials()
        if not client_id or not client_secret:
            raise ValueError(f"Missing OAuth credentials for {provider_name} in environment.")

        # Build token exchange request
        token_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri
        }
        if code_verifier:
            token_payload["code_verifier"] = code_verifier

        headers = {
            "Accept": "application/json",
            "User-Agent": "GHOSTMIND-Universal-OAuth/1.0"
        }

        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(adapter.token_url, data=token_payload, headers=headers)
            if not resp.is_success:
                logger.error(f"OAuth token exchange failed ({resp.status_code}): {resp.text}")
                raise RuntimeError(f"Token exchange failed with {adapter.display_name}: {resp.text}")

            token_data = resp.json()

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        scope_str = token_data.get("scope", "")
        granted_scopes = scope_str.split() if isinstance(scope_str, str) and scope_str else []

        # Extract account identifier if provided
        account_id = None
        if "user" in token_data and isinstance(token_data["user"], dict):
            account_id = token_data["user"].get("email") or token_data["user"].get("name")
        elif "authed_user" in token_data:
            account_id = token_data["authed_user"].get("id")

        # Encrypt and store in database
        credential_record = credential_service.store_credentials(
            db=db,
            user_id=user_id,
            provider=provider_name,
            service_name=provider_name,
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=granted_scopes,
            expires_in_seconds=expires_in,
            account_identifier=account_id
        )

        logger.info(f"Successfully authenticated with {adapter.display_name} for local user")

        return {
            "success": True,
            "provider": provider_name,
            "service_name": provider_name,
            "account_identifier": account_id,
            "connection_status": "connected",
            "scopes": granted_scopes
        }

    async def refresh_access_token_if_needed(
        self,
        db: Session,
        user_id: uuid.UUID,
        provider_name: str,
        service_name: Optional[str] = None
    ) -> Optional[str]:
        """
        Thread-safe token refresher. Checks if token is near expiration (< 5 mins),
        acquires an asynchronous provider lock, exchanges refresh token, and re-encrypts.
        """
        target_service = service_name or provider_name
        creds = credential_service.get_decrypted_credentials(db, user_id, provider_name, target_service)
        if not creds:
            return None

        # Check expiration threshold
        expiry = creds.get("token_expiry")
        if expiry and expiry > (utc_now() + datetime.resolution * 300):
            return creds["access_token"]  # Still valid

        refresh_token = creds.get("refresh_token")
        if not refresh_token:
            logger.warning(f"No refresh token available for {provider_name}:{target_service}")
            return creds.get("access_token")

        adapter = PROVIDER_ADAPTERS.get(provider_name.lower())
        if not adapter:
            return creds.get("access_token")

        client_id, client_secret = adapter.get_credentials()
        async with self._get_refresh_lock(provider_name, user_id):
            # Double-check inside lock
            rechecked = credential_service.get_decrypted_credentials(db, user_id, provider_name, target_service)
            if rechecked and rechecked.get("token_expiry") and rechecked["token_expiry"] > (utc_now() + datetime.resolution * 300):
                return rechecked["access_token"]

            payload = {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            }
            headers = {"Accept": "application/json"}

            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.post(adapter.token_url, data=payload, headers=headers)
                    if not resp.is_success:
                        logger.error(f"Token refresh failed for {provider_name}: {resp.text}")
                        return creds.get("access_token")
                    data = resp.json()

                new_access_token = data.get("access_token")
                new_refresh_token = data.get("refresh_token") or refresh_token
                expires_in = data.get("expires_in")

                credential_service.store_credentials(
                    db=db,
                    user_id=user_id,
                    provider=provider_name,
                    service_name=target_service,
                    access_token=new_access_token,
                    refresh_token=new_refresh_token,
                    expires_in_seconds=expires_in
                )
                logger.info(f"Refreshed access token for {provider_name}:{target_service}")
                return new_access_token
            except Exception as e:
                logger.error(f"Error during token refresh: {e}")
                return creds.get("access_token")


oauth_manager = UniversalOAuthManager()
