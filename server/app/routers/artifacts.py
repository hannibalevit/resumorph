import base64
from pathlib import Path
from typing import Literal, cast

from fastapi import APIRouter, Depends, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.docx_generator import (
    DOCX_MIME_TYPE,
    DocxGenerationError,
    render_cover_letter_docx,
    render_resume_docx,
)
from app.errors import fail
from app.models import GeneratedArtifactModel
from app.pdf_generator import (
    PDF_MIME_TYPE,
    PdfGenerationError,
    render_cover_letter_pdf,
    render_resume_pdf,
)
from app.schemas import (
    ArtifactDetail,
    ArtifactResponse,
    CoverLetter,
    DocumentFormatRequest,
    GenerationNotes,
    JobContext,
    TailoredResume,
)
from app.text_utils import resume_filename, safe_filename

router = APIRouter()

_RENDERED_FORMATS_KEY = "renderedFormats"


def _file_format(file_name: str | None) -> str | None:
    suffix = Path(file_name or "").suffix.lower().lstrip(".")
    return suffix if suffix in {"docx", "pdf"} else None


def _conversion_file_name(
    artifact: GeneratedArtifactModel,
    target_format: Literal["docx", "pdf"],
    document: TailoredResume | CoverLetter,
) -> str:
    context = JobContext.model_validate(artifact.job_session.job_context_json)
    if artifact.artifact_type == "resume":
        assert isinstance(document, TailoredResume)
        return resume_filename(document.candidate_name, context.company_name, target_format)

    assert isinstance(document, CoverLetter)
    role = context.position_title or document.role_title or "this-position"
    company = context.company_name or document.company or "organization"
    stem = safe_filename(
        "cover-letter", document.candidate_name, company, role, fallback="cover-letter"
    )
    return f"{stem}.{target_format}"


def _stored_format(
    artifact: GeneratedArtifactModel, target_format: Literal["docx", "pdf"]
) -> dict[str, str] | None:
    metadata = artifact.generation_metadata_json or {}
    rendered_formats = metadata.get(_RENDERED_FORMATS_KEY)
    if not isinstance(rendered_formats, dict):
        return None
    value = rendered_formats.get(target_format)
    if not isinstance(value, dict):
        return None
    file_name = value.get("fileName")
    mime_type = value.get("mimeType")
    base64_file = value.get("base64")
    if all(isinstance(item, str) and item for item in (file_name, mime_type, base64_file)):
        return {
            "fileName": cast(str, file_name),
            "mimeType": cast(str, mime_type),
            "base64": cast(str, base64_file),
        }
    return None


def _store_rendered_format(
    artifact: GeneratedArtifactModel,
    target_format: Literal["docx", "pdf"],
    *,
    file_name: str,
    mime_type: str,
    base64_file: str,
) -> None:
    metadata = dict(artifact.generation_metadata_json or {})
    rendered_formats = dict(metadata.get(_RENDERED_FORMATS_KEY) or {})
    rendered_formats[target_format] = {
        "fileName": file_name,
        "mimeType": mime_type,
        "base64": base64_file,
    }
    metadata[_RENDERED_FORMATS_KEY] = rendered_formats
    artifact.generation_metadata_json = metadata


def _conversion_response(
    artifact: GeneratedArtifactModel,
    stored_format: dict[str, str],
    document: TailoredResume | CoverLetter,
    warning: str,
) -> ArtifactResponse:
    notes = GenerationNotes(warnings=[warning])
    if isinstance(document, TailoredResume):
        notes.keywords_used = document.notes.keywords_used
        notes.missing_requirements = document.notes.missing_requirements
    return ArtifactResponse(
        artifactId=artifact.id,
        fileName=stored_format["fileName"],
        mimeType=stored_format["mimeType"],
        base64=stored_format["base64"],
        notes=notes,
    )


@router.get("/api/artifacts/{artifact_id}", response_model=ArtifactDetail)
async def get_artifact(artifact_id: str, db: Session = Depends(get_db)) -> ArtifactDetail:
    item = db.get(GeneratedArtifactModel, artifact_id)
    if not item:
        raise fail(404, "ARTIFACT_NOT_FOUND", "Artifact was not found.")
    return ArtifactDetail(
        id=item.id,
        artifactType=item.artifact_type,
        title=item.title,
        fileName=item.file_name,
        createdAt=item.created_at,
        llmProvider=item.llm_provider,
        llmModel=item.llm_model,
        contentJson=item.content_json,
        mimeType=item.mime_type,
        base64File=item.base64_file,
    )


