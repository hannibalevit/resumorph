from app.job_service import (
    compose_scan_page_text,
    extract_context_fallback,
    local_field_answer,
    normalize_url,
)
from app.schemas import JobContext, PageSnapshot


def test_normalize_url_strips_tracking_params_and_fragment() -> None:
    assert (
        normalize_url("HTTPS://Example.COM/jobs/42/?utm_source=ad&foo=bar&ref=feed#details")
        == "https://example.com/jobs/42?foo=bar"
    )


def test_compose_scan_page_text_prefers_selected_text_and_includes_detected_metadata() -> None:
    snapshot = PageSnapshot(
        url="https://example.com/job",
        normalizedUrl="https://example.com/job",
        title="Senior Python Engineer",
        visibleText="Navigation text\nBenefits\nFull page fallback details",
        selectedText="Selected role text with Python and SQL",
        primaryJobText="Primary extraction should be lower priority",
        detectedCompany="Acme",
        detectedJobTitle="Senior Python Engineer",
        detectedLocation="Remote",
    )

    result = compose_scan_page_text(snapshot)

    assert "Company: Acme" in result
    assert "Job title: Senior Python Engineer" in result
    assert "source: selected_text" in result
    assert "Selected role text with Python and SQL" in result
    assert "Full visible page text fallback/context" in result


def test_extract_context_fallback_uses_obvious_page_signals() -> None:
    snapshot = PageSnapshot(
        url="https://example.com/job",
        normalizedUrl="https://example.com/job",
        title="Senior Backend Engineer at Acme",
        hostname="example.com",
        visibleText="""
        Remote, CA

        Responsibilities
        Build Python services
        Lead SQL data improvements

        Requirements
        Python
        Docker

        Benefits
        Healthcare
        """,
        headings=[{"level": 1, "text": "Senior Backend Engineer"}],
    )

    context = extract_context_fallback(snapshot)

    assert context.company_name == "Acme"
    assert context.position_title == "Senior Backend Engineer"
    assert context.location == "Remote, CA"
    assert "Python" in context.keywords
    assert "Docker" in context.keywords
    assert context.confidence == 0.45
    assert context.warnings


def test_local_field_answer_refuses_sensitive_fields() -> None:
    answer = local_field_answer(
        "Social security number",
        "Experienced Python engineer",
        JobContext(companyName="Acme", positionTitle="Engineer"),
        300,
    )

    assert answer.answer == ""
    assert answer.confidence == 0
    assert "sensitive" in answer.warnings[0].lower()


def test_local_field_answer_uses_resume_context_for_motivation_questions() -> None:
    answer = local_field_answer(
        "Why are you interested?",
        "Built Python platforms and mentored engineers.",
        JobContext(companyName="Acme", positionTitle="Backend Engineer"),
        300,
    )

    assert "Backend Engineer" in answer.answer
    assert "Acme" in answer.answer
    assert "Built Python platforms" in answer.answer
    assert answer.needs_user_review is True
