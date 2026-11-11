import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from models import IntegrationCredential
from mcp.security import encrypt_secret, decrypt_secret

logger = logging.getLogger("ghostmind.services.credential")

def utc_now():
    return datetime.now(timezone.utc)

class CredentialService:
    """
    Secure credential manager encrypting access tokens, refresh tokens,
    and client secrets with Fernet encryption before PostgreSQL persistence.
    """

    def store_credentials(
        self,
        db: Session,
        user_id: uuid.UUID,
        provider: str,
        service_name: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        client_secret: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        expires_in_seconds: Optional[int] = None,
        account_identifier: Optional[str] = None,
        server_id: Optional[str] = None
    ) -> IntegrationCredential:
        """Encrypts sensitive fields and persists or updates an IntegrationCredential record."""
        record = db.query(IntegrationCredential).filter(
            IntegrationCredential.user_id == user_id,
            IntegrationCredential.provider == provider,
            IntegrationCredential.service_name == service_name
        ).first()

        expiry = None
        if expires_in_seconds:
            expiry = utc_now() + timedelta(seconds=int(expires_in_seconds))

        enc_access = encrypt_secret(access_token) if access_token else None
        enc_refresh = encrypt_secret(refresh_token) if refresh_token else None
        enc_secret = encrypt_secret(client_secret) if client_secret else None
        scopes_json = json.dumps(scopes) if scopes else None

        if not record:
            record = IntegrationCredential(
                user_id=user_id,
                provider=provider.lower(),
                service_name=service_name.lower(),
                server_id=server_id,
                encrypted_access_token=enc_access,
                encrypted_refresh_token=enc_refresh,
                encrypted_client_secret=enc_secret,
                granted_scopes=scopes_json,
                token_expiry=expiry,
                connection_status="connected",
                account_identifier=account_identifier
            )
            db.add(record)
        else:
            record.encrypted_access_token = enc_access
            if enc_refresh:
                record.encrypted_refresh_token = enc_refresh
            if enc_secret:
                record.encrypted_client_secret = enc_secret
            record.granted_scopes = scopes_json
            record.token_expiry = expiry
            record.connection_status = "connected"
            if account_identifier:
                record.account_identifier = account_identifier

        db.commit()
        db.refresh(record)
        logger.info(f"Stored encrypted credentials for '{provider}:{service_name}' (user={user_id})")
        return record

    def get_decrypted_credentials(
        self,
        db: Session,
        user_id: uuid.UUID,
        provider: str,
        service_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Retrieves and decrypts tokens for internal service/MCP usage."""
        p_clean = provider.lower()
        candidates = [p_clean]
        if "-" in p_clean:
            candidates.append(p_clean.split("-")[0])
        if p_clean.endswith("-workspace"):
            candidates.append(p_clean.replace("-workspace", ""))

        record = None
        for cand in candidates:
            query = db.query(IntegrationCredential).filter(
                IntegrationCredential.user_id == user_id,
                (IntegrationCredential.provider == cand) | (IntegrationCredential.service_name == cand) | (IntegrationCredential.server_id == cand)
            )
            if service_name:
                query = query.filter(IntegrationCredential.service_name == service_name.lower())
            record = query.first()
            if record:
                break

        if not record:
            record = db.query(IntegrationCredential).filter(
                IntegrationCredential.user_id == user_id,
                (IntegrationCredential.provider.in_(candidates)) | (IntegrationCredential.service_name.in_(candidates))
            ).first()

        if not record:
            return None

        access_token = decrypt_secret(record.encrypted_access_token) if record.encrypted_access_token else None
        refresh_token = decrypt_secret(record.encrypted_refresh_token) if record.encrypted_refresh_token else None
        client_secret = decrypt_secret(record.encrypted_client_secret) if record.encrypted_client_secret else None

        is_expired = False
        if record.token_expiry and record.token_expiry <= utc_now():
            is_expired = True

        return {
            "id": str(record.id),
            "provider": record.provider,
            "service_name": record.service_name,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "client_secret": client_secret,
            "scopes": json.loads(record.granted_scopes) if record.granted_scopes else [],
            "token_expiry": record.token_expiry,
            "is_expired": is_expired,
            "connection_status": record.connection_status,
            "account_identifier": record.account_identifier
        }

    def list_safe_credentials(self, db: Session, user_id: uuid.UUID) -> List[Dict[str, Any]]:
        """Lists active user credentials with ZERO plaintext token leakage."""
        records = db.query(IntegrationCredential).filter(
            IntegrationCredential.user_id == user_id
        ).all()

        results = []
        for r in records:
            is_expired = False
            if r.token_expiry and r.token_expiry <= utc_now():
                is_expired = True

            results.append({
                "id": str(r.id),
                "provider": r.provider,
                "service_name": r.service_name,
                "connection_status": r.connection_status,
                "account_identifier": r.account_identifier,
                "scopes": json.loads(r.granted_scopes) if r.granted_scopes else [],
                "is_expired": is_expired,
                "token_expiry": r.token_expiry.isoformat() if r.token_expiry else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None
            })
        return results

    def revoke_credentials(
        self,
        db: Session,
        user_id: uuid.UUID,
        provider: str,
        service_name: Optional[str] = None
    ) -> bool:
        """Deletes credential records for a provider/service."""
        query = db.query(IntegrationCredential).filter(
            IntegrationCredential.user_id == user_id,
            IntegrationCredential.provider == provider.lower()
        )
        if service_name:
            query = query.filter(IntegrationCredential.service_name == service_name.lower())

        records = query.all()
        if not records:
            return False

        for r in records:
            db.delete(r)
        db.commit()
        logger.info(f"Revoked credentials for '{provider}' (user={user_id})")
        return True


credential_service = CredentialService()

