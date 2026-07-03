import base64
from datetime import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import fail
from app.job_service import canonical_job_key, normalize_url
from app.models import GeneratedArtifactModel, JobRelatedLinkModel, JobSessionModel
from app.openai_client import ResumeGenerationError
from app.pdf_generator import (
    PDF_MIME_TYPE,
    PdfGenerationError,
    render_cover_letter_pdf,
    render_resume_pdf,
)
from app.schemas import (
    ArtifactResponse,
    FieldAnswerRequest,
    FieldAnswerResponse,
    GenerationNotes,
    JobContext,
    JobSessionDetail,
    JobSessionSummary,
    PageMatchRequest,
    PageMatchResponse,
    ScanRequest,
)
from app.serializers import base_profile, session_detail, session_summary
from app.services.generation import (
    build_cover_letter,
    build_resume,
    cover_letter_plain_text,
    generate_field_answer_content,
    run_job_scan,
)
from app.text_utils import classify_related_link, safe_filename

router = APIRouter()


@router.post("/api/job-sessions/scan", response_model=JobSessionDetail)
async def scan_job(payload: ScanRequest, db: Session = Depends(get_db)) -> JobSessionDetail:
    snapshot = payload.page_snapshot
    key = canonical_job_key(snapshot)
    context, provider_name, model = await run_job_scan(db, snapshot)
    # The company name is often only in the page header/JSON-LD, not the job body,
    # so the model may return null. Backfill from the extension's own detections.
    detected_company = (snapshot.detected_company or "").strip()
    detected_job_title = (snapshot.detected_job_title or "").strip()
    detected_location = (snapshot.detected_location or "").strip()
    if not (context.company_name or "").strip() and detected_company:
        context.company_name = detected_company
    if not (context.position_title or "").strip() and detected_job_title:
        context.position_title = detected_job_title
    if not (context.location or "").strip() and detected_location:
        context.location = detected_location
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
        db.add(
            JobRelatedLinkModel(
                job_session_id=session.id,
                url=href,
                normalized_url=normalized_link,
                link_type=classify_related_link(href),
                title=link.get("text") or None,
            )
        )
        existing_links.add(normalized_link)
    db.commit()
    db.refresh(session)
    return session_detail(session)


@router.get("/api/job-sessions", response_model=list[JobSessionSummary])
async def list_job_sessions(db: Session = Depends(get_db)) -> list[JobSessionSummary]:
    sessions = (
        db.scalars(select(JobSessionModel).order_by(JobSessionModel.last_used_at.desc()))
        .unique()
        .all()
    )
    return [session_summary(item) for item in sessions]


