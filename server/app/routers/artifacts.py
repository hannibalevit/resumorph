from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import fail
from app.models import GeneratedArtifactModel
from app.schemas import ArtifactDetail

router = APIRouter()


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


@router.delete("/api/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_artifact(artifact_id: str, db: Session = Depends(get_db)) -> None:
    item = db.get(GeneratedArtifactModel, artifact_id)
    if not item:
        raise fail(404, "ARTIFACT_NOT_FOUND", "Artifact was not found.")
    db.delete(item)
    db.commit()