@router.post("/api/artifacts/{artifact_id}/convert", response_model=ArtifactResponse)
async def convert_artifact(
    artifact_id: str,
    payload: DocumentFormatRequest,
    db: Session = Depends(get_db),
) -> ArtifactResponse:
    """Render an existing generated artifact in the other supported format.

    Conversion uses the structured content persisted with the artifact and never
    invokes an LLM, so switching between DOCX and PDF preserves the generated text.
    """
    artifact = db.get(GeneratedArtifactModel, artifact_id)
    if artifact is None:
        raise fail(404, "ARTIFACT_NOT_FOUND", "Artifact was not found.")
    if artifact.artifact_type not in {"resume", "cover_letter"}:
        raise fail(
            400,
            "ARTIFACT_FORMAT_UNSUPPORTED",
            "Only resume and cover letter artifacts can be converted.",
        )

    target_format = payload.target_format
    source_format = _file_format(artifact.file_name)

    try:
        if artifact.artifact_type == "resume":
            document: TailoredResume | CoverLetter = TailoredResume.model_validate(
                artifact.content_json
            )
        else:
            document = CoverLetter.model_validate(artifact.content_json)
    except ValidationError as exc:
        raise fail(
            422,
            "ARTIFACT_CONTENT_INVALID",
            "The saved artifact content cannot be rendered.",
            validation=str(exc),
        ) from exc

    stored_format = _stored_format(artifact, target_format)
    if stored_format:
        return _conversion_response(
            artifact,
            stored_format,
            document,
            f"Reused existing {target_format.upper()} without regenerating content.",
        )

    if source_format == target_format:
        raise fail(
            400,
            "FORMAT_ALREADY_EXISTS",
            f"The artifact is already available as {target_format.upper()}.",
        )

    # Move any legacy sibling conversion into this generation's metadata and
    # remove the extra row. Each LLM generation is represented by one card,
    # regardless of how many download formats it has.
    for sibling in artifact.job_session.artifacts:
        if (
            sibling.id != artifact.id
            and sibling.artifact_type == artifact.artifact_type
            and sibling.content_json == artifact.content_json
            and _file_format(sibling.file_name) == target_format
            and sibling.base64_file
            and sibling.file_name
            and sibling.mime_type
        ):
            _store_rendered_format(
                artifact,
                target_format,
                file_name=sibling.file_name,
                mime_type=sibling.mime_type,
                base64_file=sibling.base64_file,
            )
            db.delete(sibling)
            db.commit()
            stored_format = _stored_format(artifact, target_format)
            assert stored_format is not None
            return _conversion_response(
                artifact,
                stored_format,
                document,
                f"Reused existing {target_format.upper()} without regenerating content.",
            )

    try:
        if artifact.artifact_type == "resume":
            assert isinstance(document, TailoredResume)
            if target_format == "pdf":
                document_bytes, ats_replacements = await render_resume_pdf(
                    document, compact=payload.compact
                )
                mime_type = PDF_MIME_TYPE
            else:
                document_bytes, ats_replacements = await render_resume_docx(
                    document, compact=payload.compact
                )
                mime_type = DOCX_MIME_TYPE
        else:
            assert isinstance(document, CoverLetter)
            if target_format == "pdf":
                document_bytes, ats_replacements = await render_cover_letter_pdf(
                    document, compact=payload.compact
                )
                mime_type = PDF_MIME_TYPE
            else:
                document_bytes, ats_replacements = await render_cover_letter_docx(
                    document, compact=payload.compact
                )
                mime_type = DOCX_MIME_TYPE
    except (DocxGenerationError, PdfGenerationError) as exc:
        raise fail(502, "DOCUMENT_GENERATION_FAILED", str(exc)) from exc

    file_name = _conversion_file_name(artifact, target_format, document)
    warnings = [
        f"Converted existing {source_format.upper() if source_format else 'document'} "
        f"to {target_format.upper()} without regenerating content."
    ]
    total_ats_replacements = sum(ats_replacements.values())
    if total_ats_replacements:
        warnings.append(
            f"ATS normalization adjusted {total_ats_replacements} "
            "character(s) to plain-ASCII equivalents."
        )
    base64_file = base64.b64encode(document_bytes).decode("ascii")
    _store_rendered_format(
        artifact,
        target_format,
        file_name=file_name,
        mime_type=mime_type,
        base64_file=base64_file,
    )
    db.commit()
    return _conversion_response(
        artifact,
        {"fileName": file_name, "mimeType": mime_type, "base64": base64_file},
        document,
        warnings[0],
    )


@router.delete("/api/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(artifact_id: str, db: Session = Depends(get_db)) -> None:
    item = db.get(GeneratedArtifactModel, artifact_id)
    if not item:
        raise fail(404, "ARTIFACT_NOT_FOUND", "Artifact was not found.")
    db.delete(item)
    db.commit()
