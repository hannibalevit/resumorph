import pytest
from app.pdf_generator import (
    PdfSectionOrderError,
    normalize_text_for_ats,
    render_cover_letter_pdf,
    render_resume_pdf,
    validate_section_order,
)
from app.schemas import (
    CoverLetter,
    CoverLetterAchievement,
    ResumeExperienceItem,
    TailoredResume,
)


def _resume(**overrides) -> TailoredResume:
    defaults = {
        "candidateName": "Ada Lovelace",
        "contactInfo": "ada@example.com",
        "headline": "Senior Backend Engineer",
        "summary": "Experienced Python engineer.",
        "competencies": ["Distributed systems"],
        "skills": ["Python", "FastAPI"],
        "experience": [
            ResumeExperienceItem(
                company="Acme",
                title="Engineer",
                dates="2020-2024",
                bullets=["Built resilient APIs"],
            )
        ],
    }
    defaults.update(overrides)
    return TailoredResume(**defaults)


def _cover_letter(**overrides) -> CoverLetter:
    defaults = {
        "candidateName": "Ada Lovelace",
        "contactInfo": "ada@example.com",
        "roleTitle": "Backend Engineer",
        "company": "Acme",
        "greeting": "Dear Hiring Manager,",
        "opening": "I am excited to apply.",
        "profileIntro": "I bring years of backend experience.",
        "achievements": [CoverLetterAchievement(lead="Scaled APIs", impact="to 1M users.")],
        "closing": "Thank you for your consideration.",
    }
    defaults.update(overrides)
    return CoverLetter(**defaults)


def test_normalize_text_for_ats_replaces_unicode_in_body_only() -> None:
    html = "<p>Led team — shipped “quality” • fast…</p><style>.a{content:'—'}</style>"

    result, replacements = normalize_text_for_ats(html)

    assert "Led team - shipped" in result
    assert '"quality"' in result
    assert "..." in result
    assert replacements["em-dash"] == 1
    assert replacements["smart-double-quote"] == 2
    assert replacements["ellipsis"] == 1
    # Content inside <style> is masked and left untouched.
    assert "content:'—'" in result


def test_normalize_text_for_ats_handles_currency_and_arrows() -> None:
    _, replacements = normalize_text_for_ats("<p>€10 £5 grew A → B and C ← D</p>")
    assert replacements["euro"] == 1
    assert replacements["pound"] == 1
    assert replacements["right-arrow"] == 1
    assert replacements["left-arrow"] == 1


def test_validate_section_order_accepts_expected_order() -> None:
    html = (
        "<div class='section-title'>Summary</div>"
        "<div class='section-title'>Experience</div>"
        "<div class='section-title'>Education</div>"
    )
    # Should not raise.
    validate_section_order(html)


def test_validate_section_order_rejects_out_of_order_sections() -> None:
    html = "<div class='section-title'>Experience</div><div class='section-title'>Summary</div>"
    with pytest.raises(PdfSectionOrderError):
        validate_section_order(html)


def test_validate_section_order_ignores_when_fewer_than_two_known() -> None:
    validate_section_order("<div class='section-title'>Summary</div>")


async def test_render_resume_pdf_produces_pdf_bytes() -> None:
    pdf_bytes, page_count, replacements = await render_resume_pdf(_resume())

    assert pdf_bytes[:4] == b"%PDF"
    assert page_count >= 1
    assert isinstance(replacements, dict)


async def test_render_resume_pdf_letter_format() -> None:
    pdf_bytes, _, _ = await render_resume_pdf(_resume(pageFormat="letter"))
    assert pdf_bytes[:4] == b"%PDF"


async def test_render_cover_letter_pdf_produces_pdf_bytes() -> None:
    pdf_bytes, page_count, replacements = await render_cover_letter_pdf(_cover_letter())

    assert pdf_bytes[:4] == b"%PDF"
    assert page_count >= 1
    assert isinstance(replacements, dict)
