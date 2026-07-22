import logging
import re

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI, OpenAIError

from app.config import get_settings
from app.prompt_loader import render_prompt
from app.schemas import GenerateResumeRequest, LegacyTailoredResume

logger = logging.getLogger(__name__)


class ResumeGenerationError(Exception):
    """Raised when the resume generation model call fails in a controlled way."""


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
