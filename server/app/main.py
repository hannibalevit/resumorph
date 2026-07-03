import base64
import logging
import re
import time
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import Base, engine, get_db
from app.document_generator import DOCX_MIME_TYPE, create_docx_resume, create_docx_text
from app.file_parser import extract_resume_text_from_upload
from app.job_service import canonical_job_key, compose_scan_page_text, extract_context_fallback, local_field_answer, normalize_url
from app.models import AppSettingsModel, GeneratedArtifactModel, JobRelatedLinkModel, JobSessionModel, LlmProviderConfigModel, UserProfileModel
from app.prompt_loader import render_prompt
from app.security import SecretEncryptionError, decrypt_secret, encrypt_secret, mask_secret
from app.llm.factory import get_llm_provider
from app.openai_client import FieldAnswerGenerationError, JobExtractionError, ResumeGenerationError, extract_job_context, generate_field_answer as llm_generate_field_answer
from app.pdf_generator import PDF_MIME_TYPE, PdfGenerationError, render_resume_pdf
from app.resume_generator import create_tailored_resume
from app.schemas import (
    AdminJobDetail, AdminJobListResponse, AdminJobSessionItem, AdminJobStatus, AdminStats, ApiError, ApiErrorBody, ArtifactDetail, ArtifactResponse, ArtifactSummary, BaseResumeResponse,
    BaseResumeUpload, ExtractResumeTextResponse, FieldAnswerRequest, FieldAnswerResponse,
    GenerateResumeRequest, GenerateResumeResponse, GenerationNotes, JobContext,
    JobPage, JobSessionDetail, JobSessionSummary, LegacyTailoredResume, PageMatchRequest, PageMatchResponse,
    ProviderConfigInput, ProviderModelUpdateInput, ProviderModelsRequest, ProviderPublicConfig, ProviderSettingsResponse, ProviderTestRequest, ProviderTestResponse, RelatedLink, ResumeNotes, ScanRequest, SetDefaultLlmRequest, SetTaskLlmRequest, TailoredResume, TaskLlmSetting,
)
from app.validation import validate_generation_request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(title="Resume Tailor API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^chrome-extension://[a-z]{32}$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
def create_database() -> None:
    Base.metadata.create_all(bind=engine)
    migrations = {
        "job_sessions": {"llm_provider_used": "VARCHAR(32)", "llm_model_used": "VARCHAR(255)", "scan_llm_provider": "VARCHAR(32)", "scan_llm_model": "VARCHAR(255)", "resume_generation_provider": "VARCHAR(32)", "resume_generation_model": "VARCHAR(255)", "cover_letter_generation_provider": "VARCHAR(32)", "cover_letter_generation_model": "VARCHAR(255)"},
        "llm_provider_configs": {"available_models": "JSON", "models_updated_at": "DATETIME"},
        "generated_artifacts": {"llm_provider": "VARCHAR(32)", "llm_model": "VARCHAR(255)", "prompt_version": "VARCHAR(64)", "generation_metadata_json": "JSON"},
        "app_settings": {"scan_provider": "VARCHAR(32)", "scan_model": "VARCHAR(255)", "resume_provider": "VARCHAR(32)", "resume_model": "VARCHAR(255)", "field_answer_provider": "VARCHAR(32)", "field_answer_model": "VARCHAR(255)"},
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in migrations.items():
            existing = {item["name"] for item in inspector.get_columns(table)}
            for column, definition in columns.items():
                if column not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "REQUEST_FAILED", "message": str(exc.detail), "details": {}}},
    )


def fail(status_code: int, code: str, message: str, **details: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message, "details": details}})


def artifact_summary(value: GeneratedArtifactModel) -> ArtifactSummary:
    return ArtifactSummary(id=value.id, artifactType=value.artifact_type, title=value.title, fileName=value.file_name, createdAt=value.created_at, llmProvider=value.llm_provider, llmModel=value.llm_model)


def session_summary(value: JobSessionModel) -> JobSessionSummary:
    return JobSessionSummary(
        id=value.id,
        canonicalJobKey=value.canonical_job_key,
        sourceUrl=value.source_url,
        companyName=value.company_name,
        positionTitle=value.position_title,
        location=value.location,
        extractionConfidence=value.extraction_confidence,
        updatedAt=value.updated_at,
        artifacts=[artifact_summary(item) for item in sorted(value.artifacts, key=lambda item: item.created_at, reverse=True)],
    )


def session_detail(value: JobSessionModel) -> JobSessionDetail:
    summary = session_summary(value).model_dump(by_alias=True)
    return JobSessionDetail(
        **summary,
        normalizedUrl=value.normalized_url,
        hostname=value.hostname,
        jobContext=JobContext.model_validate(value.job_context_json),
        rawPageSnapshot=value.raw_page_snapshot_json,
        createdAt=value.created_at,
        lastUsedAt=value.last_used_at,
    )