@router.delete("/api/job-sessions", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_sessions(db: Session = Depends(get_db)) -> None:
    sessions = db.scalars(select(JobSessionModel)).unique().all()
    for session in sessions:
        db.delete(session)
    db.commit()


@router.get("/api/job-sessions/{job_session_id}", response_model=JobSessionDetail)
async def get_job_session(job_session_id: str, db: Session = Depends(get_db)) -> JobSessionDetail:
    session = db.get(JobSessionModel, job_session_id)
    if session is None:
        raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    session.last_used_at = datetime.utcnow()
    db.commit()
    db.refresh(session)
    return session_detail(session)


@router.delete("/api/job-sessions/{job_session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_session(job_session_id: str, db: Session = Depends(get_db)) -> None:
    session = db.get(JobSessionModel, job_session_id)
    if session is None:
        raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    db.delete(session)
    db.commit()


@router.post("/api/job-sessions/match-current-page", response_model=PageMatchResponse)
async def match_current_page(
    payload: PageMatchRequest, db: Session = Depends(get_db)
) -> PageMatchResponse:
    normalized = normalize_url(payload.url)
    session = db.scalar(select(JobSessionModel).where(JobSessionModel.normalized_url == normalized))
    if session:
        return PageMatchResponse(matched=True, jobSessionId=session.id, confidence=1.0)
    # A URL can differ between the job page and application page. Keep title matching conservative.
    if payload.title:
        candidates = db.scalars(
            select(JobSessionModel).where(JobSessionModel.position_title.is_not(None))
        ).all()
        lower_title = payload.title.lower()
        for candidate in candidates:
            if candidate.position_title and candidate.position_title.lower() in lower_title:
                return PageMatchResponse(matched=True, jobSessionId=candidate.id, confidence=0.62)
    return PageMatchResponse(matched=False)


@router.post("/api/job-sessions/{job_session_id}/generate-resume", response_model=ArtifactResponse)
async def generate_session_resume(
    job_session_id: str, db: Session = Depends(get_db)
) -> ArtifactResponse:
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
        warnings.append(
            f"ATS normalization adjusted {total_ats_replacements} "
            "character(s) to plain-ASCII equivalents."
        )
    file_name = f"{
        safe_filename(
            'cv',
            resume.candidate_name,
            context.company_name,
            context.position_title,
            fallback='tailored-resume',
        )
    }.pdf"
    base64_file = base64.b64encode(pdf_bytes).decode("ascii")
    artifact = GeneratedArtifactModel(
        job_session_id=session.id,
        artifact_type="resume",
        title=f"Resume — {context.position_title or 'tailored'}",
        file_name=file_name,
        mime_type=PDF_MIME_TYPE,
        base64_file=base64_file,
        content_json=resume.model_dump(by_alias=True, mode="json"),
        llm_provider=session.resume_generation_provider,
        llm_model=session.resume_generation_model,
        prompt_version="resume-v3",
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return ArtifactResponse(
        artifactId=artifact.id,
        fileName=file_name,
        mimeType=PDF_MIME_TYPE,
        base64=base64_file,
        notes=GenerationNotes(
            keywordsUsed=resume.notes.keywords_used,
            missingRequirements=resume.notes.missing_requirements,
            warnings=warnings,
        ),
    )


@router.post(
    "/api/job-sessions/{job_session_id}/generate-cover-letter", response_model=ArtifactResponse
)
async def generate_cover_letter(
    job_session_id: str, db: Session = Depends(get_db)
) -> ArtifactResponse:
    session = db.get(JobSessionModel, job_session_id)
    profile = base_profile(db)
    if session is None:
        raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    if profile is None or not profile.base_resume_text:
        raise fail(400, "NO_BASE_RESUME", "Base resume is missing.")
    try:
        letter = await build_cover_letter(profile, session, db)
    except ResumeGenerationError as exc:
        raise fail(502, "LLM_GENERATION_FAILED", str(exc)) from exc
    try:
        pdf_bytes, _page_count, ats_replacements = await render_cover_letter_pdf(letter)
    except PdfGenerationError as exc:
        raise fail(502, "PDF_GENERATION_FAILED", str(exc)) from exc
    context = JobContext.model_validate(session.job_context_json)
    role = context.position_title or letter.role_title or "this position"
    company = context.company_name or letter.company or "your organization"
    warnings = ["Review this factual draft before use."]
    total_ats_replacements = sum(ats_replacements.values())
    if total_ats_replacements:
        warnings.append(
            f"ATS normalization adjusted {total_ats_replacements} "
            "character(s) to plain-ASCII equivalents."
        )
    content_json = letter.model_dump(by_alias=True, mode="json")
    content_json["body"] = cover_letter_plain_text(letter)
    file_name = f"{
        safe_filename(
            'cover-letter',
            letter.candidate_name,
            company,
            role,
            fallback='cover-letter',
        )
    }.pdf"
    base64_file = base64.b64encode(pdf_bytes).decode("ascii")
    artifact = GeneratedArtifactModel(
        job_session_id=session.id,
        artifact_type="cover_letter",
        title=f"Cover letter — {role}",
        file_name=file_name,
        mime_type=PDF_MIME_TYPE,
        base64_file=base64_file,
        content_json=content_json,
        llm_provider=session.cover_letter_generation_provider,
        llm_model=session.cover_letter_generation_model,
        prompt_version="cover-letter-v3",
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return ArtifactResponse(
        artifactId=artifact.id,
        fileName=file_name,
        mimeType=PDF_MIME_TYPE,
        base64=base64_file,
        notes=GenerationNotes(warnings=warnings),
    )


@router.post(
    "/api/job-sessions/{job_session_id}/generate-field-answer", response_model=FieldAnswerResponse
)
async def generate_field_answer(
    job_session_id: str, payload: FieldAnswerRequest, db: Session = Depends(get_db)
) -> FieldAnswerResponse:
    session = db.get(JobSessionModel, job_session_id)
    profile = base_profile(db)
    if session is None:
        raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    if profile is None or not profile.base_resume_text:
        raise fail(400, "NO_BASE_RESUME", "Base resume is missing.")
    if payload.field.is_sensitive:
        raise fail(
            400, "SENSITIVE_FIELD", "This sensitive field cannot be filled by the assistant."
        )
    answer, provider_name, model = await generate_field_answer_content(
        db, session, profile, payload
    )
    session.llm_provider_used = provider_name
    session.llm_model_used = model
    artifact = GeneratedArtifactModel(
        job_session_id=session.id,
        artifact_type="field_answer",
        title=payload.field.label or "Application answer",
        content_json=answer.model_dump(by_alias=True),
        llm_provider=provider_name,
        llm_model=model,
        prompt_version="field-answer-v2",
    )
    db.add(artifact)
    db.commit()
    return answer
