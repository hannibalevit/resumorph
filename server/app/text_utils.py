"""Pure string helpers with no DB or LLM dependencies."""

import re
from typing import Literal

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


def resume_filename(
    candidate_name: str,
    company_name: str | None = None,
    extension: Literal["docx", "pdf"] = "docx",
) -> str:
    """Return a stable resume filename for either supported document format."""

    def _clean(value: str) -> str:
        cleaned = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE).strip()
        return re.sub(r"\s+", "_", cleaned)

    parts = [part for part in (_clean(candidate_name), _clean(company_name or "")) if part]
    stem = "_".join(parts) or "Resume"
    return f"{stem}_Resume.{extension}"


def resume_docx_filename(candidate_name: str, company_name: str | None = None) -> str:
    """Backward-compatible DOCX filename helper."""

    return resume_filename(candidate_name, company_name, "docx")


# === Section heading translations ============================================
# TailoredResume carries a single `language` BCP-47 code but no per-section
# heading strings, so headings are looked up from this table by primary
# subtag rather than hard-coded in English (falls back to English for any
# language not listed here).

_SECTION_HEADINGS: dict[str, dict[str, str]] = {
    "en": {
        "summary": "Professional Summary",
        "competencies": "Core Competencies",
        "experience": "Work Experience",
        "projects": "Projects",
        "education": "Education",
        "certifications": "Certifications",
        "skills": "Skills",
        "languages": "Languages",
    },
    "ru": {
        "summary": "Профессиональный профиль",
        "competencies": "Ключевые компетенции",
        "experience": "Опыт работы",
        "projects": "Проекты",
        "education": "Образование",
        "certifications": "Сертификаты",
        "skills": "Навыки",
        "languages": "Языки",
    },
    "de": {
        "summary": "Berufliches Profil",
        "competencies": "Kernkompetenzen",
        "experience": "Berufserfahrung",
        "projects": "Projekte",
        "education": "Ausbildung",
        "certifications": "Zertifizierungen",
        "skills": "Fähigkeiten",
        "languages": "Sprachkenntnisse",
    },
    "fr": {
        "summary": "Profil professionnel",
        "competencies": "Compétences clés",
        "experience": "Expérience professionnelle",
        "projects": "Projets",
        "education": "Formation",
        "certifications": "Certifications",
        "skills": "Compétences",
        "languages": "Langues",
    },
    "es": {
        "summary": "Perfil profesional",
        "competencies": "Competencias clave",
        "experience": "Experiencia laboral",
        "projects": "Proyectos",
        "education": "Educación",
        "certifications": "Certificaciones",
        "skills": "Habilidades",
        "languages": "Idiomas",
    },
    "pt": {
        "summary": "Perfil profissional",
        "competencies": "Competências principais",
        "experience": "Experiência profissional",
        "projects": "Projetos",
        "education": "Formação",
        "certifications": "Certificações",
        "skills": "Habilidades",
        "languages": "Idiomas",
    },
    "it": {
        "summary": "Profilo professionale",
        "competencies": "Competenze chiave",
        "experience": "Esperienza lavorativa",
        "projects": "Progetti",
        "education": "Istruzione",
        "certifications": "Certificazioni",
        "skills": "Competenze",
        "languages": "Lingue",
    },
    "nl": {
        "summary": "Professioneel profiel",
        "competencies": "Kernkwaliteiten",
        "experience": "Werkervaring",
        "projects": "Projecten",
        "education": "Opleiding",
        "certifications": "Certificeringen",
        "skills": "Vaardigheden",
        "languages": "Talen",
    },
    "pl": {
        "summary": "Profil zawodowy",
        "competencies": "Kluczowe kompetencje",
        "experience": "Doświadczenie zawodowe",
        "projects": "Projekty",
        "education": "Wykształcenie",
        "certifications": "Certyfikaty",
        "skills": "Umiejętności",
        "languages": "Języki",
    },
}


def headings_for(language: str | None) -> dict[str, str]:
    primary = (language or "en").split("-")[0].lower()
    return _SECTION_HEADINGS.get(primary, _SECTION_HEADINGS["en"])


# === ATS text hygiene ==========================================================
# Same character-level substitutions the PDF path used to apply (ported as-is):
# straight quotes/hyphens only, no zero-width or non-breaking characters, spelled
# out currency symbols. Tracks replacement counts so callers can surface a
# "we normalized N characters" warning.


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
    t, n = re.subn("€", "EUR ", t)
    if n:
        bump("euro", n)
    t, n = re.subn("£", "GBP ", t)
    if n:
        bump("pound", n)
    return t


def clean_text(text: str | None, counts: dict[str, int]) -> str:
    def bump(key: str, n: int) -> None:
        counts[key] = counts.get(key, 0) + n

    return _sanitize_text(text or "", bump)


# === Contact line splitting ===================================================
# TailoredResume.contact_info is a single free-form " | "-joined string (no
# separate city/phone/email/url fields), so the two-line contact block the
# template calls for is produced by classifying each " | " segment as a URL or
# not, rather than by a schema change.

_URL_TOKEN_RE = re.compile(r"^(https?://)?(www\.)?[\w.-]+\.[a-z]{2,}(/\S*)?$", re.IGNORECASE)


def _is_url_token(token: str) -> bool:
    token = token.strip()
    if not token or "@" in token:
        return False
    return bool(_URL_TOKEN_RE.match(token))


def split_contact_lines(contact_info: str) -> tuple[str, str]:
    parts = [part.strip() for part in re.split(r"\s*\|\s*", contact_info) if part.strip()]
    primary = [part for part in parts if not _is_url_token(part)]
    urls = [part for part in parts if _is_url_token(part)]
    return " | ".join(primary), " | ".join(urls)
