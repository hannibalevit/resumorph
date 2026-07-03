"""Backwards-compatible non-session resume endpoint.

Predates the session-based ``/api/job-sessions/*`` flow but is still live — not
dead code. ``create_tailored_resume`` is referenced here so tests stub it by
patching this module.
"""

import base64

from fastapi import APIRouter

from app.document_generator import DOCX_MIME_TYPE, create_docx_resume
from app.errors import fail
from app.openai_client import ResumeGenerationError
from app.resume_generator import create_tailored_resume
from app.schemas import GenerateResumeRequest, GenerateResumeResponse
from app.validation import validate_generation_request

router = APIRouter()


@router.post("/api/generate-resume", response_model=GenerateResumeResponse)
async def generate_resume(payload: GenerateResumeRequest) -> GenerateResumeResponse:
    validated_payload = validate_generation_request(payload)
    try:
        tailored_resume = await create_tailored_resume(validated_payload)
        docx_bytes = create_docx_resume(tailored_resume)
    except ResumeGenerationError as exc:
        raise fail(502, "LLM_GENERATION_FAILED", str(exc)) from exc
    return GenerateResumeResponse(
        fileName="tailored-resume.docx",
        mimeType=DOCX_MIME_TYPE,
        base64=base64.b64encode(docx_bytes).decode("ascii"),
        notes=tailored_resume.notes,
    )
