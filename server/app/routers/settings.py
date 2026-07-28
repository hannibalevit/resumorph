"""LLM provider configuration and per-task routing settings.

``get_llm_provider`` is referenced here (for connection tests and model listing),
so tests that exercise these endpoints stub the LLM by patching it on this module.
"""

import time
from datetime import datetime
from typing import cast

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import fail
from app.llm.factory import get_llm_provider
from app.models import AppSettingsModel, LlmProviderConfigModel
from app.schemas import (
    LlmTaskName,
    ProviderConfigInput,
    ProviderModelsRequest,
    ProviderModelUpdateInput,
    ProviderName,
    ProviderPublicConfig,
    ProviderSettingsResponse,
    ProviderTestRequest,
    ProviderTestResponse,
    SetDefaultLlmRequest,
    SetTaskLlmRequest,
)
from app.security import SecretEncryptionError, decrypt_secret, encrypt_secret, mask_secret
from app.serializers import public_provider_config
from app.services.llm_settings import (
    KEYLESS_PROVIDERS,
    LLM_TASKS,
    SUPPORTED_PROVIDERS,
    default_model_for,
    effective_default_provider,
    has_configured_default_provider,
    normalize_base_url,
    resolve_ollama_base_url,
    task_setting_response,
)

router = APIRouter()


def _resolve_request_base_url(
    provider: str, requested: str | None, saved: str | None
) -> str | None:
    if provider != "ollama":
        return None
    if requested and requested.strip():
        return normalize_base_url(requested)
    return resolve_ollama_base_url(saved)


@router.get("/api/settings/llm-providers", response_model=ProviderSettingsResponse)
async def get_llm_providers(db: Session = Depends(get_db)) -> ProviderSettingsResponse:
    configs = {item.provider: item for item in db.scalars(select(LlmProviderConfigModel)).all()}
    app_settings = db.get(AppSettingsModel, "local-settings")
    default_provider = effective_default_provider(app_settings)
    default_config = configs.get(default_provider)
    default_model = (
        app_settings.default_model
        if app_settings and app_settings.default_provider == default_provider
        else None
    ) or (default_config.default_model if default_config else None)
    return ProviderSettingsResponse(
        providers=[
            public_provider_config(name, configs.get(name)) for name in SUPPORTED_PROVIDERS
        ],
        defaultProvider=cast("ProviderName | None", default_provider),
        defaultModel=default_model,
        taskSettings={
            cast(LlmTaskName, task): task_setting_response(db, app_settings, task)
            for task in LLM_TASKS
        },
    )


@router.post("/api/settings/llm-providers/{provider}", response_model=ProviderPublicConfig)
async def save_llm_provider(
    provider: str, payload: ProviderConfigInput, db: Session = Depends(get_db)
) -> ProviderPublicConfig:
    if provider not in SUPPORTED_PROVIDERS:
        raise fail(422, "LLM_PROVIDER_ERROR", "Unsupported LLM provider.")
    if provider not in KEYLESS_PROVIDERS and (not payload.api_key or len(payload.api_key) < 8):
        raise fail(
            422,
            "LLM_PROVIDER_ERROR",
            "API key is required for this provider.",
            provider=provider,
        )

    api_key = payload.api_key or ""
    try:
        encrypted = encrypt_secret(api_key)
    except SecretEncryptionError as exc:
        raise fail(500, "SETTINGS_SAVE_FAILED", str(exc)) from exc

    # Empty key must not go through mask_secret (it returns "••••" and looks set).
    key_mask = mask_secret(api_key) if api_key else ""

    base_url: str | None = None
    if provider == "ollama":
        if payload.base_url and payload.base_url.strip():
            base_url = normalize_base_url(payload.base_url)
        # else leave NULL so env/default resolution still applies under Docker
    elif payload.base_url:
        raise fail(
            422,
            "LLM_PROVIDER_ERROR",
            "baseUrl is only supported for the Ollama provider.",
            provider=provider,
        )

    config = db.scalar(
        select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == provider)
    )
    if config is None:
        config = LlmProviderConfigModel(
            provider=provider,
            encrypted_api_key=encrypted,
            key_mask=key_mask,
            base_url=base_url,
        )
        db.add(config)
    else:
        config.encrypted_api_key = encrypted
        config.key_mask = key_mask
        config.is_enabled = True
        if provider == "ollama":
            # Only overwrite when the client sent a value (including clearing via "").
            if payload.base_url is not None:
                config.base_url = base_url
        else:
            config.base_url = None
    config.default_model = payload.default_model or default_model_for(provider)
    if payload.available_models is not None:
        config.available_models, config.models_updated_at = (
            payload.available_models,
            datetime.utcnow(),
        )
    config.updated_at = datetime.utcnow()
    app_settings = db.get(AppSettingsModel, "local-settings")
    should_set_default = (
        not has_configured_default_provider(app_settings)
        or effective_default_provider(app_settings) == provider
    )
    if should_set_default:
        if app_settings is None:
            app_settings = AppSettingsModel(id="local-settings", default_provider=provider)
            db.add(app_settings)
        app_settings.default_provider = provider
        app_settings.default_model = config.default_model
        app_settings.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    if payload.test_after_save:
        await test_llm_provider(
            provider,
            ProviderTestRequest(model=config.default_model, baseUrl=config.base_url),
            db,
        )
        db.refresh(config)
    return public_provider_config(provider, config)


