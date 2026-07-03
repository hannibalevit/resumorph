import logging
from datetime import datetime

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import fail
from app.file_parser import extract_resume_text_from_upload
from app.models import UserProfileModel
from app.schemas import BaseResumeResponse, BaseResumeUpload, ExtractResumeTextResponse
from app.serializers import base_profile

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/extract-resume-text", response_model=ExtractResumeTextResponse)
async def extract_resume_text(file: UploadFile = File(...)) -> ExtractResumeTextResponse:
    text = await extract_resume_text_from_upload(file)
    logger.info("Extracted resume text. text_chars=%s", len(text))
    return ExtractResumeTextResponse(text=text)


@router.post("/api/profile/base-resume", response_model=BaseResumeResponse)
async def save_base_resume(
    payload: BaseResumeUpload, db: Session = Depends(get_db)
) -> BaseResumeResponse:
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


@router.get("/api/profile/base-resume", response_model=BaseResumeResponse)
async def get_base_resume(db: Session = Depends(get_db)) -> BaseResumeResponse:
    profile = base_profile(db)
    if profile is None or not profile.base_resume_text:
        raise fail(404, "NO_BASE_RESUME", "Base resume is missing.")
    return BaseResumeResponse(text=profile.base_resume_text, updatedAt=profile.updated_at)


@router.delete("/api/profile/base-resume", status_code=status.HTTP_204_NO_CONTENT)
async def delete_base_resume(db: Session = Depends(get_db)) -> None:
    profile = base_profile(db)
    if profile is not None:
        db.delete(profile)
        db.commit()
