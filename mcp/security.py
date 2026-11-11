import os
import base64
import ipaddress
import urllib.parse
from typing import List, Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from core.config import settings

_fernet_instance: Optional[Fernet] = None

def _get_fernet() -> Fernet:
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance

    # Obtain key from settings or environment
    raw_key = os.getenv(
        "TOKEN_ENCRYPTION_KEY",
        getattr(settings, "TOKEN_ENCRYPTION_KEY", "ghostmind-default-secure-mcp-encryption-key-2026")
    )
    
    # Derive a valid 32-byte URL-safe base64-encoded key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"ghostmind_mcp_salt_v1",
        iterations=100_000,
    )
    derived_key = base64.urlsafe_b64encode(kdf.derive(raw_key.encode("utf-8")))
    _fernet_instance = Fernet(derived_key)
    return _fernet_instance


def encrypt_secret(plaintext: str) -> str:
    """Encrypts sensitive tokens or secrets before database persistence."""
    if not plaintext:
        return ""
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """Decrypts ciphertext retrieved from the database."""
    if not ciphertext:
        return ""
    try:
        fernet = _get_fernet()
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except Exception as e:
        # Never leak raw ciphertext in logs
        raise ValueError(f"Decryption failed or invalid key: {type(e).__name__}")


def validate_remote_url(url: str, allow_local_dev: bool = False) -> bool:
    """
    Validates remote MCP server URLs to protect against SSRF, cloud metadata exfiltration,
    and private intranet scanning.
    """
    if not url:
        return False

    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # Check for AWS / GCP / Azure metadata endpoint
        if hostname in ("169.254.169.254", "metadata.google.internal", "metadata"):
            return False

        # Attempt IP check
        try:
            ip = ipaddress.ip_address(hostname)
            if not allow_local_dev:
                if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                    return False
        except ValueError:
            # Domain name, check for forbidden localhost patterns unless dev mode
            if not allow_local_dev and hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0"):
                return False

        return True
    except Exception:
        return False


def validate_stdio_command(command: str, args: List[str]) -> bool:
    """
    Validates stdio executable and arguments to prevent arbitrary command injection.
    Allows standard runtimes: npx, node, python, uv, uvx, docker.
    """
    if not command:
        return False

    clean_cmd = os.path.basename(command).lower()
    if clean_cmd.endswith(".exe"):
        clean_cmd = clean_cmd[:-4]

    allowed_commands = {
        "npx", "node", "python", "python3", "uv", "uvx", "docker", "mcp"
    }

    if clean_cmd not in allowed_commands:
        # Also allow absolute paths to python executables in venv
        if not (os.path.isabs(command) and os.path.exists(command)):
            return False

    # Check for shell piping / chaining injection tokens
    forbidden_tokens = {";", "&", "|", "`", "$", "\n", "\r"}
    for arg in args:
        if any(token in arg for token in forbidden_tokens):
            return False

    return True