@router.delete("/api/settings/llm-providers/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_provider(provider: str, db: Session = Depends(get_db)) -> None:
    config = db.scalar(
        select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == provider)
    )
    if config:
        db.delete(config)
        app_settings = db.get(AppSettingsModel, "local-settings")
        if app_settings and app_settings.default_provider == provider:
            app_settings.default_provider, app_settings.default_model = None, None
        if app_settings:
            for task in LLM_TASKS:
                if getattr(app_settings, f"{task}_provider", None) == provider:
                    setattr(app_settings, f"{task}_provider", None)
                    setattr(app_settings, f"{task}_model", None)
        db.commit()


@router.post(
    "/api/settings/llm-providers/{provider}/default-model", response_model=ProviderPublicConfig
)
async def update_llm_provider_model(
    provider: str, payload: ProviderModelUpdateInput, db: Session = Depends(get_db)
) -> ProviderPublicConfig:
    if provider not in SUPPORTED_PROVIDERS:
        raise fail(422, "LLM_PROVIDER_ERROR", "Unsupported LLM provider.")
    config = db.scalar(
        select(LlmProviderConfigModel).where(
            LlmProviderConfigModel.provider == provider, LlmProviderConfigModel.is_enabled.is_(True)
        )
    )
    if config is None:
        raise fail(
            400,
            "LLM_PROVIDER_NOT_CONFIGURED",
            "No API key configured for selected provider.",
            provider=provider,
        )
    config.default_model = payload.default_model
    if payload.available_models is not None:
        config.available_models = payload.available_models
        config.models_updated_at = datetime.utcnow()
    config.updated_at = datetime.utcnow()
    app_settings = db.get(AppSettingsModel, "local-settings")
    if effective_default_provider(app_settings) == provider:
        if app_settings is None:
            app_settings = AppSettingsModel(id="local-settings", default_provider=provider)
            db.add(app_settings)
        app_settings.default_provider = provider
        app_settings.default_model = payload.default_model
        app_settings.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    return public_provider_config(provider, config)


@router.post("/api/settings/llm-providers/{provider}/test", response_model=ProviderTestResponse)
async def test_llm_provider(
    provider: str, payload: ProviderTestRequest, db: Session = Depends(get_db)
) -> ProviderTestResponse:
    if provider not in SUPPORTED_PROVIDERS:
        raise fail(422, "LLM_PROVIDER_ERROR", "Unsupported LLM provider.")
    provider_name = cast(ProviderName, provider)
    config = db.scalar(
        select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == provider)
    )
    api_key = payload.api_key
    if not api_key:
        if config is None:
            if provider not in KEYLESS_PROVIDERS:
                raise fail(
                    400,
                    "LLM_PROVIDER_NOT_CONFIGURED",
                    "No API key configured for selected provider.",
                    provider=provider,
                )
            api_key = ""
        else:
            try:
                api_key = decrypt_secret(config.encrypted_api_key)
            except SecretEncryptionError as exc:
                raise fail(500, "SETTINGS_SAVE_FAILED", str(exc)) from exc
    model = (
        payload.model or (config.default_model if config else None) or default_model_for(provider)
    )
    base_url = _resolve_request_base_url(
        provider, payload.base_url, config.base_url if config else None
    )
    started = time.perf_counter()
    try:
        result = await get_llm_provider(provider, base_url=base_url).test_connection(api_key, model)
        latency = int((time.perf_counter() - started) * 1000)
        if config:
            config.last_test_status, config.last_test_error, config.last_tested_at = (
                "success",
                None,
                datetime.utcnow(),
            )
            db.commit()
        return ProviderTestResponse(
            provider=provider_name,
            model=model,
            status="success",
            latencyMs=latency,
            message="Connection successful",
            rawTextPreview=str(result.get("rawTextPreview", "ok"))[:100],
        )
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        message = str(exc)[:500]
        if config:
            config.last_test_status, config.last_test_error, config.last_tested_at = (
                "failed",
                message,
                datetime.utcnow(),
            )
            db.commit()
        return ProviderTestResponse(
            provider=provider_name,
            model=model,
            status="failed",
            latencyMs=latency,
            message="Connection failed",
            errorCode="LLM_CONNECTION_TEST_FAILED",
            details=message,
        )