def base_profile(db: Session) -> UserProfileModel | None:
    return db.get(UserProfileModel, "local-user")


def default_model_for(provider: str) -> str:
    return {"openai": settings.default_openai_model, "gemini": settings.default_gemini_model, "claude": settings.default_claude_model}[provider]


def public_provider_config(provider: str, config: LlmProviderConfigModel | None) -> ProviderPublicConfig:
    return ProviderPublicConfig(provider=provider, isEnabled=bool(config and config.is_enabled), keyMask=config.key_mask if config else None, defaultModel=config.default_model if config else None, availableModels=config.available_models or [] if config else [], modelsUpdatedAt=config.models_updated_at if config else None, lastTestStatus=config.last_test_status if config else "never_tested", lastTestError=config.last_test_error if config else None, lastTestedAt=config.last_tested_at if config else None)


def effective_default_provider(app_settings: AppSettingsModel | None) -> str:
    return app_settings.default_provider if app_settings and app_settings.default_provider else settings.default_llm_provider


LLM_TASKS = ("scan", "resume", "field_answer")


def task_provider_model(app_settings: AppSettingsModel | None, task: str) -> tuple[str | None, str | None]:
    if app_settings is None:
        return None, None
    return getattr(app_settings, f"{task}_provider", None), getattr(app_settings, f"{task}_model", None)


def resolve_llm(db: Session, provider_name: str, model: str | None = None) -> tuple[str, str, str]:
    config = db.scalar(select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == provider_name, LlmProviderConfigModel.is_enabled.is_(True)))
    if config is None:
        raise fail(400, "LLM_PROVIDER_NOT_CONFIGURED", "No LLM provider configured. Open Settings and add an API key.", provider=provider_name)
    effective_model = model or config.default_model or default_model_for(provider_name)
    if not effective_model:
        raise fail(400, "LLM_MODEL_NOT_AVAILABLE", "No model configured for the selected provider.", provider=provider_name)
    try:
        return provider_name, effective_model, decrypt_secret(config.encrypted_api_key)
    except SecretEncryptionError as exc:
        raise fail(500, "SETTINGS_SAVE_FAILED", str(exc)) from exc


def resolve_default_llm(db: Session) -> tuple[str, str, str]:
    app_settings = db.get(AppSettingsModel, "local-settings")
    provider_name = effective_default_provider(app_settings)
    model = app_settings.default_model if app_settings and app_settings.default_provider == provider_name else None
    return resolve_llm(db, provider_name, model)


def resolve_task_llm(db: Session, task: str) -> tuple[str, str, str]:
    app_settings = db.get(AppSettingsModel, "local-settings")
    task_provider, task_model = task_provider_model(app_settings, task)
    if task_provider:
        config = db.scalar(select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == task_provider, LlmProviderConfigModel.is_enabled.is_(True)))
        if config:
            return resolve_llm(db, task_provider, task_model)
    return resolve_default_llm(db)


def task_setting_response(db: Session, app_settings: AppSettingsModel | None, task: str) -> TaskLlmSetting:
    task_provider, task_model = task_provider_model(app_settings, task)
    is_custom = bool(task_provider)
    if task_provider:
        config = db.scalar(select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == task_provider, LlmProviderConfigModel.is_enabled.is_(True)))
        if config:
            return TaskLlmSetting(task=task, provider=task_provider, model=task_model or config.default_model or default_model_for(task_provider), isCustom=is_custom)
    provider_name = effective_default_provider(app_settings)
    config = db.scalar(select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == provider_name, LlmProviderConfigModel.is_enabled.is_(True)))
    model = (app_settings.default_model if app_settings and app_settings.default_provider == provider_name else None) or (config.default_model if config else None) or default_model_for(provider_name)
    return TaskLlmSetting(task=task, provider=provider_name, model=model, isCustom=False)


def classify_related_link(url: str) -> str:
    lowered = url.lower()
    if "linkedin.com" in lowered: return "linkedin"
    if any(part in lowered for part in ("greenhouse.io", "lever.co", "workday.com", "ashbyhq.com", "smartrecruiters.com")): return "ats"
    if any(part in lowered for part in ("apply", "application", "candidate")): return "application_form"
    return "other"


def extract_contact_info(base_resume: str) -> str | None:
    lines = [re.sub(r"\s+", " ", line).strip() for line in base_resume.splitlines() if line.strip()]
    contact_pattern = re.compile(r"@|https?://|linkedin\.com|github\.com|\+?\d[\d\s().-]{6,}|remote|relocat|[A-Z][a-z]+,\s*[A-Z]{2}\b", re.I)
    candidates = [line for line in lines[1:8] if contact_pattern.search(line)]
    if candidates:
        return " | ".join(candidates[:3])[:500]
    return lines[1][:500] if len(lines) > 1 and len(lines[1]) <= 180 else None


