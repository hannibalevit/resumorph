import asyncio
import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from app.schemas import CoverLetter, TailoredResume

PDF_MIME_TYPE = "application/pdf"

TEMPLATES_DIR = Path(__file__).with_name("templates")

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)

# CSS @page size keyword per paper format (drives physical page dimensions in
# WeasyPrint; margins are set alongside it in the template's @page rule).
PAGE_SIZE = {"letter": "letter", "a4": "A4"}


class PdfGenerationError(Exception):
    """Raised when rendering the tailored resume to PDF fails."""


class PdfSectionOrderError(PdfGenerationError):
    """Raised when the rendered HTML's section order violates the expected order."""


# Ported from career-ops's generate-pdf.mjs SECTION_ALIASES map.
SECTION_ALIASES = {
    "summary": "summary",
    "professional summary": "summary",
    "competencies": "competencies",
    "core competencies": "competencies",
    "experience": "experience",
    "work experience": "experience",
    "professional experience": "experience",
    "projects": "projects",
    "selected projects": "projects",
    "personal projects": "projects",
    "education": "education",
    "education & certifications": "education",
    "certifications": "certifications",
    "skills": "skills",
    "technical skills": "skills",
}

EXPECTED_SECTION_ORDER = [
    "summary",
    "competencies",
    "experience",
    "projects",
    "education",
    "certifications",
    "skills",
]

