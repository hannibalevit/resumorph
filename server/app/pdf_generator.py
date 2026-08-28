"""Programmatic PDF rendering for tailored resumes and cover letters."""

from pathlib import Path

from fpdf import FPDF, XPos, YPos

from app.schemas import CoverLetter, TailoredResume
from app.text_utils import clean_text, headings_for, split_contact_lines

PDF_MIME_TYPE = "application/pdf"
PDF_FONT_FAMILY = "DejaVu"
_FONT_DIRECTORY = Path(__file__).with_name("assets") / "fonts"

_FONT_PATHS = {
    "regular": _FONT_DIRECTORY / "DejaVuSans.ttf",
    "bold": _FONT_DIRECTORY / "DejaVuSans-Bold.ttf",
}
_NORMAL_MARGIN_MM = 18
_COMPACT_MARGIN_MM = 15
_COMPACT_SCALE = 0.7


class PdfGenerationError(Exception):
    """Raised when rendering a tailored document to PDF fails."""


class _DocumentPdf(FPDF):
    def header(self) -> None:
        # Documents intentionally have no repeating header.
        return


def _new_pdf(page_format: str, compact: bool = False) -> _DocumentPdf:
    pdf = _DocumentPdf(format="letter" if page_format == "letter" else "A4", unit="mm")
    pdf.add_font(PDF_FONT_FAMILY, fname=_FONT_PATHS["regular"])
    pdf.add_font(PDF_FONT_FAMILY, style="B", fname=_FONT_PATHS["bold"])
    margin = _COMPACT_MARGIN_MM if compact else _NORMAL_MARGIN_MM
    pdf.set_margins(margin, margin, margin)
    pdf.set_auto_page_break(auto=True, margin=margin)
    pdf.add_page()
    return pdf


def _text(value: str | None, counts: dict[str, int]) -> str:
    return clean_text(value, counts)


def _multi_cell(pdf: _DocumentPdf, height: float, text: str) -> None:
    pdf.multi_cell(pdf.epw, height, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _paragraph(
    pdf: _DocumentPdf,
    text: str,
    counts: dict[str, int],
    *,
    size: float = 10.5,
    compact: bool = False,
) -> None:
    pdf.set_font(PDF_FONT_FAMILY, size=size)
    _multi_cell(pdf, 5.2 * (_COMPACT_SCALE if compact else 1), _text(text, counts))
    pdf.ln(1.2 * (_COMPACT_SCALE if compact else 1))


def _heading(
    pdf: _DocumentPdf, text: str, counts: dict[str, int], *, compact: bool = False
) -> None:
    scale = _COMPACT_SCALE if compact else 1
    pdf.ln(2 * scale)
    pdf.set_font(PDF_FONT_FAMILY, style="B", size=12)
    _multi_cell(pdf, 6 * scale, _text(text, counts))
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2 * scale)