def preserve_resume_identity(resume: TailoredResume, base_resume: str) -> TailoredResume:
    if not resume.contact_info:
        resume.contact_info = extract_contact_info(base_resume)
    return resume


def safe_filename(*parts: str | None, fallback: str) -> str:
    stem = "-".join(part for part in parts if part).lower()
    stem = re.sub(r"[^a-z0-9а-яё]+", "-", stem, flags=re.I).strip("-")
    return (stem or fallback)[:120]


async def build_resume(profile: UserProfileModel, session: JobSessionModel, db: Session) -> TailoredResume:
    context = JobContext.model_validate(session.job_context_json)
    provider_name, model, api_key = resolve_task_llm(db, "resume")
    prompt = render_prompt(
        provider_name,
        "tailored_resume",
        tailored_resume_schema=TailoredResume.model_json_schema(),
        job_context_json=context.model_dump_json(by_alias=True),
        base_resume=profile.base_resume_text,
    )
    try:
        raw = await get_llm_provider(provider_name).generate_json(api_key, model, prompt.system, prompt.user, TailoredResume.model_json_schema(), 4800)
        resume = preserve_resume_identity(TailoredResume.model_validate(raw), profile.base_resume_text)
    except Exception as exc:
        raise ResumeGenerationError(f"{provider_name} could not generate a valid structured resume with model {model}: {str(exc)[:300]}") from exc
    session.llm_provider_used = session.resume_generation_provider = provider_name
    session.llm_model_used = session.resume_generation_model = model
    return resume


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/settings/llm-providers", response_model=ProviderSettingsResponse)
async def get_llm_providers(db: Session = Depends(get_db)) -> ProviderSettingsResponse:
    configs = {item.provider: item for item in db.scalars(select(LlmProviderConfigModel)).all()}
    app_settings = db.get(AppSettingsModel, "local-settings")
    default_provider = effective_default_provider(app_settings)
    default_config = configs.get(default_provider)
    default_model = (app_settings.default_model if app_settings and app_settings.default_provider == default_provider else None) or (default_config.default_model if default_config else None)
    return ProviderSettingsResponse(
        providers=[public_provider_config(name, configs.get(name)) for name in ("openai", "gemini", "claude")],
        defaultProvider=default_provider,
        defaultModel=default_model,
        taskSettings={task: task_setting_response(db, app_settings, task) for task in LLM_TASKS},
    )


@app.post("/api/settings/llm-providers/{provider}", response_model=ProviderPublicConfig)
async def save_llm_provider(provider: str, payload: ProviderConfigInput, db: Session = Depends(get_db)) -> ProviderPublicConfig:
    if provider not in {"openai", "gemini", "claude"}:
        raise fail(422, "LLM_PROVIDER_ERROR", "Unsupported LLM provider.")
    try:
        encrypted = encrypt_secret(payload.api_key)
    except SecretEncryptionError as exc:
        raise fail(500, "SETTINGS_SAVE_FAILED", str(exc)) from exc
    config = db.scalar(select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == provider))
    if config is None:
        config = LlmProviderConfigModel(provider=provider, encrypted_api_key=encrypted, key_mask=mask_secret(payload.api_key))
        db.add(config)
    else:
        config.encrypted_api_key, config.key_mask, config.is_enabled = encrypted, mask_secret(payload.api_key), True
    config.default_model = payload.default_model or default_model_for(provider)
    if payload.available_models is not None:
        config.available_models, config.models_updated_at = payload.available_models, datetime.utcnow()
    config.updated_at = datetime.utcnow()
    app_settings = db.get(AppSettingsModel, "local-settings")
    if effective_default_provider(app_settings) == provider:
        if app_settings is None:
            app_settings = AppSettingsModel(id="local-settings", default_provider=provider)
            db.add(app_settings)
        app_settings.default_provider = provider
        app_settings.default_model = config.default_model
        app_settings.updated_at = datetime.utcnow()
    db.commit(); db.refresh(config)
    if payload.test_after_save:
        await test_llm_provider(provider, ProviderTestRequest(model=config.default_model), db)
        db.refresh(config)
    return public_provider_config(provider, config)


@app.delete("/api/settings/llm-providers/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_provider(provider: str, db: Session = Depends(get_db)) -> None:
    config = db.scalar(select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == provider))
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


@app.post("/api/settings/llm-providers/{provider}/default-model", response_model=ProviderPublicConfig)
async def update_llm_provider_model(provider: str, payload: ProviderModelUpdateInput, db: Session = Depends(get_db)) -> ProviderPublicConfig:
    if provider not in {"openai", "gemini", "claude"}:
        raise fail(422, "LLM_PROVIDER_ERROR", "Unsupported LLM provider.")
    config = db.scalar(select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == provider, LlmProviderConfigModel.is_enabled.is_(True)))
    if config is None:
        raise fail(400, "LLM_PROVIDER_NOT_CONFIGURED", "No API key configured for selected provider.", provider=provider)
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


