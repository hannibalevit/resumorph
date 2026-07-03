"""LLM-backed content generation.

This is the single module through which every generation task invokes the LLM:
``resolve_task_llm`` (provider/model/key resolution) and ``get_llm_provider`` (the
provider client) are referenced only here for the generation path, so tests stub
the LLM by patching those two names on this module.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.job_service import (
    compose_scan_page_text,
    extract_context_fallback,
    local_field_answer,
)
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


async def run_job_scan(db: Session, snapshot: PageSnapshot) -> tuple[JobContext, str, str]:
    """Extract a ``JobContext`` from a page snapshot, falling back to a heuristic
    extractor if the LLM call fails. Returns the context plus provider/model used."""
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
        context = JobContext.model_validate(
            await get_llm_provider(provider_name).generate_json(
                api_key, model, prompt.system, prompt.user, JobContext.model_json_schema(), 3000
            )
        )
    except Exception as exc:
        context = extract_context_fallback(snapshot)
        context.warnings.append(f"LLM extraction unavailable: {str(exc)[:240]}")
    return context, provider_name, model


async def build_resume(
    profile: UserProfileModel, session: JobSessionModel, db: Session
) -> TailoredResume:
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
        raw = await get_llm_provider(provider_name).generate_json(
            api_key, model, prompt.system, prompt.user, TailoredResume.model_json_schema(), 4800
        )
        resume = preserve_resume_identity(
            TailoredResume.model_validate(raw), profile.base_resume_text
        )
    except Exception as exc:
        raise ResumeGenerationError(
            f"{provider_name} could not generate a valid structured resume "
            f"with model {model}: {str(exc)[:300]}"
        ) from exc
    session.llm_provider_used = session.resume_generation_provider = provider_name
    session.llm_model_used = session.resume_generation_model = model
    return resume


async def build_cover_letter(
    profile: UserProfileModel, session: JobSessionModel, db: Session
) -> CoverLetter:
    context = JobContext.model_validate(session.job_context_json)
    role = context.position_title or "this position"
    company = context.company_name or "your organization"
    today = datetime.now()
    today_str = f"{today.day} {today:%B %Y}"
    provider_name, model, api_key = resolve_task_llm(db, "resume")
    prompt = render_prompt(
        provider_name,
        "cover_letter",
        cover_letter_schema=CoverLetter.model_json_schema(),
        role=role,
        company=company,
        today=today_str,
        job_context_json=context.model_dump_json(by_alias=True),
        base_resume=profile.base_resume_text,
    )
    try:
        raw = await get_llm_provider(provider_name).generate_json(
            api_key, model, prompt.system, prompt.user, CoverLetter.model_json_schema(), 2400
        )
        letter = CoverLetter.model_validate(raw)
    except Exception as exc:
        raise ResumeGenerationError(
            f"{provider_name} could not generate a valid structured cover letter "
            f"with model {model}: {str(exc)[:300]}"
        ) from exc
    if not letter.contact_info:
        letter.contact_info = extract_contact_info(profile.base_resume_text)
    if not letter.dateline:
        letter.dateline = today_str
    session.llm_provider_used = session.cover_letter_generation_provider = provider_name
    session.llm_model_used = session.cover_letter_generation_model = model
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
    provider_name, model, api_key = resolve_task_llm(db, "field_answer")
    question = (
        payload.field.label
        or payload.field.nearby_text
        or payload.field.placeholder
        or "Application question"
    )
    resume_artifact = db.scalars(
        select(GeneratedArtifactModel)
        .where(
            GeneratedArtifactModel.job_session_id == session.id,
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
        raw = await get_llm_provider(provider_name).generate_json(
            api_key,
            model,
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
    return answer, provider_name, model
