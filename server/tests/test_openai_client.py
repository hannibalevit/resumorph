from types import SimpleNamespace

import app.openai_client as openai_client
import pytest
from app.openai_client import (
    FieldAnswerGenerationError,
    JobExtractionError,
    ResumeGenerationError,
    build_resume_prompt,
    extract_contact_info,
    extract_job_context,
    generate_field_answer,
    generate_tailored_resume,
)
from app.schemas import (
    DetectedFormField,
    FieldAnswerResponse,
    GenerateOptions,
    GenerateResumeRequest,
    JobContext,
    JobPage,
    LegacyTailoredResume,
    PageSnapshot,
    ResumeExperienceItem,
)
from openai import OpenAIError

BASE_RESUME = (
    "Ada Lovelace\n"
    "ada@example.com | +1 555 123 4567\n"
    "London, UK\n"
    "Senior Python engineer with a decade of backend experience."
)


def _patch_settings(monkeypatch, api_key="sk-test") -> None:
    monkeypatch.setattr(
        openai_client,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key=api_key, openai_timeout_seconds=60.0, openai_model="gpt-test"
        ),
    )


def _patch_client(monkeypatch, *, parsed=None, raises=None) -> None:
    class Responses:
        async def parse(self, **kwargs: object):
            if raises is not None:
                raise raises
            return SimpleNamespace(output_parsed=parsed)

    def factory(*args: object, **kwargs: object):
        return SimpleNamespace(responses=Responses())

    monkeypatch.setattr(openai_client, "AsyncOpenAI", factory)


def _resume_request() -> GenerateResumeRequest:
    return GenerateResumeRequest(
        baseResume=BASE_RESUME + " " * 50 + "More detail about delivery and testing.",
        jobPage=JobPage(url="https://x.com/job", title="Engineer", text="Build APIs"),
        options=GenerateOptions(),
    )


# ---------------------------------------------------------------------------
# extract_contact_info
# ---------------------------------------------------------------------------


def test_extract_contact_info_collects_contact_lines() -> None:
    result = extract_contact_info(BASE_RESUME)
    assert result is not None
    assert "ada@example.com" in result


def test_extract_contact_info_falls_back_to_second_line() -> None:
    resume = "Ada Lovelace\nSenior Engineer\nSome body text here."
    assert extract_contact_info(resume) == "Senior Engineer"


def test_extract_contact_info_returns_none_for_single_line() -> None:
    assert extract_contact_info("Ada Lovelace") is None


# ---------------------------------------------------------------------------
# build_resume_prompt
# ---------------------------------------------------------------------------


def test_build_resume_prompt_includes_job_text() -> None:
    prompt = build_resume_prompt(_resume_request())
    assert "Build APIs" in prompt


# ---------------------------------------------------------------------------
# generate_tailored_resume
# ---------------------------------------------------------------------------


async def test_generate_tailored_resume_requires_api_key(monkeypatch) -> None:
    _patch_settings(monkeypatch, api_key="")
    with pytest.raises(ResumeGenerationError, match="not configured"):
        await generate_tailored_resume(_resume_request())


async def test_generate_tailored_resume_backfills_contact_info(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    parsed = LegacyTailoredResume(
        candidateName="Ada Lovelace",
        contactInfo=None,
        headline="Engineer",
        summary="Summary",
        skills=["Python"],
        experience=[ResumeExperienceItem(company="Acme", title="Eng", bullets=["Did work"])],
    )
    _patch_client(monkeypatch, parsed=parsed)
    result = await generate_tailored_resume(_resume_request())
    assert result.contact_info is not None
    assert "ada@example.com" in result.contact_info


async def test_generate_tailored_resume_maps_openai_error(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    _patch_client(monkeypatch, raises=OpenAIError("boom"))
    with pytest.raises(ResumeGenerationError, match="could not generate"):
        await generate_tailored_resume(_resume_request())


async def test_generate_tailored_resume_rejects_invalid_format(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    _patch_client(monkeypatch, parsed={"not": "a model"})
    with pytest.raises(ResumeGenerationError, match="invalid resume format"):
        await generate_tailored_resume(_resume_request())


# ---------------------------------------------------------------------------
# extract_job_context
# ---------------------------------------------------------------------------


def _snapshot() -> PageSnapshot:
    return PageSnapshot(
        url="https://x.com/job",
        normalizedUrl="https://x.com/job",
        title="Engineer",
        visibleText="Build APIs with Python and SQL across teams and services.",
    )


async def test_extract_job_context_requires_api_key(monkeypatch) -> None:
    _patch_settings(monkeypatch, api_key="")
    with pytest.raises(JobExtractionError, match="not configured"):
        await extract_job_context(_snapshot())


async def test_extract_job_context_success(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    _patch_client(monkeypatch, parsed=JobContext(companyName="Acme", positionTitle="Engineer"))
    result = await extract_job_context(_snapshot())
    assert result.company_name == "Acme"


async def test_extract_job_context_maps_openai_error(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    _patch_client(monkeypatch, raises=OpenAIError("boom"))
    with pytest.raises(JobExtractionError, match="could not extract"):
        await extract_job_context(_snapshot())


# ---------------------------------------------------------------------------
# generate_field_answer
# ---------------------------------------------------------------------------


def _field() -> DetectedFormField:
    return DetectedFormField(fieldId="f1", tagName="textarea", label="Why do you want this role?")


async def test_generate_field_answer_requires_api_key(monkeypatch) -> None:
    _patch_settings(monkeypatch, api_key="")
    with pytest.raises(FieldAnswerGenerationError, match="not configured"):
        await generate_field_answer(_field(), BASE_RESUME, JobContext(), "professional", 300)


async def test_generate_field_answer_success(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    _patch_client(
        monkeypatch,
        parsed=FieldAnswerResponse(answer="Because I love it.", confidence=0.8),
    )
    result = await generate_field_answer(_field(), BASE_RESUME, JobContext(), "professional", 300)
    assert result.answer == "Because I love it."


async def test_generate_field_answer_maps_unexpected_error(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    _patch_client(monkeypatch, raises=RuntimeError("kaboom"))
    with pytest.raises(FieldAnswerGenerationError, match="Unexpected error"):
        await generate_field_answer(_field(), BASE_RESUME, JobContext(), "professional", 300)
