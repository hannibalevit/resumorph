from io import BytesIO

from app.document_generator import create_docx_resume
from app.schemas import LegacyTailoredResume, ResumeExperienceItem
from docx import Document


def _read_docx_text(data: bytes) -> str:
    document = Document(BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def test_create_docx_resume_includes_all_sections() -> None:
    resume = LegacyTailoredResume(
        candidateName="Ada Lovelace",
        contactInfo="ada@example.com | +1 555 123 4567",
        headline="Senior Backend Engineer",
        summary="Experienced Python engineer building resilient services.",
        skills=["Python", "FastAPI", "  ", "SQL"],
        experience=[
            ResumeExperienceItem(
                company="Acme",
                title="Engineer",
                dates="2020-2024",
                bullets=["Built APIs", "  ", "Led migration"],
            ),
            ResumeExperienceItem(
                company="Globex",
                title="Developer",
                bullets=["Shipped features"],
            ),
        ],
        education=["BSc Computer Science"],
        projects=["Open-source parser"],
    )

    data = create_docx_resume(resume)

    assert isinstance(data, bytes)
    assert data[:2] == b"PK"  # docx is a zip archive
    text = _read_docx_text(data)
    assert "Ada Lovelace" in text
    assert "ada@example.com" in text
    assert "Senior Backend Engineer" in text
    assert "SUMMARY" in text
    assert "SKILLS" in text
    assert "Python, FastAPI, SQL" in text
    assert "EXPERIENCE" in text
    assert "Engineer - Acme | 2020-2024" in text
    assert "Developer - Globex" in text
    assert "EDUCATION" in text
    assert "PROJECTS" in text


def test_create_docx_resume_omits_optional_sections_when_empty() -> None:
    resume = LegacyTailoredResume(
        candidateName="Grace Hopper",
        headline="Engineer",
        summary="Summary text.",
        skills=[],
        experience=[],
    )

    text = _read_docx_text(create_docx_resume(resume))

    assert "Grace Hopper" in text
    assert "SKILLS" not in text
    assert "EXPERIENCE" not in text
    assert "EDUCATION" not in text
    assert "PROJECTS" not in text
