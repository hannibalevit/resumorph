"""Programmatic PDF rendering for tailored resumes and cover letters."""

from pathlib import Path

from fpdf import FPDF, XPos, YPos

from app.schemas import CoverLetter, TailoredResume
from app.text_utils import clean_text, headings_for, split_contact_lines

PDF_MIME_TYPE = "application/pdf"
PDF_FONT_FAMILY = "DejaVu"
_FONT_DIRECTORY = Path(__file__).with_name("assets") / "fonts"


class PdfGenerationError(Exception):
    """Raised when rendering a tailored document to PDF fails."""


class _DocumentPdf(FPDF):
    def header(self) -> None:
        # Documents intentionally have no repeating header.
        return


def _new_pdf(page_format: str) -> _DocumentPdf:
    pdf = _DocumentPdf(format="letter" if page_format == "letter" else "A4", unit="mm")
    pdf.add_font(PDF_FONT_FAMILY, fname=_FONT_DIRECTORY / "DejaVuSans.ttf")
    pdf.add_font(PDF_FONT_FAMILY, style="B", fname=_FONT_DIRECTORY / "DejaVuSans-Bold.ttf")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    return pdf


def _text(value: str | None, counts: dict[str, int]) -> str:
    return clean_text(value, counts)


def _multi_cell(pdf: _DocumentPdf, height: float, text: str) -> None:
    pdf.multi_cell(pdf.epw, height, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _paragraph(pdf: _DocumentPdf, text: str, counts: dict[str, int], *, size: float = 10.5) -> None:
    pdf.set_font(PDF_FONT_FAMILY, size=size)
    _multi_cell(pdf, 5.2, _text(text, counts))
    pdf.ln(1.2)


def _heading(pdf: _DocumentPdf, text: str, counts: dict[str, int]) -> None:
    pdf.ln(2)
    pdf.set_font(PDF_FONT_FAMILY, style="B", size=12)
    _multi_cell(pdf, 6, _text(text, counts))
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)


def _resume_pdf(resume: TailoredResume) -> tuple[bytes, dict[str, int]]:
    counts: dict[str, int] = {}
    pdf = _new_pdf(resume.page_format)
    headings = headings_for(resume.language)

    pdf.set_font(PDF_FONT_FAMILY, style="B", size=18)
    _multi_cell(pdf, 8, _text(resume.candidate_name, counts))
    primary, urls = split_contact_lines(resume.contact_info or "")
    if primary:
        _paragraph(pdf, primary, counts, size=10)
    if urls:
        _paragraph(pdf, urls, counts, size=10)

    if resume.summary.strip():
        _heading(pdf, headings["summary"], counts)
        _paragraph(pdf, resume.summary, counts)
    competencies = [item.strip() for item in resume.competencies if item.strip()]
    if competencies:
        _heading(pdf, headings["competencies"], counts)
        _paragraph(pdf, " | ".join(competencies), counts)
    if resume.experience:
        _heading(pdf, headings["experience"], counts)
        for job in resume.experience:
            pdf.set_font(PDF_FONT_FAMILY, style="B", size=11)
            _multi_cell(pdf, 5.5, _text(job.title, counts))
            company = job.company if not job.dates else f"{job.company} | {job.dates}"
            _paragraph(pdf, company, counts, size=10)
            if job.location:
                _paragraph(pdf, job.location, counts, size=10)
            for bullet in job.bullets:
                if bullet.strip():
                    _paragraph(pdf, f"- {bullet.strip()}", counts)
    if resume.projects:
        _heading(pdf, headings["projects"], counts)
        for project in resume.projects:
            title = f"{project.title} ({project.badge})" if project.badge else project.title
            pdf.set_font(PDF_FONT_FAMILY, style="B", size=11)
            _multi_cell(pdf, 5.5, _text(title, counts))
            if project.description:
                _paragraph(pdf, project.description, counts)
            if project.tech:
                _paragraph(pdf, project.tech, counts, size=10)
    if resume.education:
        _heading(pdf, headings["education"], counts)
        for education in resume.education:
            heading = (
                education.degree if not education.year else f"{education.degree} | {education.year}"
            )
            pdf.set_font(PDF_FONT_FAMILY, style="B", size=11)
            _multi_cell(pdf, 5.5, _text(heading, counts))
            _paragraph(pdf, education.institution, counts, size=10)
            if education.description:
                _paragraph(pdf, education.description, counts)
    if resume.certifications:
        _heading(pdf, headings["certifications"], counts)
        for certification in resume.certifications:
            label = (
                f"{certification.title} - {certification.org}"
                if certification.org
                else certification.title
            )
            if certification.year:
                label = f"{label} | {certification.year}"
            _paragraph(pdf, label, counts)
    if resume.skills:
        _heading(pdf, headings["skills"], counts)
        _paragraph(pdf, ", ".join(item.strip() for item in resume.skills if item.strip()), counts)
    languages = [item for item in resume.languages if item.language.strip()]
    if languages:
        _heading(pdf, headings["languages"], counts)
        _paragraph(
            pdf,
            ", ".join(
                f"{item.language.strip()} ({item.proficiency.strip()})"
                if item.proficiency and item.proficiency.strip()
                else item.language.strip()
                for item in languages
            ),
            counts,
        )

    return bytes(pdf.output()), counts


def _cover_letter_pdf(letter: CoverLetter) -> tuple[bytes, dict[str, int]]:
    counts: dict[str, int] = {}
    pdf = _new_pdf(letter.page_format)
    pdf.set_font(PDF_FONT_FAMILY, style="B", size=18)
    _multi_cell(pdf, 8, _text(letter.candidate_name, counts))
    primary, urls = split_contact_lines(letter.contact_info or "")
    if primary:
        _paragraph(pdf, primary, counts, size=10)
    if urls:
        _paragraph(pdf, urls, counts, size=10)
    credentials = [item.strip() for item in letter.credentials if item.strip()]
    if credentials:
        _paragraph(pdf, " | ".join(credentials), counts, size=10)
    role_line = (
        letter.role_title if not letter.company else f"{letter.role_title} - {letter.company}"
    )
    _paragraph(pdf, role_line, counts, size=11)
    if letter.dateline:
        _paragraph(pdf, letter.dateline, counts)
    _paragraph(pdf, letter.greeting, counts)
    _paragraph(pdf, letter.opening, counts)
    _paragraph(pdf, letter.profile_intro, counts)
    for item in letter.achievements:
        _paragraph(pdf, f"- {item.lead} {item.impact}", counts)
    if letter.problems:
        _paragraph(pdf, letter.problems, counts)
    _paragraph(pdf, letter.closing, counts)
    if letter.language_closing:
        _paragraph(pdf, letter.language_closing, counts)
    return bytes(pdf.output()), counts


async def render_resume_pdf(resume: TailoredResume) -> tuple[bytes, dict[str, int]]:
    try:
        return _resume_pdf(resume)
    except Exception as exc:
        raise PdfGenerationError(f"Failed to render resume PDF: {exc}") from exc


async def render_cover_letter_pdf(letter: CoverLetter) -> tuple[bytes, dict[str, int]]:
    try:
        return _cover_letter_pdf(letter)
    except Exception as exc:
        raise PdfGenerationError(f"Failed to render cover letter PDF: {exc}") from exc
