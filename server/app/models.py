from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.utcnow()


class UserProfileModel(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default="local-user")
    base_resume_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class JobSessionModel(Base):
    __tablename__ = "job_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    canonical_job_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    source_url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text, index=True)
    hostname: Mapped[str] = mapped_column(String(255), default="")
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    position_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_context_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_page_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    llm_conversation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    llm_provider_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_model_used: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scan_llm_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scan_llm_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resume_generation_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resume_generation_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cover_letter_generation_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cover_letter_generation_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    artifacts: Mapped[list["GeneratedArtifactModel"]] = relationship(
        back_populates="job_session", cascade="all, delete-orphan"
    )
    related_links: Mapped[list["JobRelatedLinkModel"]] = relationship(back_populates="job_session", cascade="all, delete-orphan")


class GeneratedArtifactModel(Base):
    __tablename__ = "generated_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_session_id: Mapped[str] = mapped_column(ForeignKey("job_sessions.id"), index=True)
    artifact_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255), default="")
    content_json: Mapped[dict] = mapped_column(JSON, default=dict)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base64_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    generation_metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    job_session: Mapped[JobSessionModel] = relationship(back_populates="artifacts")


class LlmProviderConfigModel(Base):
    __tablename__ = "llm_provider_configs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    key_mask: Mapped[str] = mapped_column(String(64))
    default_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    available_models: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    models_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_enabled: Mapped[bool] = mapped_column(default=True)
    last_test_status: Mapped[str] = mapped_column(String(32), default="never_tested")
    last_test_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class AppSettingsModel(Base):
    __tablename__ = "app_settings"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default="local-settings")
    default_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scan_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scan_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resume_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resume_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_answer_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    field_answer_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class JobRelatedLinkModel(Base):
    __tablename__ = "job_related_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_session_id: Mapped[str] = mapped_column(ForeignKey("job_sessions.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text)
    link_type: Mapped[str] = mapped_column(String(32), default="other")
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    job_session: Mapped[JobSessionModel] = relationship(back_populates="related_links")