@app.post("/api/settings/llm-providers/{provider}/test", response_model=ProviderTestResponse)
async def test_llm_provider(provider: str, payload: ProviderTestRequest, db: Session = Depends(get_db)) -> ProviderTestResponse:
    if provider not in {"openai", "gemini", "claude"}:
        raise fail(422, "LLM_PROVIDER_ERROR", "Unsupported LLM provider.")
    config = db.scalar(select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == provider))
    api_key = payload.api_key
    if not api_key:
        if config is None:
            raise fail(400, "LLM_PROVIDER_NOT_CONFIGURED", "No API key configured for selected provider.", provider=provider)
        try:
            api_key = decrypt_secret(config.encrypted_api_key)
        except SecretEncryptionError as exc:
            raise fail(500, "SETTINGS_SAVE_FAILED", str(exc)) from exc
    model = payload.model or (config.default_model if config else None) or default_model_for(provider)
    started = time.perf_counter()
    try:
        result = await get_llm_provider(provider).test_connection(api_key, model)
        latency = int((time.perf_counter() - started) * 1000)
        if config:
            config.last_test_status, config.last_test_error, config.last_tested_at = "success", None, datetime.utcnow(); db.commit()
        return ProviderTestResponse(provider=provider, model=model, status="success", latencyMs=latency, message="Connection successful", rawTextPreview=str(result.get("rawTextPreview", "ok"))[:100])
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        message = str(exc)[:500]
        if config:
            config.last_test_status, config.last_test_error, config.last_tested_at = "failed", message, datetime.utcnow(); db.commit()
        return ProviderTestResponse(provider=provider, model=model, status="failed", latencyMs=latency, message="Connection failed", errorCode="LLM_CONNECTION_TEST_FAILED", details=message)


async def load_provider_models(provider: str, api_key: str | None, refresh: bool, db: Session) -> dict[str, object]:
    if provider not in {"openai", "gemini", "claude"}:
        raise fail(422, "LLM_PROVIDER_ERROR", "Unsupported LLM provider.")
    supplied_api_key = api_key is not None
    config = db.scalar(select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == provider, LlmProviderConfigModel.is_enabled.is_(True)))
    if not api_key and config and config.available_models and not refresh:
        return {"provider": provider, "models": config.available_models}
    if not api_key:
        if config is None:
            raise fail(400, "LLM_PROVIDER_NOT_CONFIGURED", "Enter or save an API key before loading models.", provider=provider)
        try:
            api_key = decrypt_secret(config.encrypted_api_key)
        except SecretEncryptionError as exc:
            raise fail(500, "SETTINGS_SAVE_FAILED", str(exc)) from exc
    try:
        models = await get_llm_provider(provider).list_models(api_key)
        if config and not supplied_api_key:
            config.available_models, config.models_updated_at = models, datetime.utcnow()
            db.commit()
        return {"provider": provider, "models": models}
    except Exception as exc:
        raise fail(502, "LLM_PROVIDER_ERROR", "Could not load models for this provider.", provider=provider, reason=str(exc)[:300]) from exc


@app.get("/api/settings/llm-providers/{provider}/models")
async def list_saved_provider_models(provider: str, db: Session = Depends(get_db)) -> dict[str, object]:
    return await load_provider_models(provider, None, False, db)


@app.post("/api/settings/llm-providers/{provider}/models")
async def list_provider_models(provider: str, payload: ProviderModelsRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    return await load_provider_models(provider, payload.api_key, payload.refresh, db)


@app.post("/api/settings/default-llm", response_model=ProviderSettingsResponse)
async def set_default_llm(payload: SetDefaultLlmRequest, db: Session = Depends(get_db)) -> ProviderSettingsResponse:
    config = db.scalar(select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == payload.provider, LlmProviderConfigModel.is_enabled.is_(True)))
    if config is None:
        raise fail(400, "LLM_PROVIDER_NOT_CONFIGURED", "No API key configured for selected provider.", provider=payload.provider)
    app_settings = db.get(AppSettingsModel, "local-settings") or AppSettingsModel(id="local-settings")
    if not db.get(AppSettingsModel, "local-settings"): db.add(app_settings)
    app_settings.default_provider, app_settings.default_model, app_settings.updated_at = payload.provider, payload.model, datetime.utcnow()
    db.commit()
    return await get_llm_providers(db)


