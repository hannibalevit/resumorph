from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretEncryptionError(ValueError):
    pass


def _fernet() -> Fernet:
    key = get_settings().master_encryption_key.strip()
    if not key:
        raise SecretEncryptionError("MASTER_ENCRYPTION_KEY is not configured.")
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise SecretEncryptionError("MASTER_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError, TypeError) as exc:
        raise SecretEncryptionError("Stored provider key cannot be decrypted.") from exc


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "••••"
    return f"{value[:4]}...{value[-4:]}"