_SECTION_TITLE_RE = re.compile(
    r"class=[\"'][^\"']*\bsection-title\b[^\"']*[\"'][^>]*>([\s\S]*?)</[^>]+>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_SCRIPT_RE = re.compile(r"<(style|script)\b[^>]*>[\s\S]*?</\1>", re.IGNORECASE)


def _normalize_section_title(text: str) -> str:
    text = _TAG_RE.sub(" ", text)
    text = text.replace("{{", " ").replace("}}", " ")
    text = text.replace("&amp;", "&")
    text = re.sub(r"[*_`~]", "", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _section_key(text: str) -> str:
    normalized = _normalize_section_title(text)
    return SECTION_ALIASES.get(normalized, normalized)


def validate_section_order(html: str) -> None:
    """Guard against the Jinja2 template rendering sections out of order.

    Unlike career-ops (which diffs the LLM-authored HTML against cv.md), there
    is no per-request source of truth here — the template itself controls
    section order, not the LLM. This is a template-authoring regression
    guard, not an LLM-output guard.
    """
    titles = [
        _normalize_section_title(match.group(1)) for match in _SECTION_TITLE_RE.finditer(html)
    ]
    titles = [title for title in titles if title]
    rendered_keys = [_section_key(title) for title in titles]
    rendered_comparable = [key for key in rendered_keys if key in EXPECTED_SECTION_ORDER]
    if len(rendered_comparable) < 2:
        return

    expected_positions = {key: index for index, key in enumerate(EXPECTED_SECTION_ORDER)}
    for previous, current in zip(rendered_comparable, rendered_comparable[1:], strict=False):
        if expected_positions[current] < expected_positions[previous]:
            raise PdfSectionOrderError(
                f"Resume template section order diverges from the expected order: "
                f"rendered {' -> '.join(rendered_comparable)}; "
                f"expected {' -> '.join(EXPECTED_SECTION_ORDER)}"
            )


def normalize_text_for_ats(html: str) -> tuple[str, dict[str, int]]:
    """Convert problematic Unicode to ASCII equivalents in body text only.

    Near-literal port of career-ops's generate-pdf.mjs normalizeTextForATS.
    Only touches text nodes outside <style>/<script>/tags — never CSS, JS,
    tag attributes, or URLs.
    """
    replacements: dict[str, int] = {}

    def bump(key: str, n: int = 1) -> None:
        replacements[key] = replacements.get(key, 0) + n

    masks: list[str] = []

    def mask(match: re.Match[str]) -> str:
        token = f"\x00MASK{len(masks)}\x00"
        masks.append(match.group(0))
        return token

    masked = _STYLE_SCRIPT_RE.sub(mask, html)

    out: list[str] = []
    i = 0
    length = len(masked)
    while i < length:
        lt = masked.find("<", i)
        if lt == -1:
            out.append(_sanitize_text(masked[i:], bump))
            break
        out.append(_sanitize_text(masked[i:lt], bump))
        gt = masked.find(">", lt)
        if gt == -1:
            out.append(masked[lt:])
            break
        out.append(masked[lt : gt + 1])
        i = gt + 1

    result = "".join(out)
    for index, original in enumerate(masks):
        result = result.replace(f"\x00MASK{index}\x00", original)

    return result, replacements


def _sanitize_text(text: str, bump) -> str:
    if not text:
        return text
    t = text
    t, n = re.subn("—", "-", t)
    if n:
        bump("em-dash", n)
    t, n = re.subn("–", "-", t)
    if n:
        bump("en-dash", n)
    t, n = re.subn("[“”„‟]", '"', t)
    if n:
        bump("smart-double-quote", n)
    t, n = re.subn("[‘’‚‛]", "'", t)
    if n:
        bump("smart-single-quote", n)
    t, n = re.subn("…", "...", t)
    if n:
        bump("ellipsis", n)
    t, n = re.subn("[​‌‍⁠﻿]", "", t)
    if n:
        bump("zero-width", n)
    t, n = re.subn("\xa0", " ", t)
    if n:
        bump("nbsp", n)
    t, n = re.subn(r"\s*→\s*", " to ", t)
    if n:
        bump("right-arrow", n)
    t, n = re.subn(r"\s*←\s*", " from ", t)
    if n:
        bump("left-arrow", n)
    t, n = re.subn(r"\s*[↑↓]\s*", " ", t)
    if n:
        bump("vert-arrow", n)
    t, n = re.subn(r"\s*·\s*", " | ", t)
    if n:
        bump("middot", n)
    t, n = re.subn(r"\s*•\s*", " | ", t)
    if n:
        bump("bullet", n)
    # ¥ (yen) is intentionally left untouched — ambiguous JPY/CNY, see
    # career-ops's generate-pdf.mjs for the same rationale.
    t, n = re.subn("€", "EUR ", t)
    if n:
        bump("euro", n)
    t, n = re.subn("£", "GBP ", t)
    if n:
        bump("pound", n)
    return t


def _render_pdf_sync(html: str) -> tuple[bytes, int]:
    """Render HTML to PDF bytes via WeasyPrint (synchronous, CPU-bound)."""
    document = HTML(string=html).render()
    pdf_bytes = document.write_pdf()
    return pdf_bytes, len(document.pages)


async def render_html_to_pdf(html: str) -> tuple[bytes, int]:
    """Run the blocking WeasyPrint render in a thread so the event loop is free.

    Paper size (letter/a4) and 0.6in margins are baked into the HTML's @page
    CSS rule by the template — WeasyPrint reads them from there, so no
    per-call format argument is needed (unlike the previous Playwright path,
    which set margins via page.pdf() options).
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _render_pdf_sync, html)


async def render_resume_pdf(resume: TailoredResume) -> tuple[bytes, int, dict[str, int]]:
    page_size = PAGE_SIZE.get(resume.page_format, PAGE_SIZE["a4"])
    template = _jinja_env.get_template("cv_template.html")
    html = template.render(resume=resume, page_size=page_size, lang=resume.language or "en")

    validate_section_order(html)
    html, replacements = normalize_text_for_ats(html)

    try:
        pdf_bytes, page_count = await render_html_to_pdf(html)
    except PdfGenerationError:
        raise
    except Exception as exc:
        raise PdfGenerationError(f"Failed to render resume PDF: {exc}") from exc

    return pdf_bytes, page_count, replacements


async def render_cover_letter_pdf(letter: CoverLetter) -> tuple[bytes, int, dict[str, int]]:
    page_size = PAGE_SIZE.get(letter.page_format, PAGE_SIZE["a4"])
    template = _jinja_env.get_template("cover_letter_template.html")
    # Cover letters have no fixed section sequence, so validate_section_order
    # (a resume-only guard) is intentionally skipped here.
    html = template.render(letter=letter, page_size=page_size, lang="en")

    html, replacements = normalize_text_for_ats(html)

    try:
        pdf_bytes, page_count = await render_html_to_pdf(html)
    except PdfGenerationError:
        raise
    except Exception as exc:
        raise PdfGenerationError(f"Failed to render cover letter PDF: {exc}") from exc

    return pdf_bytes, page_count, replacements
