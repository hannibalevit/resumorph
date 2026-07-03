"""Small, deliberately conservative job-session helpers for the local MVP."""

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.schemas import CompanyInfo, FieldAnswerResponse, JobContext, PageSnapshot

TRACKING_PARAMS = {"ref", "source", "trk", "trackingid", "utm_source", "utm_medium", "utm_campaign"}
SENSITIVE_TERMS = (
    "password",
    "credit card",
    "card number",
    "payment",
    "ssn",
    "social security",
    "passport",
    "national id",
    "security question",
    "medical",
    "disability",
    "gender",
    "race",
    "ethnicity",
    "veteran",
)
MANUAL_TERMS = ("salary", "compensation", "work authorization", "visa", "relocat", "availability")
MAX_SCAN_PROMPT_TEXT = 80_000
PRIMARY_SCAN_TEXT_BUDGET = 45_000


def normalize_url(value: str) -> str:
    parsed = urlparse(value)
    query = [
        (key, val) for key, val in parse_qsl(parsed.query) if key.lower() not in TRACKING_PARAMS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", urlencode(query), ""))


def canonical_job_key(snapshot: PageSnapshot) -> str:
    normalized = normalize_url(snapshot.normalized_url or snapshot.url)
    # Stable provider IDs in the path/query make the URL enough for an MVP.
    return normalized.lower()


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _detected_meta_block(snapshot: PageSnapshot) -> str:
    """Surface high-signal identity fields the page header/structured data exposes.

    The company name in particular often lives only in a logo, header, or JSON-LD
    block that never appears in the job-description body, so without this hint the
    model returns null and the UI shows "Unknown company".
    """
    pairs = (
        ("Company", snapshot.detected_company),
        ("Job title", snapshot.detected_job_title),
        ("Location", snapshot.detected_location),
    )
    lines = [f"- {label}: {value.strip()}" for label, value in pairs if value and value.strip()]
    if not lines:
        return ""
    body = "\n".join(lines)
    return (
        "Structured metadata detected from the page header/JSON-LD (explicit facts "
        "from this page — prefer these for the corresponding fields):\n" + body
    )


def compose_scan_page_text(snapshot: PageSnapshot) -> str:
    """Give the model a focused extraction plus full-page context within one budget."""
    selected = (snapshot.selected_text or "").strip()
    primary = selected or (snapshot.primary_job_text or "").strip()
    visible = (snapshot.visible_text or "").strip()
    meta_block = _detected_meta_block(snapshot)
    prefix = f"{meta_block}\n\n" if meta_block else ""

    if not primary:
        return _clip(f"{prefix}Full visible page text:\n{visible}", MAX_SCAN_PROMPT_TEXT)

    source = "selected_text" if selected else (snapshot.primary_job_source or "primary_extraction")
    confidence = snapshot.primary_job_confidence
    confidence_label = f", confidence {confidence:.2f}" if confidence is not None else ""
    primary_part = prefix + _clip(
        f"Primary extracted job text (source: {source}{confidence_label}):\n{primary}",
        PRIMARY_SCAN_TEXT_BUDGET,
    )

    remaining = MAX_SCAN_PROMPT_TEXT - len(primary_part) - 160
    if remaining <= 0 or not visible:
        return primary_part

    visible_part = _clip(
        "Full visible page text fallback/context. Use it to recover details missing "
        "from the primary extraction, but beware navigation, similar jobs, and "
        f"boilerplate:\n{visible}",
        remaining,
    )
    return f"{primary_part}\n\n{visible_part}"


def _lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip("•- \t") for line in text.splitlines() if line.strip()]


def _section_items(text: str, names: tuple[str, ...]) -> list[str]:
    lines = _lines(text)
    start = next(
        (index for index, line in enumerate(lines) if any(name in line.lower() for name in names)),
        None,
    )
    if start is None:
        return []
    result: list[str] = []
    for line in lines[start + 1 : start + 12]:
        if len(line) < 3:
            continue
        if (
            any(
                marker in line.lower()
                for marker in (
                    "benefit",
                    "qualification",
                    "requirement",
                    "responsibilit",
                    "about the",
                )
            )
            and result
        ):
            break
        result.append(line)
    return result[:8]