@app.post("/api/settings/task-llm", response_model=ProviderSettingsResponse)
async def set_task_llm(payload: SetTaskLlmRequest, db: Session = Depends(get_db)) -> ProviderSettingsResponse:
    config = db.scalar(select(LlmProviderConfigModel).where(LlmProviderConfigModel.provider == payload.provider, LlmProviderConfigModel.is_enabled.is_(True)))
    if config is None:
        raise fail(400, "LLM_PROVIDER_NOT_CONFIGURED", "No API key configured for selected provider.", provider=payload.provider, task=payload.task)
    app_settings = db.get(AppSettingsModel, "local-settings") or AppSettingsModel(id="local-settings")
    if not db.get(AppSettingsModel, "local-settings"):
        db.add(app_settings)
    setattr(app_settings, f"{payload.task}_provider", payload.provider)
    setattr(app_settings, f"{payload.task}_model", payload.model)
    app_settings.updated_at = datetime.utcnow()
    db.commit()
    return await get_llm_providers(db)


@app.delete("/api/settings/task-llm/{task}", response_model=ProviderSettingsResponse)
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


@app.post("/api/extract-resume-text", response_model=ExtractResumeTextResponse)
async def extract_resume_text(file: UploadFile = File(...)) -> ExtractResumeTextResponse:
    text = await extract_resume_text_from_upload(file)
    logger.info("Extracted resume text. text_chars=%s", len(text))
    return ExtractResumeTextResponse(text=text)


@app.post("/api/profile/base-resume", response_model=BaseResumeResponse)
async def save_base_resume(payload: BaseResumeUpload, db: Session = Depends(get_db)) -> BaseResumeResponse:
    profile = base_profile(db)
    if profile is None:
        profile = UserProfileModel(id="local-user", base_resume_text=payload.text)
        db.add(profile)
    else:
        profile.base_resume_text = payload.text
        profile.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(profile)
    return BaseResumeResponse(text=profile.base_resume_text, updatedAt=profile.updated_at)


@app.get("/api/profile/base-resume", response_model=BaseResumeResponse)
async def get_base_resume(db: Session = Depends(get_db)) -> BaseResumeResponse:
    profile = base_profile(db)
    if profile is None or not profile.base_resume_text:
        raise fail(404, "NO_BASE_RESUME", "Base resume is missing.")
    return BaseResumeResponse(text=profile.base_resume_text, updatedAt=profile.updated_at)


@app.delete("/api/profile/base-resume", status_code=status.HTTP_204_NO_CONTENT)
async def delete_base_resume(db: Session = Depends(get_db)) -> None:
    profile = base_profile(db)
    if profile is not None:
        db.delete(profile)
        db.commit()


@app.post("/api/job-sessions/scan", response_model=JobSessionDetail)
async def scan_job(payload: ScanRequest, db: Session = Depends(get_db)) -> JobSessionDetail:
    snapshot = payload.page_snapshot
    key = canonical_job_key(snapshot)
    provider_name, model, api_key = resolve_task_llm(db, "scan")
    prompt = render_prompt(
        provider_name,
        "job_scan",
        job_context_schema=JobContext.model_json_schema(),
        url=snapshot.url,
        title=snapshot.title,
        headings=snapshot.headings[:12],
        page_text=compose_scan_page_text(snapshot),
    )
    try:
        context = JobContext.model_validate(await get_llm_provider(provider_name).generate_json(api_key, model, prompt.system, prompt.user, JobContext.model_json_schema(), 3000))
    except Exception as exc:
        context = extract_context_fallback(snapshot)
        context.warnings.append(f"LLM extraction unavailable: {str(exc)[:240]}")
    session = db.scalar(select(JobSessionModel).where(JobSessionModel.canonical_job_key == key))
    snapshot_json = snapshot.model_dump(by_alias=True, mode="json")
    if session is None:
        session = JobSessionModel(
            canonical_job_key=key,
            source_url=snapshot.url,
            normalized_url=normalize_url(snapshot.normalized_url or snapshot.url),
            hostname=snapshot.hostname,
        )
        db.add(session)
    session.source_url = snapshot.url
    session.normalized_url = normalize_url(snapshot.normalized_url or snapshot.url)
    session.hostname = snapshot.hostname
    session.company_name = context.company_name
    session.position_title = context.position_title
    session.location = context.location
    session.job_context_json = context.model_dump(by_alias=True, mode="json")
    session.raw_page_snapshot_json = snapshot_json
    session.extraction_confidence = context.confidence
    session.llm_provider_used = session.scan_llm_provider = provider_name
    session.llm_model_used = session.scan_llm_model = model
    session.last_used_at = datetime.utcnow()
    db.flush()
    existing_links = {item.normalized_url for item in session.related_links}
    for link in snapshot.links[:100]:
        href = link.get("href")
        if not href or not href.startswith(("http://", "https://")):
            continue
        normalized_link = normalize_url(href)
        if normalized_link in existing_links:
            continue
        db.add(JobRelatedLinkModel(job_session_id=session.id, url=href, normalized_url=normalized_link, link_type=classify_related_link(href), title=link.get("text") or None))
        existing_links.add(normalized_link)
    db.commit()
    db.refresh(session)
    return session_detail(session)


