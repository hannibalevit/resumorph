"""Per-task LLM provider/model resolution and settings serialization.

Each generation task (``scan``, ``resume``, ``field_answer``) can have its own
provider/model override stored on ``AppSettingsModel``, falling back to the global
default provider. ``resolve_task_llm`` / ``resolve_default_llm`` implement that
fallback chain — use these rather than reading ``AppSettingsModel`` fields directly.
"""

from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.errors import fail
from app.models import AppSettingsModel, LlmProviderConfigModel
from app.schemas import LlmTaskName, ProviderName, TaskLlmSetting
from app.security import SecretEncryptionError, decrypt_secret

settings = get_settings()

LLM_TASKS = ("scan", "resume", "field_answer")


def default_model_for(provider: str) -> str:
    return {
        "openai": settings.default_openai_model,
        "gemini": settings.default_gemini_model,
        "claude": settings.default_claude_model,
    }[provider]


def effective_default_provider(app_settings: AppSettingsModel | None) -> str:
    return (
        app_settings.default_provider
        if app_settings and app_settings.default_provider
        else settings.default_llm_provider
    )


def task_provider_model(
    app_settings: AppSettingsModel | None, task: str
) -> tuple[str | None, str | None]:
    if app_settings is None:
        return None, None
    return getattr(app_settings, f"{task}_provider", None), getattr(
        app_settings, f"{task}_model", None
    )


def resolve_llm(db: Session, provider_name: str, model: str | None = None) -> tuple[str, str, str]:
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
    effective_model = model or config.default_model or default_model_for(provider_name)
    if not effective_model:
        raise fail(
            400,
            "LLM_MODEL_NOT_AVAILABLE",
            "No model configured for the selected provider.",
            provider=provider_name,
        )
    try:
        return provider_name, effective_model, decrypt_secret(config.encrypted_api_key)
    except SecretEncryptionError as exc:
        raise fail(500, "SETTINGS_SAVE_FAILED", str(exc)) from exc


def resolve_default_llm(db: Session) -> tuple[str, str, str]:
    app_settings = db.get(AppSettingsModel, "local-settings")
    provider_name = effective_default_provider(app_settings)
    model = (
        app_settings.default_model
        if app_settings and app_settings.default_provider == provider_name
        else None
    )
    return resolve_llm(db, provider_name, model)


def resolve_task_llm(db: Session, task: str) -> tuple[str, str, str]:
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
