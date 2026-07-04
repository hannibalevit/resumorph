from app.text_utils import resume_docx_filename


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
