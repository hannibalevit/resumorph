"""Focused coverage for Ollama resolution and keyless settings paths."""

from datetime import datetime

import pytest
from app.models import AppSettingsModel, LlmProviderConfigModel
from app.routers import settings as settings_router
from app.security import encrypt_secret
from app.services.llm_settings import (
    default_model_for,
    resolve_default_llm,
    resolve_llm,
    resolve_task_llm,
)
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_default_model_for_ollama() -> None:
    assert default_model_for("ollama")


def test_resolve_llm_ollama_returns_base_url(db_session: Session) -> None:
    db_session.add(
        LlmProviderConfigModel(
            provider="ollama",
            encrypted_api_key=encrypt_secret(""),
            key_mask="",
            base_url="http://10.0.0.9:11434",
            default_model="llama3.2",
            is_enabled=True,
        )
    )
    db_session.commit()

    resolved = resolve_llm(db_session, "ollama")
    assert resolved.provider == "ollama"
    assert resolved.model == "llama3.2"
    assert resolved.api_key == ""
    assert resolved.base_url == "http://10.0.0.9:11434"


def test_resolve_task_llm_uses_task_override(db_session: Session) -> None:
    db_session.add(
        LlmProviderConfigModel(
            provider="ollama",
            encrypted_api_key=encrypt_secret(""),
            key_mask="",
            base_url=None,
            default_model="mistral",
            is_enabled=True,
        )
    )
    db_session.add(
        LlmProviderConfigModel(
            provider="openai",
            encrypted_api_key=encrypt_secret("sk-secret-123456"),
            key_mask="sk-s...3456",
            default_model="gpt-test",
            is_enabled=True,
        )
    )
    db_session.add(
        AppSettingsModel(
            id="local-settings",
            default_provider="openai",
            default_model="gpt-test",
            scan_provider="ollama",
            scan_model="llama3.2",
        )
    )
    db_session.commit()

    resolved = resolve_task_llm(db_session, "scan")
    assert resolved.provider == "ollama"
    assert resolved.model == "llama3.2"
    assert resolve_default_llm(db_session).provider == "openai"


def test_save_ollama_without_base_url_uses_env_default(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StubProvider:
        async def test_connection(self, api_key: str, model: str | None = None):
            return {"rawTextPreview": "ok"}

        async def list_models(self, api_key: str) -> list[str]:
            return ["llama3.2"]

    monkeypatch.setattr(
        settings_router, "get_llm_provider", lambda provider, base_url=None: StubProvider()
    )
    response = client.post(
        "/api/settings/llm-providers/ollama",
        json={"defaultModel": "llama3.2"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["keyMask"] == ""
    assert body["baseUrl"]  # effective URL from env/default
    assert body["isEnabled"] is True


def test_save_rejects_base_url_for_openai(client: TestClient) -> None:
    response = client.post(
        "/api/settings/llm-providers/openai",
        json={"apiKey": "sk-secret-123456", "baseUrl": "http://localhost:11434"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LLM_PROVIDER_ERROR"


def test_get_providers_includes_ollama_effective_url(client: TestClient) -> None:
    response = client.get("/api/settings/llm-providers")
    assert response.status_code == 200
    providers = {item["provider"]: item for item in response.json()["providers"]}
    assert "ollama" in providers
    assert providers["ollama"]["baseUrl"]
    assert providers["ollama"]["isEnabled"] is False


def test_update_ollama_base_url_on_existing_row(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StubProvider:
        async def test_connection(self, api_key: str, model: str | None = None):
            return {"rawTextPreview": "ok"}

        async def list_models(self, api_key: str) -> list[str]:
            return ["llama3.2"]

    monkeypatch.setattr(
        settings_router, "get_llm_provider", lambda provider, base_url=None: StubProvider()
    )
    first = client.post(
        "/api/settings/llm-providers/ollama",
        json={"baseUrl": "http://localhost:11434", "defaultModel": "llama3.2"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/settings/llm-providers/ollama",
        json={"baseUrl": "http://192.168.0.50:11434/", "defaultModel": "llama3.2"},
    )
    assert second.status_code == 200
    assert second.json()["baseUrl"] == "http://192.168.0.50:11434"


def test_list_ollama_models_persists_when_configured(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_session.add(
        LlmProviderConfigModel(
            provider="ollama",
            encrypted_api_key=encrypt_secret(""),
            key_mask="",
            default_model="llama3.2",
            is_enabled=True,
            available_models=None,
            models_updated_at=None,
        )
    )
    db_session.commit()

    class StubProvider:
        async def list_models(self, api_key: str) -> list[str]:
            return ["llama3.2", "mistral"]

    monkeypatch.setattr(
        settings_router, "get_llm_provider", lambda provider, base_url=None: StubProvider()
    )
    response = client.post(
        "/api/settings/llm-providers/ollama/models",
        json={"refresh": True},
    )
    assert response.status_code == 200
    assert response.json()["models"] == ["llama3.2", "mistral"]

    cached = client.get("/api/settings/llm-providers/ollama/models")
    assert cached.status_code == 200
    assert cached.json()["models"] == ["llama3.2", "mistral"]


def test_delete_ollama_clears_default(client: TestClient, db_session: Session) -> None:
    db_session.add(
        LlmProviderConfigModel(
            provider="ollama",
            encrypted_api_key=encrypt_secret(""),
            key_mask="",
            default_model="llama3.2",
            is_enabled=True,
        )
    )
    db_session.add(
        AppSettingsModel(
            id="local-settings",
            default_provider="ollama",
            default_model="llama3.2",
            updated_at=datetime.utcnow(),
        )
    )
    db_session.commit()

    assert client.delete("/api/settings/llm-providers/ollama").status_code == 204
    listed = client.get("/api/settings/llm-providers")
    assert listed.json()["defaultProvider"] in (None, "openai")