async def load_provider_models(
    provider: str,
    api_key: str | None,
    refresh: bool,
    db: Session,
    base_url: str | None = None,
) -> dict[str, object]:
    if provider not in SUPPORTED_PROVIDERS:
        raise fail(422, "LLM_PROVIDER_ERROR", "Unsupported LLM provider.")
    supplied_api_key = api_key is not None
    config = db.scalar(
        select(LlmProviderConfigModel).where(
            LlmProviderConfigModel.provider == provider, LlmProviderConfigModel.is_enabled.is_(True)
        )
    )
    if not api_key and config and config.available_models and not refresh:
        return {"provider": provider, "models": config.available_models}
    if not api_key:
        if config is None:
            if provider not in KEYLESS_PROVIDERS:
                raise fail(
                    400,
                    "LLM_PROVIDER_NOT_CONFIGURED",
                    "Enter or save an API key before loading models.",
                    provider=provider,
                )
            api_key = ""
        else:
            try:
                api_key = decrypt_secret(config.encrypted_api_key)
            except SecretEncryptionError as exc:
                raise fail(500, "SETTINGS_SAVE_FAILED", str(exc)) from exc
    resolved_base_url = _resolve_request_base_url(
        provider, base_url, config.base_url if config else None
    )
    try:
        models = await get_llm_provider(provider, base_url=resolved_base_url).list_models(api_key)
        if config and not supplied_api_key:
            config.available_models, config.models_updated_at = models, datetime.utcnow()
            db.commit()
        return {"provider": provider, "models": models}
    except Exception as exc:
        raise fail(
            502,
            "LLM_PROVIDER_ERROR",
            "Could not load models for this provider.",
            provider=provider,
            reason=str(exc)[:300],
        ) from exc


@router.get("/api/settings/llm-providers/{provider}/models")
async def list_saved_provider_models(
    provider: str, db: Session = Depends(get_db)
) -> dict[str, object]:
    return await load_provider_models(provider, None, False, db)


@router.post("/api/settings/llm-providers/{provider}/models")
async def list_provider_models(
    provider: str, payload: ProviderModelsRequest, db: Session = Depends(get_db)
) -> dict[str, object]:
    return await load_provider_models(
        provider, payload.api_key, payload.refresh, db, base_url=payload.base_url
    )


@router.post("/api/settings/default-llm", response_model=ProviderSettingsResponse)
async def set_default_llm(
    payload: SetDefaultLlmRequest, db: Session = Depends(get_db)
) -> ProviderSettingsResponse:
    config = db.scalar(
        select(LlmProviderConfigModel).where(
            LlmProviderConfigModel.provider == payload.provider,
            LlmProviderConfigModel.is_enabled.is_(True),
        )
    )
    if config is None:
        raise fail(
            400,
            "LLM_PROVIDER_NOT_CONFIGURED",
            "No API key configured for selected provider.",
            provider=payload.provider,
        )
    app_settings = db.get(AppSettingsModel, "local-settings") or AppSettingsModel(
        id="local-settings"
    )
    if not db.get(AppSettingsModel, "local-settings"):
        db.add(app_settings)
    app_settings.default_provider, app_settings.default_model, app_settings.updated_at = (
        payload.provider,
        payload.model,
        datetime.utcnow(),
    )
    db.commit()
    return await get_llm_providers(db)


@router.post("/api/settings/task-llm", response_model=ProviderSettingsResponse)
async def set_task_llm(
    payload: SetTaskLlmRequest, db: Session = Depends(get_db)
) -> ProviderSettingsResponse:
    config = db.scalar(
        select(LlmProviderConfigModel).where(
            LlmProviderConfigModel.provider == payload.provider,
            LlmProviderConfigModel.is_enabled.is_(True),
        )
    )
    if config is None:
        raise fail(
            400,
            "LLM_PROVIDER_NOT_CONFIGURED",
            "No API key configured for selected provider.",
            provider=payload.provider,
            task=payload.task,
        )
    app_settings = db.get(AppSettingsModel, "local-settings") or AppSettingsModel(
        id="local-settings"
    )
    if not db.get(AppSettingsModel, "local-settings"):
        db.add(app_settings)
    setattr(app_settings, f"{payload.task}_provider", payload.provider)
    setattr(app_settings, f"{payload.task}_model", payload.model)
    app_settings.updated_at = datetime.utcnow()
    db.commit()
    return await get_llm_providers(db)


@router.delete("/api/settings/task-llm/{task}", response_model=ProviderSettingsResponse)
async def clear_task_llm(task: str, db: Session = Depends(get_db)) -> ProviderSettingsResponse:
    if task not in LLM_TASKS:
        raise fail(422, "LLM_TASK_ERROR", "Unsupported LLM task.", task=task)
    app_settings = db.get(AppSettingsModel, "local-settings")
    if app_settings:
        setattr(app_settings, f"{task}_provider", None)
        setattr(app_settings, f"{task}_model", None)
        app_settings.updated_at = datetime.utcnow()
        db.commit()
    return await get_llm_providers(db)