def extract_context_fallback(snapshot: PageSnapshot) -> JobContext:
    """Extract only obvious on-page signals when no LLM key is configured."""
    text = snapshot.selected_text or snapshot.primary_job_text or snapshot.visible_text
    lines = _lines(text)
    title = snapshot.title.split("|")[0].split(" - ")[0].strip() or None
    h1 = next(
        (
            heading.get("text", "").strip()
            for heading in snapshot.headings
            if heading.get("level") == 1
        ),
        "",
    )
    if h1 and len(h1) <= 140:
        title = h1
    company = None
    company_match = re.search(r"(?:at|@)\s+([A-Z][\w&.,' -]{1,80})", snapshot.title)
    if company_match:
        company = company_match.group(1).strip(" -|")
    location = next(
        (
            line
            for line in lines[:25]
            if re.search(r"\b(remote|hybrid|on-site|onsite)\b|,\s*[A-Z]{2}\b", line, re.I)
        ),
        None,
    )
    requirements = _section_items(
        text, ("requirements", "qualifications", "what you bring", "skills")
    )
    responsibilities = _section_items(
        text, ("responsibilities", "what you'll do", "what you will do", "role")
    )
    benefits = _section_items(text, ("benefits", "perks", "what we offer"))
    keywords = []
    for word in (
        "python",
        "typescript",
        "react",
        "sql",
        "aws",
        "docker",
        "leadership",
        "analytics",
        "product",
    ):
        if re.search(rf"\b{re.escape(word)}\b", text, re.I):
            keywords.append(word.title() if word != "aws" else "AWS")
    description = "\n".join(lines[:30])[:5000] or None
    return JobContext(
        companyName=company,
        positionTitle=title,
        location=location,
        jobDescription=description,
        responsibilities=responsibilities,
        requirements=requirements,
        benefits=benefits,
        companyInfo=CompanyInfo(),
        keywords=keywords,
        confidence=0.45,
        warnings=["OPENAI_API_KEY is not configured; used conservative local extraction."],
    )


def missing_requirements(resume: str, context: JobContext) -> list[str]:
    resume_lower = resume.lower()
    return [item for item in context.requirements if item.lower() not in resume_lower][:8]


def local_field_answer(
    label: str, resume: str, context: JobContext, max_length: int
) -> FieldAnswerResponse:
    lower = label.lower()
    if any(term in lower for term in SENSITIVE_TERMS):
        return FieldAnswerResponse(
            answer="",
            confidence=0,
            warnings=["This is a sensitive field and must be completed manually."],
        )
    if any(term in lower for term in MANUAL_TERMS):
        return FieldAnswerResponse(
            answer="[Please provide your own answer for this question.]",
            confidence=0.1,
            warnings=["This question needs a personal confirmation; the assistant will not guess."],
        )
    role = context.position_title or "this role"
    company = context.company_name or "your company"
    excerpt = re.sub(r"\s+", " ", resume).strip()[: min(700, max_length - 260)]
    if any(term in lower for term in ("why", "interest", "motiv", "cover letter")):
        answer = (
            f"I am interested in the {role} opportunity at {company} "
            f"because it aligns with my documented background: {excerpt}"
        )
    elif any(
        term in lower
        for term in ("experience", "describe", "background", "tell us", "qualification")
    ):
        answer = f"Regarding “{label}”: my relevant documented experience is {excerpt}"
    elif any(term in lower for term in ("website", "portfolio", "linkedin", "github")):
        answer = "[Please add the relevant link from your profile.]"
    elif any(term in lower for term in ("name", "phone", "email", "address")):
        answer = "[Please enter your personal contact information manually.]"
    else:
        answer = f"Regarding “{label}”: {excerpt}"
    return FieldAnswerResponse(
        answer=answer[:max_length],
        confidence=0.35,
        warnings=[
            "OPENAI_API_KEY is not configured; this is a conservative "
            "question-specific draft. Review and edit it."
        ],
    )
