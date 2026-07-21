"""Pure string helpers with no DB or LLM dependencies."""

import re

_COMPANY_JOBS_LINK_PHRASES = (
    "all jobs",
    "all open positions",
    "all openings",
    "browse jobs",
    "careers",
    "current openings",
    "explore careers",
    "job openings",
    "open positions",
    "open roles",
    "our jobs",
    "search jobs",
    "see all jobs",
    "view all jobs",
    "view jobs",
    "view openings",
)
_COMPANY_HOME_LINK_PHRASES = (
    "about us",
    "company website",
    "home page",
    "homepage",
    "learn more about",
    "our website",
    "visit our website",
    "visit website",
)


def classify_related_link(url: str, text: str = "", company_name: str | None = None) -> str:
    """Classify a scraped anchor as one of a fixed set of link types.

    ``company``/``company_jobs`` rely on the anchor's visible text (a URL alone
    can't distinguish a company's homepage or "all open roles" page from any
    other link on the same domain), so a link is only ever tagged that way
    when the page itself labelled it clearly enough — anything ambiguous
    falls through to ``other`` rather than guessing.
    """
    lowered_url = url.lower()
    lowered_text = text.strip().lower()
    if "linkedin.com" in lowered_url:
        return "linkedin"
    if any(phrase in lowered_text for phrase in _COMPANY_JOBS_LINK_PHRASES):
        return "company_jobs"
    if any(
        part in lowered_url
        for part in (
            "greenhouse.io",
            "lever.co",
            "workday.com",
            "ashbyhq.com",
            "smartrecruiters.com",
        )
    ):
        return "ats"
    if any(part in lowered_text for part in ("apply", "application")) or any(
        part in lowered_url for part in ("apply", "application", "candidate")
    ):
        return "application_form"
    if lowered_text and company_name and lowered_text == company_name.strip().lower():
        return "company"
    if any(phrase in lowered_text for phrase in _COMPANY_HOME_LINK_PHRASES):
        return "company"
    return "other"


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


def safe_filename(*parts: str | None, fallback: str) -> str:
    stem = "-".join(part for part in parts if part).lower()
    stem = re.sub(r"[^a-z0-9а-яё]+", "-", stem, flags=re.I).strip("-")
    return (stem or fallback)[:120]


def resume_docx_filename(candidate_name: str, company_name: str | None = None) -> str:
    """<Name>_<Company>_Resume.docx, e.g. "Ada Lovelace", "Acme Corp" ->
    "Ada_Lovelace_Acme_Corp_Resume.docx". Falls back to "<Name>_Resume.docx" when
    the company name is missing (a job session's company_name can be null)."""

    def _clean(value: str) -> str:
        cleaned = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE).strip()
        return re.sub(r"\s+", "_", cleaned)

    parts = [part for part in (_clean(candidate_name), _clean(company_name or "")) if part]
    stem = "_".join(parts) or "Resume"
    return f"{stem}_Resume.docx"
