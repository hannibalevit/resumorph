"""Pure model → schema mappers shared by the routers.

These functions never touch the LLM or mutate state (apart from ``base_profile``,
a thin read helper); they only translate SQLAlchemy models into the camelCase
Pydantic response schemas.
"""

from typing import cast

from sqlalchemy.orm import Session

from app.llm.claude_cli import is_oauth_token
from app.models import (
    GeneratedArtifactModel,
    JobSessionModel,
    LlmProviderConfigModel,
    UserProfileModel,
)
from app.schemas import (
    AdminJobSessionItem,
    AdminJobStatus,
    ArtifactSummary,
    JobContext,
    JobSessionDetail,
    JobSessionSummary,
    ProviderName,
    ProviderPublicConfig,
)
from app.security import SecretEncryptionError, decrypt_secret


def base_profile(db: Session) -> UserProfileModel | None:
    return db.get(UserProfileModel, "local-user")


def artifact_summary(value: GeneratedArtifactModel) -> ArtifactSummary:
    return ArtifactSummary(
        id=value.id,
        artifactType=value.artifact_type,
        title=value.title,
        fileName=value.file_name,
        createdAt=value.created_at,
        llmProvider=value.llm_provider,
        llmModel=value.llm_model,
    )


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
        artifacts=[
            artifact_summary(item)
            for item in sorted(value.artifacts, key=lambda item: item.created_at, reverse=True)
        ],
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


def admin_item(session: JobSessionModel) -> AdminJobSessionItem:
    types = {artifact.artifact_type for artifact in session.artifacts}
    return AdminJobSessionItem(
        id=session.id,
        title=(
            f"{session.company_name or 'Unknown company'} | "
            f"{session.position_title or 'Untitled role'}"
        ),
        companyName=session.company_name,
        positionTitle=session.position_title,
        location=session.location,
        sourceUrl=session.source_url,
        hostname=session.hostname,
        status=AdminJobStatus(
            scanned=True,
            resumeGenerated="resume" in types,
            coverLetterGenerated="cover_letter" in types,
            fieldAnswersGenerated="field_answer" in types,
        ),
        llmProviderUsed=session.llm_provider_used,
        llmModelUsed=session.llm_model_used,
        createdAt=session.created_at,
        updatedAt=session.updated_at,
    )


def provider_auth_mode(provider: str, config: LlmProviderConfigModel | None) -> str | None:
    """Return "subscription" if the stored Claude secret is an OAuth token,
    "api_key" otherwise. Always None for non-Claude providers or unset secrets.
    """
    if provider != "claude" or config is None:
        return None
    try:
        secret = decrypt_secret(config.encrypted_api_key)
    except SecretEncryptionError:
        return None
    return "subscription" if is_oauth_token(secret) else "api_key"


def public_provider_config(
    provider: str, config: LlmProviderConfigModel | None
) -> ProviderPublicConfig:
    return ProviderPublicConfig(
        provider=cast(ProviderName, provider),
        isEnabled=bool(config and config.is_enabled),
        keyMask=config.key_mask if config else None,
        defaultModel=config.default_model if config else None,
        availableModels=config.available_models or [] if config else [],
        modelsUpdatedAt=config.models_updated_at if config else None,
        lastTestStatus=config.last_test_status if config else "never_tested",
        lastTestError=config.last_test_error if config else None,
        lastTestedAt=config.last_tested_at if config else None,
        authMode=provider_auth_mode(provider, config),
    )