@app.get("/api/job-sessions", response_model=list[JobSessionSummary])
async def list_job_sessions(db: Session = Depends(get_db)) -> list[JobSessionSummary]:
    sessions = db.scalars(select(JobSessionModel).order_by(JobSessionModel.last_used_at.desc())).unique().all()
    return [session_summary(item) for item in sessions]


@app.delete("/api/job-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_sessions(db: Session = Depends(get_db)) -> None:
    sessions = db.scalars(select(JobSessionModel)).unique().all()
    for session in sessions:
        db.delete(session)
    db.commit()


@app.get("/api/job-sessions/{job_session_id}", response_model=JobSessionDetail)
async def get_job_session(job_session_id: str, db: Session = Depends(get_db)) -> JobSessionDetail:
    session = db.get(JobSessionModel, job_session_id)
    if session is None:
        raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    session.last_used_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session_detail(session)


@app.delete("/api/job-sessions/{job_session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_session(job_session_id: str, db: Session = Depends(get_db)) -> None:
    session = db.get(JobSessionModel, job_session_id)
    if session is None:
        raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    db.delete(session)
    db.commit()


@app.post("/api/job-sessions/match-current-page", response_model=PageMatchResponse)
async def match_current_page(payload: PageMatchRequest, db: Session = Depends(get_db)) -> PageMatchResponse:
    normalized = normalize_url(payload.url)
    session = db.scalar(select(JobSessionModel).where(JobSessionModel.normalized_url == normalized))
    if session:
        return PageMatchResponse(matched=True, jobSessionId=session.id, confidence=1.0)
    # A URL can differ between the job page and application page. Keep title matching conservative.
    if payload.title:
        candidates = db.scalars(select(JobSessionModel).where(JobSessionModel.position_title.is_not(None))).all()
        lower_title = payload.title.lower()
        for candidate in candidates:
            if candidate.position_title and candidate.position_title.lower() in lower_title:
                return PageMatchResponse(matched=True, jobSessionId=candidate.id, confidence=0.62)
    return PageMatchResponse(matched=False)


@app.post("/api/job-sessions/{job_session_id}/generate-resume", response_model=ArtifactResponse)
async def generate_session_resume(job_session_id: str, db: Session = Depends(get_db)) -> ArtifactResponse:
    session = db.get(JobSessionModel, job_session_id)
    profile = base_profile(db)
    if session is None:
        raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    if profile is None or not profile.base_resume_text:
        raise fail(400, "NO_BASE_RESUME", "Base resume is missing.")
    try:
        resume = await build_resume(profile, session, db)
    except ResumeGenerationError as exc:
        raise fail(502, "LLM_GENERATION_FAILED", str(exc)) from exc
    try:
        pdf_bytes, _page_count, ats_replacements = await render_resume_pdf(resume)
    except PdfGenerationError as exc:
        raise fail(502, "PDF_GENERATION_FAILED", str(exc)) from exc
    context = JobContext.model_validate(session.job_context_json)
    warnings: list[str] = []
    total_ats_replacements = sum(ats_replacements.values())
    if total_ats_replacements:
        warnings.append(f"ATS normalization adjusted {total_ats_replacements} character(s) to plain-ASCII equivalents.")
    artifact = GeneratedArtifactModel(
        job_session_id=session.id,
        artifact_type="resume",
        title=f"Resume — {context.position_title or 'tailored'}",
        file_name=f"{safe_filename(context.company_name, context.position_title, 'resume', fallback='tailored-resume')}.pdf",
        mime_type=PDF_MIME_TYPE,
        base64_file=base64.b64encode(pdf_bytes).decode("ascii"),
        content_json=resume.model_dump(by_alias=True, mode="json"),
        llm_provider=session.resume_generation_provider,
        llm_model=session.resume_generation_model,
        prompt_version="resume-v3",
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return ArtifactResponse(artifactId=artifact.id, fileName=artifact.file_name, mimeType=PDF_MIME_TYPE, base64=artifact.base64_file, notes=GenerationNotes(keywordsUsed=resume.notes.keywords_used, missingRequirements=resume.notes.missing_requirements, warnings=warnings))


@app.post("/api/job-sessions/{job_session_id}/generate-cover-letter", response_model=ArtifactResponse)
async def generate_cover_letter(job_session_id: str, db: Session = Depends(get_db)) -> ArtifactResponse:
    session = db.get(JobSessionModel, job_session_id)
    profile = base_profile(db)
    if session is None:
        raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    if profile is None or not profile.base_resume_text:
        raise fail(400, "NO_BASE_RESUME", "Base resume is missing.")
    context = JobContext.model_validate(session.job_context_json)
    role = context.position_title or "this position"
    company = context.company_name or "your organization"
    provider_name, model, api_key = resolve_task_llm(db, "resume")
    prompt = render_prompt(
        provider_name,
        "cover_letter",
        role=role,
        company=company,
        job_context_json=context.model_dump_json(by_alias=True),
        base_resume=profile.base_resume_text,
    )
    body = await get_llm_provider(provider_name).generate_text(api_key, model, prompt.system, prompt.user, 1800)
    session.llm_provider_used = session.cover_letter_generation_provider = provider_name
    session.llm_model_used = session.cover_letter_generation_model = model
    content = create_docx_text(f"Cover Letter — {role}", body)
    artifact = GeneratedArtifactModel(job_session_id=session.id, artifact_type="cover_letter", title=f"Cover letter — {role}", file_name=f"{safe_filename(company, role, 'cover-letter', fallback='cover-letter')}.docx", mime_type=DOCX_MIME_TYPE, base64_file=base64.b64encode(content).decode("ascii"), content_json={"body": body}, llm_provider=provider_name, llm_model=model, prompt_version="cover-letter-v2")
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return ArtifactResponse(artifactId=artifact.id, fileName=artifact.file_name, mimeType=DOCX_MIME_TYPE, base64=artifact.base64_file, notes=GenerationNotes(warnings=["Review this factual draft before use."]))


@app.post("/api/job-sessions/{job_session_id}/generate-field-answer", response_model=FieldAnswerResponse)
async def generate_field_answer(job_session_id: str, payload: FieldAnswerRequest, db: Session = Depends(get_db)) -> FieldAnswerResponse:
    session = db.get(JobSessionModel, job_session_id)
    profile = base_profile(db)
    if session is None:
        raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    if profile is None or not profile.base_resume_text:
        raise fail(400, "NO_BASE_RESUME", "Base resume is missing.")
    if payload.field.is_sensitive:
        raise fail(400, "SENSITIVE_FIELD", "This sensitive field cannot be filled by the assistant.")
    context = JobContext.model_validate(session.job_context_json)
    provider_name, model, api_key = resolve_task_llm(db, "field_answer")
    question = payload.field.label or payload.field.nearby_text or payload.field.placeholder or "Application question"
    resume_artifact = db.scalars(
        select(GeneratedArtifactModel)
        .where(
            GeneratedArtifactModel.job_session_id == job_session_id,
            GeneratedArtifactModel.artifact_type == "resume",
        )
        .order_by(GeneratedArtifactModel.created_at.desc())
        .limit(1)
    ).first()
    resume_text = (
        TailoredResume.model_validate(resume_artifact.content_json).model_dump_json(by_alias=True)
        if resume_artifact and resume_artifact.content_json
        else profile.base_resume_text
    )
    prompt = render_prompt(
        provider_name,
        "field_answer",
        question=question,
        max_length=payload.max_length,
        field_answer_schema=FieldAnswerResponse.model_json_schema(),
        field_type=payload.field.type or payload.field.tag_name,
        placeholder=payload.field.placeholder or "(none)",
        nearby_text=payload.field.nearby_text or "(none)",
        current_value=payload.field.current_value or "(empty)",
        job_context_json=context.model_dump_json(by_alias=True),
        resume=resume_text,
    )
    try:
        raw = await get_llm_provider(provider_name).generate_json(api_key, model, prompt.system, prompt.user, FieldAnswerResponse.model_json_schema(), payload.max_length)
        answer = FieldAnswerResponse.model_validate(raw)
    except Exception as exc:
        answer = local_field_answer(question, profile.base_resume_text, context, payload.max_length)
        answer.warnings.append(f"LLM field answer unavailable: {str(exc)[:240]}")
    answer.needs_user_review = True
    session.llm_provider_used = provider_name; session.llm_model_used = model
    artifact = GeneratedArtifactModel(job_session_id=session.id, artifact_type="field_answer", title=payload.field.label or "Application answer", content_json=answer.model_dump(by_alias=True), llm_provider=provider_name, llm_model=model, prompt_version="field-answer-v2")
    db.add(artifact)
    db.commit()
    return answer


def admin_item(session: JobSessionModel) -> AdminJobSessionItem:
    types = {artifact.artifact_type for artifact in session.artifacts}
    return AdminJobSessionItem(id=session.id, title=f"{session.company_name or 'Unknown company'} | {session.position_title or 'Untitled role'}", companyName=session.company_name, positionTitle=session.position_title, location=session.location, sourceUrl=session.source_url, hostname=session.hostname, status=AdminJobStatus(scanned=True, resumeGenerated="resume" in types, coverLetterGenerated="cover_letter" in types, fieldAnswersGenerated="field_answer" in types), llmProviderUsed=session.llm_provider_used, llmModelUsed=session.llm_model_used, createdAt=session.created_at, updatedAt=session.updated_at)


@app.get("/api/admin/job-sessions", response_model=AdminJobListResponse)
async def admin_job_sessions(search: str = "", provider: str = "", status_filter: str = "", sort: str = "updated_at_desc", limit: int = 30, offset: int = 0, db: Session = Depends(get_db)) -> AdminJobListResponse:
    limit = max(1, min(limit, 100)); offset = max(0, offset)
    query = select(JobSessionModel)
    if search.strip():
        term = f"%{search.strip()}%"; query = query.where((JobSessionModel.company_name.ilike(term)) | (JobSessionModel.position_title.ilike(term)))
    if provider: query = query.where(JobSessionModel.llm_provider_used == provider)
    if sort != "updated_at_asc": query = query.order_by(JobSessionModel.updated_at.desc())
    else: query = query.order_by(JobSessionModel.updated_at.asc())
    sessions = db.scalars(query.offset(offset).limit(limit)).unique().all()
    if status_filter:
        sessions = [item for item in sessions if status_filter in {artifact.artifact_type for artifact in item.artifacts} or status_filter == "scanned"]
    total = db.scalar(select(func.count()).select_from(JobSessionModel)) or 0
    return AdminJobListResponse(items=[admin_item(item) for item in sessions], total=total)


@app.get("/api/admin/job-sessions/{job_session_id}", response_model=AdminJobDetail)
async def admin_job_detail(job_session_id: str, db: Session = Depends(get_db)) -> AdminJobDetail:
    session = db.get(JobSessionModel, job_session_id)
    if not session: raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    base = session_detail(session).model_dump(by_alias=True)
    links = [RelatedLink(id=item.id, url=item.url, normalizedUrl=item.normalized_url, linkType=item.link_type, title=item.title, createdAt=item.created_at) for item in session.related_links]
    return AdminJobDetail(**base, relatedLinks=links)


@app.get("/api/admin/job-sessions/{job_session_id}/artifacts", response_model=list[ArtifactDetail])
async def admin_artifacts(job_session_id: str, db: Session = Depends(get_db)) -> list[ArtifactDetail]:
    session = db.get(JobSessionModel, job_session_id)
    if not session: raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    return [ArtifactDetail(id=item.id, artifactType=item.artifact_type, title=item.title, fileName=item.file_name, createdAt=item.created_at, llmProvider=item.llm_provider, llmModel=item.llm_model, contentJson=item.content_json, mimeType=item.mime_type, base64File=item.base64_file) for item in sorted(session.artifacts, key=lambda value: value.created_at, reverse=True)]


@app.get("/api/artifacts/{artifact_id}", response_model=ArtifactDetail)
async def get_artifact(artifact_id: str, db: Session = Depends(get_db)) -> ArtifactDetail:
    item = db.get(GeneratedArtifactModel, artifact_id)
    if not item: raise fail(404, "ARTIFACT_NOT_FOUND", "Artifact was not found.")
    return ArtifactDetail(id=item.id, artifactType=item.artifact_type, title=item.title, fileName=item.file_name, createdAt=item.created_at, llmProvider=item.llm_provider, llmModel=item.llm_model, contentJson=item.content_json, mimeType=item.mime_type, base64File=item.base64_file)


@app.delete("/api/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(artifact_id: str, db: Session = Depends(get_db)) -> None:
    item = db.get(GeneratedArtifactModel, artifact_id)
    if not item: raise fail(404, "ARTIFACT_NOT_FOUND", "Artifact was not found.")
    db.delete(item); db.commit()


@app.get("/api/admin/stats", response_model=AdminStats)
async def admin_stats(db: Session = Depends(get_db)) -> AdminStats:
    artifacts = db.scalars(select(GeneratedArtifactModel)).all()
    by_provider = {name: 0 for name in ("openai", "gemini", "claude")}
    for item in artifacts:
        if item.llm_provider in by_provider: by_provider[item.llm_provider] += 1
    return AdminStats(totalJobSessions=db.scalar(select(func.count()).select_from(JobSessionModel)) or 0, totalGeneratedResumes=sum(item.artifact_type == "resume" for item in artifacts), totalGeneratedCoverLetters=sum(item.artifact_type == "cover_letter" for item in artifacts), totalGeneratedFieldAnswers=sum(item.artifact_type == "field_answer" for item in artifacts), byProvider=by_provider)


# Backwards-compatible original endpoint.
@app.post("/api/generate-resume", response_model=GenerateResumeResponse)
async def generate_resume(payload: GenerateResumeRequest) -> GenerateResumeResponse:
    validated_payload = validate_generation_request(payload)
    try:
        tailored_resume = await create_tailored_resume(validated_payload)
        docx_bytes = create_docx_resume(tailored_resume)
    except ResumeGenerationError as exc:
        raise fail(502, "LLM_GENERATION_FAILED", str(exc)) from exc
    return GenerateResumeResponse(fileName="tailored-resume.docx", mimeType=DOCX_MIME_TYPE, base64=base64.b64encode(docx_bytes).decode("ascii"), notes=tailored_resume.notes)