def _resume_pdf(resume: TailoredResume, *, compact: bool = False) -> tuple[bytes, dict[str, int]]:
    counts: dict[str, int] = {}
    pdf = _new_pdf(resume.page_format, compact)
    headings = headings_for(resume.language)

    pdf.set_font(PDF_FONT_FAMILY, style="B", size=18)
    _multi_cell(pdf, 8, _text(resume.candidate_name, counts))
    primary, urls = split_contact_lines(resume.contact_info or "")
    if primary:
        _paragraph(pdf, primary, counts, size=10, compact=compact)
    if urls:
        _paragraph(pdf, urls, counts, size=10, compact=compact)

    if resume.summary.strip():
        _heading(pdf, headings["summary"], counts, compact=compact)
        _paragraph(pdf, resume.summary, counts, compact=compact)
    competencies = [item.strip() for item in resume.competencies if item.strip()]
    if competencies:
        _heading(pdf, headings["competencies"], counts, compact=compact)
        _paragraph(pdf, " | ".join(competencies), counts, compact=compact)
    if resume.experience:
        _heading(pdf, headings["experience"], counts, compact=compact)
        for job in resume.experience:
            pdf.set_font(PDF_FONT_FAMILY, style="B", size=11)
            _multi_cell(pdf, 5.5 * (_COMPACT_SCALE if compact else 1), _text(job.title, counts))
            company = job.company if not job.dates else f"{job.company} | {job.dates}"
            _paragraph(pdf, company, counts, size=10, compact=compact)
            if job.location:
                _paragraph(pdf, job.location, counts, size=10, compact=compact)
            for bullet in job.bullets:
                if bullet.strip():
                    _paragraph(pdf, f"- {bullet.strip()}", counts, compact=compact)
    if resume.projects:
        _heading(pdf, headings["projects"], counts, compact=compact)
        for project in resume.projects:
            title = f"{project.title} ({project.badge})" if project.badge else project.title
            pdf.set_font(PDF_FONT_FAMILY, style="B", size=11)
            _multi_cell(pdf, 5.5 * (_COMPACT_SCALE if compact else 1), _text(title, counts))
            if project.description:
                _paragraph(pdf, project.description, counts, compact=compact)
            if project.tech:
                _paragraph(pdf, project.tech, counts, size=10, compact=compact)
    if resume.education:
        _heading(pdf, headings["education"], counts, compact=compact)
        for education in resume.education:
            heading = (
                education.degree if not education.year else f"{education.degree} | {education.year}"
            )
            pdf.set_font(PDF_FONT_FAMILY, style="B", size=11)
            _multi_cell(pdf, 5.5 * (_COMPACT_SCALE if compact else 1), _text(heading, counts))
            _paragraph(pdf, education.institution, counts, size=10, compact=compact)
            if education.description:
                _paragraph(pdf, education.description, counts, compact=compact)
    if resume.certifications:
        _heading(pdf, headings["certifications"], counts, compact=compact)
        for certification in resume.certifications:
            label = (
                f"{certification.title} - {certification.org}"
                if certification.org
                else certification.title
            )
            if certification.year:
                label = f"{label} | {certification.year}"
            _paragraph(pdf, label, counts, compact=compact)
    if resume.skills:
        _heading(pdf, headings["skills"], counts, compact=compact)
        _paragraph(
            pdf,
            ", ".join(item.strip() for item in resume.skills if item.strip()),
            counts,
            compact=compact,
        )
    languages = [item for item in resume.languages if item.language.strip()]
    if languages:
        _heading(pdf, headings["languages"], counts, compact=compact)
        _paragraph(
            pdf,
            ", ".join(
                f"{item.language.strip()} ({item.proficiency.strip()})"
                if item.proficiency and item.proficiency.strip()
                else item.language.strip()
                for item in languages
            ),
            counts,
            compact=compact,
        )

    return bytes(pdf.output()), counts


def _cover_letter_pdf(
    letter: CoverLetter, *, compact: bool = False
) -> tuple[bytes, dict[str, int]]:
    counts: dict[str, int] = {}
    pdf = _new_pdf(letter.page_format, compact)
    pdf.set_font(PDF_FONT_FAMILY, style="B", size=18)
    _multi_cell(pdf, 8, _text(letter.candidate_name, counts))
    primary, urls = split_contact_lines(letter.contact_info or "")
    if primary:
        _paragraph(pdf, primary, counts, size=10, compact=compact)
    if urls:
        _paragraph(pdf, urls, counts, size=10, compact=compact)
    credentials = [item.strip() for item in letter.credentials if item.strip()]
    if credentials:
        _paragraph(pdf, " | ".join(credentials), counts, size=10, compact=compact)
    role_line = (
        letter.role_title if not letter.company else f"{letter.role_title} - {letter.company}"
    )
    _paragraph(pdf, role_line, counts, size=11, compact=compact)
    if letter.dateline:
        _paragraph(pdf, letter.dateline, counts, compact=compact)
    _paragraph(pdf, letter.greeting, counts, compact=compact)
    _paragraph(pdf, letter.opening, counts, compact=compact)
    _paragraph(pdf, letter.profile_intro, counts, compact=compact)
    for item in letter.achievements:
        _paragraph(pdf, f"- {item.lead} {item.impact}", counts, compact=compact)
    if letter.problems:
        _paragraph(pdf, letter.problems, counts, compact=compact)
    _paragraph(pdf, letter.closing, counts, compact=compact)
    if letter.language_closing:
        _paragraph(pdf, letter.language_closing, counts, compact=compact)
    return bytes(pdf.output()), counts


async def render_resume_pdf(
    resume: TailoredResume, *, compact: bool = False
) -> tuple[bytes, dict[str, int]]:
    try:
        return _resume_pdf(resume, compact=compact)
    except Exception as exc:
        raise PdfGenerationError(f"Failed to render resume PDF: {exc}") from exc


async def render_cover_letter_pdf(
    letter: CoverLetter, *, compact: bool = False
) -> tuple[bytes, dict[str, int]]:
    try:
        return _cover_letter_pdf(letter, compact=compact)
    except Exception as exc:
        raise PdfGenerationError(f"Failed to render cover letter PDF: {exc}") from exc
