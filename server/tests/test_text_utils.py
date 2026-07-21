from app.text_utils import classify_related_link, resume_docx_filename


def test_resume_docx_filename_replaces_spaces_with_underscores() -> None:
    assert resume_docx_filename("Ada Lovelace") == "Ada_Lovelace_Resume.docx"


def test_resume_docx_filename_includes_company_name() -> None:
    assert resume_docx_filename("Ada Lovelace", "Acme Corp") == "Ada_Lovelace_Acme_Corp_Resume.docx"


def test_resume_docx_filename_strips_punctuation() -> None:
    assert (
        resume_docx_filename("Jean-Luc O'Brien, Jr.", "Acme, Inc.")
        == "Jean-Luc_OBrien_Jr_Acme_Inc_Resume.docx"
    )


def test_resume_docx_filename_falls_back_when_company_is_missing() -> None:
    assert resume_docx_filename("Ada Lovelace", None) == "Ada_Lovelace_Resume.docx"
    assert resume_docx_filename("Ada Lovelace", "  ") == "Ada_Lovelace_Resume.docx"


def test_resume_docx_filename_falls_back_when_name_is_blank() -> None:
    assert resume_docx_filename("   ") == "Resume_Resume.docx"


def test_classify_related_link_detects_linkedin() -> None:
    assert classify_related_link("https://www.linkedin.com/company/acme") == "linkedin"


def test_classify_related_link_detects_ats_by_url() -> None:
    assert classify_related_link("https://boards.greenhouse.io/acme/jobs/123") == "ats"


def test_classify_related_link_detects_application_form_by_url() -> None:
    assert classify_related_link("https://jobs.example.com/apply?ref=site") == "application_form"


def test_classify_related_link_detects_application_form_by_text() -> None:
    assert classify_related_link("https://jobs.example.com/x", "Apply now") == "application_form"


def test_classify_related_link_detects_company_jobs_by_text() -> None:
    assert classify_related_link("https://acme.com/careers", "Careers") == "company_jobs"
    assert (
        classify_related_link("https://boards.greenhouse.io/acme", "View all open positions")
        == "company_jobs"
    )


def test_classify_related_link_company_jobs_text_wins_over_ats_url() -> None:
    # A "see all jobs" link hosted on the ATS domain is the company's jobs
    # page, not a generic ATS link — the text match should take priority.
    assert (
        classify_related_link("https://boards.greenhouse.io/acme", "See all jobs") == "company_jobs"
    )


def test_classify_related_link_detects_company_by_exact_name_match() -> None:
    assert classify_related_link("https://acme.com", "Acme Corp", "Acme Corp") == "company"
    assert classify_related_link("https://acme.com", "  acme corp  ", "Acme Corp") == "company"


def test_classify_related_link_detects_company_by_generic_phrase() -> None:
    assert classify_related_link("https://acme.com", "Visit our website") == "company"
    assert classify_related_link("https://acme.com", "About us", "Acme Corp") == "company"


def test_classify_related_link_falls_back_to_other() -> None:
    assert classify_related_link("https://acme.com/blog/post-1", "Read more") == "other"
    assert classify_related_link("https://acme.com", "Acme Corp", "Globex") == "other"
