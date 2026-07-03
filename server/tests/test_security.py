import pytest
from app.config import get_settings
from app.security import SecretEncryptionError, decrypt_secret, encrypt_secret, mask_secret


def test_encrypt_secret_round_trips() -> None:
    encrypted = encrypt_secret("sk-test-secret")

    assert encrypted != "sk-test-secret"
    assert decrypt_secret(encrypted) == "sk-test-secret"


def test_mask_secret_hides_short_values_and_keeps_edges_for_long_values() -> None:
    assert mask_secret("short") == "••••"
    assert mask_secret("sk-1234567890") == "sk-1...7890"


def test_encrypt_secret_requires_valid_fernet_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", "not-a-fernet-key")
    get_settings.cache_clear()

    with pytest.raises(SecretEncryptionError, match="valid Fernet key"):
        encrypt_secret("sk-test-secret")
