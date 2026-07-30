from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import fail
from app.models import GeneratedArtifactModel, JobSessionModel
from app.schemas import (
    AdminJobDetail,
    AdminJobListResponse,
    AdminStats,
    ArtifactDetail,
    RelatedLink,
)
from app.serializers import admin_item, session_detail

router = APIRouter()


@router.get("/api/admin/job-sessions", response_model=AdminJobListResponse)
async def admin_job_sessions(
    search: str = "",
    provider: str = "",
    status_filter: str = "",
    sort: str = "updated_at_desc",
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
) -> AdminJobListResponse:
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    query = select(JobSessionModel)
    if search.strip():
        term = f"%{search.strip()}%"
        query = query.where(
            (JobSessionModel.company_name.ilike(term))
            | (JobSessionModel.position_title.ilike(term))
        )
    if provider:
        query = query.where(JobSessionModel.llm_provider_used == provider)
    if sort != "updated_at_asc":
        query = query.order_by(JobSessionModel.updated_at.desc())
    else:
        query = query.order_by(JobSessionModel.updated_at.asc())
    sessions = db.scalars(query.offset(offset).limit(limit)).unique().all()
    if status_filter:
        sessions = [
            item
            for item in sessions
            if status_filter in {artifact.artifact_type for artifact in item.artifacts}
            or status_filter == "scanned"
        ]
    total = db.scalar(select(func.count()).select_from(JobSessionModel)) or 0
    return AdminJobListResponse(items=[admin_item(item) for item in sessions], total=total)


@router.get("/api/admin/job-sessions/{job_session_id}", response_model=AdminJobDetail)
async def admin_job_detail(job_session_id: str, db: Session = Depends(get_db)) -> AdminJobDetail:
    session = db.get(JobSessionModel, job_session_id)
    if not session:
        raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    base = session_detail(session).model_dump(by_alias=True)
    links = [
        RelatedLink(
            id=item.id,
            url=item.url,
            normalizedUrl=item.normalized_url,
            linkType=item.link_type,
            title=item.title,
            createdAt=item.created_at,
        )
        for item in session.related_links
    ]
    return AdminJobDetail(**base, relatedLinks=links)


@router.get(
    "/api/admin/job-sessions/{job_session_id}/artifacts", response_model=list[ArtifactDetail]
)
async def admin_artifacts(
    job_session_id: str, db: Session = Depends(get_db)
) -> list[ArtifactDetail]:
    session = db.get(JobSessionModel, job_session_id)
    if not session:
        raise fail(404, "JOB_SESSION_NOT_FOUND", "Job session was not found.")
    return [
        ArtifactDetail(
            id=item.id,
            artifactType=item.artifact_type,
            title=item.title,
            fileName=item.file_name,
            createdAt=item.created_at,
            llmProvider=item.llm_provider,
            llmModel=item.llm_model,
            contentJson=item.content_json,
            mimeType=item.mime_type,
            base64File=item.base64_file,
        )
        for item in sorted(session.artifacts, key=lambda value: value.created_at, reverse=True)
    ]


@router.get("/api/admin/stats", response_model=AdminStats)
async def admin_stats(db: Session = Depends(get_db)) -> AdminStats:
    artifacts = db.scalars(select(GeneratedArtifactModel)).all()
    by_provider = dict.fromkeys(("openai", "gemini", "claude", "ollama"), 0)
    for item in artifacts:
        if item.llm_provider in by_provider:
            by_provider[item.llm_provider] += 1
    return AdminStats(
        totalJobSessions=db.scalar(select(func.count()).select_from(JobSessionModel)) or 0,
        totalGeneratedResumes=sum(item.artifact_type == "resume" for item in artifacts),
        totalGeneratedCoverLetters=sum(item.artifact_type == "cover_letter" for item in artifacts),
        totalGeneratedFieldAnswers=sum(item.artifact_type == "field_answer" for item in artifacts),
        byProvider=by_provider,
    )
