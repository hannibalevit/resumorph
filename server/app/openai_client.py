import logging
import re

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, OpenAIError

from app.config import get_settings
from app.job_service import compose_scan_page_text
from app.prompt_loader import render_prompt
from app.schemas import (
    DetectedFormField,
    FieldAnswerResponse,
    GenerateResumeRequest,
    JobContext,
    LegacyTailoredResume,
    PageSnapshot,
)

logger = logging.getLogger(__name__)


class ResumeGenerationError(Exception):
    """Raised when the resume generation model call fails in a controlled way."""


class JobExtractionError(Exception):
    """Raised when the job-context extraction request cannot be completed."""


class FieldAnswerGenerationError(Exception):
    """Raised when a question-specific application answer cannot be generated."""


def extract_contact_info(base_resume: str) -> str | None:
    lines = [re.sub(r"\s+", " ", line).strip() for line in base_resume.splitlines() if line.strip()]
    contact_pattern = re.compile(
        r"@|https?://|linkedin\.com|github\.com|\+?\d[\d\s().-]{6,}|remote|relocat|[A-Z][a-z]+,\s*[A-Z]{2}\b",
        re.I,
    )
    candidates = [line for line in lines[1:8] if contact_pattern.search(line)]
    if candidates:
        return " | ".join(candidates[:3])[:500]
    return lines[1][:500] if len(lines) > 1 and len(lines[1]) <= 180 else None


async def generate_field_answer(
    field: DetectedFormField,
    base_resume: str,
    context: JobContext,
    tone: str,
    max_length: int,
) -> FieldAnswerResponse:
    """Generate an answer for exactly one field, grounded in the supplied facts."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise FieldAnswerGenerationError("OPENAI_API_KEY is not configured on the backend.")
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
    question = field.label or field.nearby_text or field.placeholder or "Application question"
    prompt = render_prompt(
        "openai",
        "field_answer",
        question=question,
        max_length=max_length,
        field_answer_schema=FieldAnswerResponse.model_json_schema(),
        field_type=field.type or field.tag_name,
        placeholder=field.placeholder or "(none)",
        nearby_text=field.nearby_text or "(none)",
        current_value=field.current_value or "(empty)",
        job_context_json=context.model_dump_json(by_alias=True),
        base_resume=base_resume[:50_000],
    )
    try:
        response = await client.responses.parse(
            model=settings.openai_model,
            input=[
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            text_format=FieldAnswerResponse,
        )
    except (APITimeoutError, APIConnectionError) as exc:
        raise FieldAnswerGenerationError(
            "OpenAI answer generation timed out or could not connect."
        ) from exc
    except OpenAIError as exc:
        raise FieldAnswerGenerationError(
            "OpenAI could not generate an answer for this field."
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected field-answer generation failure")
        raise FieldAnswerGenerationError(
            "Unexpected error while generating the field answer."
        ) from exc
    parsed = response.output_parsed
    if not isinstance(parsed, FieldAnswerResponse):
        raise FieldAnswerGenerationError("OpenAI returned an invalid field-answer format.")
    return parsed


async def extract_job_context(snapshot: PageSnapshot) -> JobContext:
    """Ask the model for strict structured context, never facts beyond the snapshot."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise JobExtractionError("OPENAI_API_KEY is not configured on the backend.")
    client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)
    prompt = render_prompt(
        "openai",
        "job_scan",
        job_context_schema=JobContext.model_json_schema(),
        url=snapshot.url,
        title=snapshot.title,
        headings=snapshot.headings[:12],
        page_text=compose_scan_page_text(snapshot),
    )
    try:
        response = await client.responses.parse(
            model=settings.openai_model,
            input=[
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            text_format=JobContext,
        )
    except (APITimeoutError, APIConnectionError) as exc:
        raise JobExtractionError("OpenAI extraction timed out or could not connect.") from exc
    except OpenAIError as exc:
        raise JobExtractionError("OpenAI could not extract the job posting.") from exc
    except Exception as exc:
        logger.exception("Unexpected job extraction failure")
        raise JobExtractionError("Unexpected error while extracting job context.") from exc
    parsed = response.output_parsed
    if not isinstance(parsed, JobContext):
        raise JobExtractionError("OpenAI returned an invalid job-context format.")
    return parsed


def build_resume_prompt(payload: GenerateResumeRequest) -> str:
    language_name = "English" if payload.options.language == "en" else "Russian"

    return render_prompt(
        "openai",
        "legacy_tailored_resume",
        language_name=language_name,
        base_resume=payload.base_resume,
        job_url=payload.job_page.url,
        job_title=payload.job_page.title,
        job_text=payload.job_page.text,
    ).user


async def generate_tailored_resume(payload: GenerateResumeRequest) -> LegacyTailoredResume:
    settings = get_settings()

    if not settings.openai_api_key:
        raise ResumeGenerationError("OPENAI_API_KEY is not configured on the backend.")

    client = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
    )
    prompt = render_prompt(
        "openai",
        "legacy_tailored_resume",
        language_name="English" if payload.options.language == "en" else "Russian",
        base_resume=payload.base_resume,
        job_url=payload.job_page.url,
        job_title=payload.job_page.title,
        job_text=payload.job_page.text,
    )

    try:
        response = await client.responses.parse(
            model=settings.openai_model,
            input=[
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            text_format=LegacyTailoredResume,
        )
    except (APITimeoutError, APIConnectionError) as exc:
        logger.warning(
            "OpenAI request failed due to connectivity or timeout: %s", exc.__class__.__name__
        )
        raise ResumeGenerationError("OpenAI request timed out or could not connect.") from exc
    except OpenAIError as exc:
        logger.warning("OpenAI request failed: %s", exc.__class__.__name__)
        raise ResumeGenerationError("OpenAI could not generate the tailored resume.") from exc
    except Exception as exc:
        logger.exception("Unexpected resume generation failure")
        raise ResumeGenerationError(
            "Unexpected error while generating the tailored resume."
        ) from exc

    parsed = response.output_parsed
    if not isinstance(parsed, LegacyTailoredResume):
        raise ResumeGenerationError("OpenAI returned an invalid resume format.")
    if not parsed.contact_info:
        parsed.contact_info = extract_contact_info(payload.base_resume)

    return parsed
