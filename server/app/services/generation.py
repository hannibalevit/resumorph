"""LLM-backed content generation.

This is the single module through which every generation task invokes the LLM:
``resolve_task_llm`` (provider/model/key/base_url resolution) and ``get_llm_provider``
(the provider client) are referenced only here for the generation path, so tests stub
the LLM by patching those two names on this module.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.job_service import (
    compose_scan_page_text,
    extract_context_fallback,
    local_field_answer,
)
from app.llm.base import LlmProvider
from app.llm.factory import get_llm_provider
from app.models import GeneratedArtifactModel, JobSessionModel, UserProfileModel
from app.openai_client import ResumeGenerationError
from app.prompt_loader import render_prompt
from app.schemas import (
    CoverLetter,
    FieldAnswerRequest,
    FieldAnswerResponse,
    JobContext,
    PageSnapshot,
    TailoredResume,
)
from app.services.llm_settings import resolve_task_llm
from app.text_utils import extract_contact_info

__all__ = [
    "build_cover_letter",
    "build_resume",
    "cover_letter_plain_text",
    "generate_field_answer_content",
    "preserve_resume_identity",
    "run_job_scan",
]


def preserve_resume_identity(resume: TailoredResume, base_resume: str) -> TailoredResume:
    if not resume.contact_info:
        resume.contact_info = extract_contact_info(base_resume)
    return resume


def _latest_resume_text(db: Session, session_id: str, fallback: str) -> str:
    """Return the most recently generated tailored resume for this job session
    (serialized as JSON), or ``fallback`` (the base resume) if none exists yet."""
    artifact = db.scalars(
        select(GeneratedArtifactModel)
        .where(
            GeneratedArtifactModel.job_session_id == session_id,
            GeneratedArtifactModel.artifact_type == "resume",
        )
        .order_by(GeneratedArtifactModel.created_at.desc())
        .limit(1)
    ).first()
    if artifact and artifact.content_json:
        return TailoredResume.model_validate(artifact.content_json).model_dump_json(by_alias=True)
    return fallback


async def _generate_structured[T: BaseModel](
    provider: LlmProvider,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    schema: dict[str, Any],
    max_tokens: int,
    model_cls: type[T],
) -> T:
    """Call ``generate_json`` and validate the result against ``model_cls``, retrying
    once with a stricter instruction if the LLM's JSON doesn't match the requested
    shape - e.g. a reasoning model emitting a bare array (which parse_json_response
    wraps as ``{"items": [...]}``) instead of the requested object - rather than
    failing the whole generation on the first malformed response."""
    try:
        raw = await provider.generate_json(
            api_key, model, system_prompt, user_prompt, schema, max_tokens
        )
        return model_cls.model_validate(raw)
    except (ValidationError, ValueError):
        retry_prompt = (
            f"{user_prompt}\n\nYour previous response did not match the required JSON "
            "object shape. Return exactly one JSON object with every required field "
            "populated - not a list, and not a partial object."
        )
        raw = await provider.generate_json(
            api_key, model, system_prompt, retry_prompt, schema, max_tokens
        )
        return model_cls.model_validate(raw)


async def run_job_scan(db: Session, snapshot: PageSnapshot) -> tuple[JobContext, str, str]:
    """Extract a ``JobContext`` from a page snapshot, falling back to a heuristic
    extractor if the LLM call fails. Returns the context plus provider/model used."""
    resolved = resolve_task_llm(db, "scan")
    prompt = render_prompt(
        resolved.provider,
        "job_scan",
        job_context_schema=JobContext.model_json_schema(),
        url=snapshot.url,
        title=snapshot.title,
        headings=snapshot.headings[:12],
        page_text=compose_scan_page_text(snapshot),
    )
    try:
        context = JobContext.model_validate(
            await get_llm_provider(resolved.provider, base_url=resolved.base_url).generate_json(
                resolved.api_key,
                resolved.model,
                prompt.system,
                prompt.user,
                JobContext.model_json_schema(),
                3000,
            )
        )
    except Exception as exc:
        context = extract_context_fallback(snapshot)
        context.warnings.append(f"LLM extraction unavailable: {str(exc)[:240]}")
    return context, resolved.provider, resolved.model


async def build_resume(
    profile: UserProfileModel, session: JobSessionModel, db: Session
) -> TailoredResume:
    context = JobContext.model_validate(session.job_context_json)
    resolved = resolve_task_llm(db, "resume")
    prompt = render_prompt(
        resolved.provider,
        "tailored_resume",
        tailored_resume_schema=TailoredResume.model_json_schema(),
        job_context_json=context.model_dump_json(by_alias=True),
        base_resume=profile.base_resume_text,
    )
    try:
        resume = preserve_resume_identity(
            await _generate_structured(
                get_llm_provider(resolved.provider, base_url=resolved.base_url),
                resolved.api_key,
                resolved.model,
                prompt.system,
                prompt.user,
                TailoredResume.model_json_schema(),
                4800,
                TailoredResume,
            ),
            profile.base_resume_text,
        )
    except Exception as exc:
        raise ResumeGenerationError(
            f"{resolved.provider} could not generate a valid structured resume "
            f"with model {resolved.model}: {str(exc)[:300]}"
        ) from exc
    session.llm_provider_used = session.resume_generation_provider = resolved.provider
    session.llm_model_used = session.resume_generation_model = resolved.model
    return resume


async def build_cover_letter(
    profile: UserProfileModel, session: JobSessionModel, db: Session
) -> CoverLetter:
    context = JobContext.model_validate(session.job_context_json)
    role = context.position_title or "this position"
    company = context.company_name or "your organization"
    today = datetime.now()
    today_str = f"{today.day} {today:%B %Y}"
    resolved = resolve_task_llm(db, "resume")
    resume_text = _latest_resume_text(db, session.id, profile.base_resume_text)
    prompt = render_prompt(
        resolved.provider,
        "cover_letter",
        cover_letter_schema=CoverLetter.model_json_schema(),
        role=role,
        company=company,
        today=today_str,
        job_context_json=context.model_dump_json(by_alias=True),
        resume=resume_text,
    )
    try:
        letter = await _generate_structured(
            get_llm_provider(resolved.provider, base_url=resolved.base_url),
            resolved.api_key,
            resolved.model,
            prompt.system,
            prompt.user,
            CoverLetter.model_json_schema(),
            2400,
            CoverLetter,
        )
    except Exception as exc:
        raise ResumeGenerationError(
            f"{resolved.provider} could not generate a valid structured cover letter "
            f"with model {resolved.model}: {str(exc)[:300]}"
        ) from exc
    if not letter.contact_info:
        letter.contact_info = extract_contact_info(profile.base_resume_text)
    if not letter.dateline:
        letter.dateline = today_str
    session.llm_provider_used = session.cover_letter_generation_provider = resolved.provider
    session.llm_model_used = session.cover_letter_generation_model = resolved.model
    return letter


def cover_letter_plain_text(letter: CoverLetter) -> str:
    """Flat-text rendering of the letter, stored in content_json["body"] so the
    sidepanel preview and Copy button keep working (they read contentJson.body)."""
    blocks: list[str] = []
    if letter.dateline:
        blocks.append(letter.dateline)
    if letter.greeting:
        blocks.append(letter.greeting)
    blocks.append(letter.opening)
    blocks.append(letter.profile_intro)
    if letter.achievements:
        blocks.append("\n".join(f"• {item.lead} {item.impact}" for item in letter.achievements))
    if letter.problems:
        blocks.append(letter.problems)
    if letter.closing:
        blocks.append(letter.closing)
    if letter.language_closing:
        blocks.append(letter.language_closing)
    return "\n\n".join(block for block in blocks if block).strip()


async def generate_field_answer_content(
    db: Session,
    session: JobSessionModel,
    profile: UserProfileModel,
    payload: FieldAnswerRequest,
) -> tuple[FieldAnswerResponse, str, str]:
    """Draft an application-field answer, falling back to a local heuristic if the
    LLM call fails. Returns the answer plus provider/model used."""
    context = JobContext.model_validate(session.job_context_json)
    resolved = resolve_task_llm(db, "field_answer")
    question = (
        payload.field.label
        or payload.field.nearby_text
        or payload.field.placeholder
        or "Application question"
    )
    resume_text = _latest_resume_text(db, session.id, profile.base_resume_text)
    prompt = render_prompt(
        resolved.provider,
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
        raw = await get_llm_provider(resolved.provider, base_url=resolved.base_url).generate_json(
            resolved.api_key,
            resolved.model,
            prompt.system,
            prompt.user,
            FieldAnswerResponse.model_json_schema(),
            payload.max_length,
        )
        answer = FieldAnswerResponse.model_validate(raw)
    except Exception as exc:
        answer = local_field_answer(question, profile.base_resume_text, context, payload.max_length)
        answer.warnings.append(f"LLM field answer unavailable: {str(exc)[:240]}")
    answer.needs_user_review = True
    return answer, resolved.provider, resolved.model
