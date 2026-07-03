import pytest
from app.schemas import GenerateResumeRequest
from app.validation import MAX_JOB_TEXT_LENGTH, validate_generation_request
from fastapi import HTTPException, status


def make_request(job_text: str) -> GenerateResumeRequest:
    return GenerateResumeRequest(
        baseResume="Senior Python engineer with product experience. " * 4,
        jobPage={
            "url": "https://example.com/job",
            "title": "Backend Engineer",
            "text": job_text,
        },
    )


def test_validate_generation_request_rejects_blank_job_text() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_generation_request(make_request("   \n\t "))

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.detail == "Job page text is empty."


def test_validate_generation_request_clips_long_job_text() -> None:
    payload = make_request("x" * (MAX_JOB_TEXT_LENGTH + 100))

    result = validate_generation_request(payload)

    assert result is payload
    assert len(result.job_page.text) == MAX_JOB_TEXT_LENGTH
