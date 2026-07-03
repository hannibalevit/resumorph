import base64
import io
import re
import tempfile
from pathlib import Path
from typing import Literal
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright
from pypdf import PdfReader

from app.schemas import TailoredResume

PDF_MIME_TYPE = "application/pdf"

TEMPLATES_DIR = Path(__file__).with_name("templates")
FONTS_DIR = TEMPLATES_DIR / "fonts"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)

PAGE_WIDTH = {"letter": "8.5in", "a4": "210mm"}


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
_FONT_REF_RE = re.compile(r"url\(\s*(['\"]?)\./fonts/([^'\")\s]+)\1\s*\)")

_FONT_MIME = {"woff2": "font/woff2", "woff": "font/woff", "otf": "font/otf", "ttf": "font/ttf"}


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
    titles = [_normalize_section_title(match.group(1)) for match in _SECTION_TITLE_RE.finditer(html)]
    titles = [title for title in titles if title]
    rendered_keys = [_section_key(title) for title in titles]
    rendered_comparable = [key for key in rendered_keys if key in EXPECTED_SECTION_ORDER]
    if len(rendered_comparable) < 2:
        return

    expected_positions = {key: index for index, key in enumerate(EXPECTED_SECTION_ORDER)}
    for previous, current in zip(rendered_comparable, rendered_comparable[1:]):
        if expected_positions[current] < expected_positions[previous]:
            raise PdfSectionOrderError(
                f"Resume template section order diverges from the expected order: "
                f"rendered {' -> '.join(rendered_comparable)}; expected {' -> '.join(EXPECTED_SECTION_ORDER)}"
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
    t, n = re.subn(" ", " ", t)
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


def inline_local_fonts(html: str, fonts_dir: Path = FONTS_DIR) -> str:
    """Inline url('./fonts/...') references as base64 data: URLs.

    Ported defensively from career-ops's generate-pdf.mjs even though the
    current template only uses system fonts (so this is expected to be a
    no-op today) — kept for future templates that may bundle local fonts.
    """
    names = {match.group(2) for match in _FONT_REF_RE.finditer(html)}
    if not names:
        return html

    data_urls: dict[str, str] = {}
    for name in names:
        font_path = (fonts_dir / name).resolve()
        try:
            font_path.relative_to(fonts_dir.resolve())
        except ValueError:
            continue
        if not font_path.is_file():
            continue
        extension = font_path.suffix.lstrip(".").lower()
        mime = _FONT_MIME.get(extension, "application/octet-stream")
        encoded = base64.b64encode(font_path.read_bytes()).decode("ascii")
        data_urls[name] = f"url('data:{mime};base64,{encoded}')"

    def replace(match: re.Match[str]) -> str:
        return data_urls.get(match.group(2), match.group(0))

    return _FONT_REF_RE.sub(replace, html)


async def render_html_to_pdf(html: str, page_format: Literal["letter", "a4"]) -> tuple[bytes, int]:
    with tempfile.TemporaryDirectory(prefix="resume-pdf-") as temp_dir:
        html_path = Path(temp_dir) / f"{uuid4()}.html"
        html_path.write_text(html, encoding="utf-8")

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(html_path.as_uri(), wait_until="load")
                await page.evaluate("document.fonts.ready")
                pdf_bytes = await page.pdf(
                    format=page_format,
                    print_background=True,
                    margin={"top": "0.6in", "right": "0.6in", "bottom": "0.6in", "left": "0.6in"},
                    prefer_css_page_size=False,
                )
            finally:
                await browser.close()

    page_count = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    return pdf_bytes, page_count


async def render_resume_pdf(resume: TailoredResume) -> tuple[bytes, int, dict[str, int]]:
    page_width = PAGE_WIDTH.get(resume.page_format, PAGE_WIDTH["a4"])
    template = _jinja_env.get_template("cv_template.html")
    html = template.render(resume=resume, page_width=page_width, lang=resume.language or "en")

    validate_section_order(html)
    html, replacements = normalize_text_for_ats(html)
    html = inline_local_fonts(html)

    try:
        pdf_bytes, page_count = await render_html_to_pdf(html, resume.page_format)
    except PdfGenerationError:
        raise
    except Exception as exc:
        raise PdfGenerationError(f"Failed to render resume PDF: {exc}") from exc

    return pdf_bytes, page_count, replacements
