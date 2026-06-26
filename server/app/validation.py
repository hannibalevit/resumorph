from fastapi import HTTPException, status

from app.schemas import GenerateResumeRequest

MAX_JOB_TEXT_LENGTH = 50_000


def validate_generation_request(payload: GenerateResumeRequest) -> GenerateResumeRequest:
    if not payload.job_page.text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Job page text is empty.",
        )

    if len(payload.job_page.text) > MAX_JOB_TEXT_LENGTH:
        payload.job_page.text = payload.job_page.text[:MAX_JOB_TEXT_LENGTH]

    return payload
