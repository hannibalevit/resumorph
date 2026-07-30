"""Per-task LLM provider/model resolution and settings serialization.

Each generation task (``scan``, ``resume``, ``field_answer``) can have its own
provider/model override stored on ``AppSettingsModel``, falling back to the global
default provider. ``resolve_task_llm`` / ``resolve_default_llm`` implement that
fallback chain — use these rather than reading ``AppSettingsModel`` fields directly.
"""

from typing import NamedTuple, cast
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DEFAULT_OLLAMA_BASE_URL, get_settings
from app.errors import fail
from app.models import AppSettingsModel, LlmProviderConfigModel
from app.schemas import LlmTaskName, ProviderName, TaskLlmSetting
from app.security import SecretEncryptionError, decrypt_secret

settings = get_settings()

LLM_TASKS = ("scan", "resume", "field_answer")
KEYLESS_PROVIDERS = frozenset({"ollama"})
SUPPORTED_PROVIDERS = ("openai", "gemini", "claude", "ollama")


class ResolvedLlm(NamedTuple):
    provider: str
    model: str
    api_key: str
    base_url: str | None


def default_model_for(provider: str) -> str:
    return {
        "openai": settings.default_openai_model,
        "gemini": settings.default_gemini_model,
        "claude": settings.default_claude_model,
        "ollama": settings.default_ollama_model,
    }[provider]


def normalize_base_url(url: str) -> str:
    """Validate and canonicalize a user-supplied Ollama base URL.

    Rejects embedded credentials (they can leak via httpx error text). Drops
    query strings and fragments. Strips trailing slashes.
    """
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise fail(
            422,
            "LLM_PROVIDER_ERROR",
            "Base URL must be an absolute http:// or https:// URL.",
            baseUrl=url,
        )
    if parsed.username is not None or parsed.password is not None:
        raise fail(
            422,
            "LLM_PROVIDER_ERROR",
            "Base URL must not include credentials.",
            baseUrl=url,
        )
    # urlparse.port raises ValueError for non-integer or out-of-range ports.
    try:
        port = parsed.port
    except ValueError:
        raise fail(
            422,
            "LLM_PROVIDER_ERROR",
            "Base URL must have a valid port.",
            baseUrl=url,
        ) from None
    host = parsed.hostname
    # urlparse strips brackets from IPv6 literals; put them back for the URL.
    if ":" in host:
        host = f"[{host}]"
    netloc = f"{host}:{port}" if port is not None else host
    path = (parsed.path or "").rstrip("/")
    return f"{parsed.scheme}://{netloc}{path}"


def resolve_ollama_base_url(saved: str | None) -> str:
    """saved base_url → OLLAMA_BASE_URL from settings (config.py is the sole default)."""
    if saved and saved.strip():
        return saved.strip().rstrip("/")
    # Whitespace-only env must not win over the real default (strip, then fall back).
    env = settings.ollama_base_url.strip().rstrip("/")
    return env or DEFAULT_OLLAMA_BASE_URL


def effective_default_provider(app_settings: AppSettingsModel | None) -> str:
    return (
        app_settings.default_provider
        if app_settings and app_settings.default_provider
        else settings.default_llm_provider
    )


def has_configured_default_provider(app_settings: AppSettingsModel | None) -> bool:
    return bool(app_settings and app_settings.default_provider)


def task_provider_model(
    app_settings: AppSettingsModel | None, task: str
) -> tuple[str | None, str | None]:
    if app_settings is None:
        return None, None
    return getattr(app_settings, f"{task}_provider", None), getattr(
        app_settings, f"{task}_model", None
    )


def resolve_llm(db: Session, provider_name: str, model: str | None = None) -> ResolvedLlm:
    config = db.scalar(
        select(LlmProviderConfigModel).where(
            LlmProviderConfigModel.provider == provider_name,
            LlmProviderConfigModel.is_enabled.is_(True),
        )
    )
    if config is None:
        raise fail(
            400,
            "LLM_PROVIDER_NOT_CONFIGURED",
            "No LLM provider configured. Open Settings and add an API key.",
            provider=provider_name,
        )
    try:
        api_key = decrypt_secret(config.encrypted_api_key)
    except SecretEncryptionError as exc:
        raise fail(500, "SETTINGS_SAVE_FAILED", str(exc)) from exc
    effective_model = model or config.default_model or default_model_for(provider_name)
    if not effective_model:
        raise fail(
            400,
            "LLM_MODEL_NOT_AVAILABLE",
            "No model configured for the selected provider.",
            provider=provider_name,
        )
    base_url = (
        resolve_ollama_base_url(config.base_url) if provider_name == "ollama" else config.base_url
    )
    return ResolvedLlm(provider_name, effective_model, api_key, base_url)


def resolve_default_llm(db: Session) -> ResolvedLlm:
    app_settings = db.get(AppSettingsModel, "local-settings")
    provider_name = effective_default_provider(app_settings)
    model = (
        app_settings.default_model
        if app_settings and app_settings.default_provider == provider_name
        else None
    )
    return resolve_llm(db, provider_name, model)


def resolve_task_llm(db: Session, task: str) -> ResolvedLlm:
    app_settings = db.get(AppSettingsModel, "local-settings")
    task_provider, task_model = task_provider_model(app_settings, task)
    if task_provider:
        config = db.scalar(
            select(LlmProviderConfigModel).where(
                LlmProviderConfigModel.provider == task_provider,
                LlmProviderConfigModel.is_enabled.is_(True),
            )
        )
        if config:
            return resolve_llm(db, task_provider, task_model)
    return resolve_default_llm(db)


def task_setting_response(
    db: Session, app_settings: AppSettingsModel | None, task: str
) -> TaskLlmSetting:
    task_provider, task_model = task_provider_model(app_settings, task)
    is_custom = bool(task_provider)
    if task_provider:
        config = db.scalar(
            select(LlmProviderConfigModel).where(
                LlmProviderConfigModel.provider == task_provider,
                LlmProviderConfigModel.is_enabled.is_(True),
            )
        )
        if config:
            return TaskLlmSetting(
                task=cast(LlmTaskName, task),
                provider=cast(ProviderName, task_provider),
                model=task_model or config.default_model or default_model_for(task_provider),
                isCustom=is_custom,
            )
    provider_name = effective_default_provider(app_settings)
    config = db.scalar(
        select(LlmProviderConfigModel).where(
            LlmProviderConfigModel.provider == provider_name,
            LlmProviderConfigModel.is_enabled.is_(True),
        )
    )
    model = (
        (
            app_settings.default_model
            if app_settings and app_settings.default_provider == provider_name
            else None
        )
        or (config.default_model if config else None)
        or default_model_for(provider_name)
    )
    return TaskLlmSetting(
        task=cast(LlmTaskName, task),
        provider=cast(ProviderName, provider_name),
        model=model,
        isCustom=False,
    )
