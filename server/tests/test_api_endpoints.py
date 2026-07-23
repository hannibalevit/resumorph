"""Endpoint coverage for the session, artifact, settings and admin routes."""

from io import BytesIO

import app.services.generation as generation
import pytest
from app.models import (
    GeneratedArtifactModel,
    JobSessionModel,
    LlmProviderConfigModel,
    UserProfileModel,
)
from app.routers import legacy as legacy_router
from app.routers import settings as settings_router
from app.schemas import JobContext
from app.security import encrypt_secret
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# A single payload that satisfies TailoredResume, CoverLetter and
# FieldAnswerResponse validation at once (extra keys are ignored).
STUB_GENERATION = {
    "candidateName": "Ada Lovelace",
    "contactInfo": "ada@example.com",
    "headline": "Senior Backend Engineer",
    "summary": "Experienced Python engineer.",
    "competencies": ["Distributed systems"],
    "skills": ["Python", "FastAPI"],
    "experience": [{"company": "Acme", "title": "Engineer", "bullets": ["Built APIs"]}],
    "roleTitle": "Backend Engineer",
    "greeting": "Dear Hiring Manager,",
    "opening": "I am excited to apply.",
    "profileIntro": "I bring years of backend experience.",
    "closing": "Thank you for your consideration.",
    "answer": "Because the mission resonates with me.",
    "confidence": 0.8,
}


class StubProvider:
    async def generate_json(self, *args: object, **kwargs: object) -> dict[str, object]:
        return dict(STUB_GENERATION)

    async def test_connection(self, api_key: str, model: str | None = None) -> dict[str, object]:
        return {"rawTextPreview": "ok"}

    async def list_models(self, api_key: str) -> list[str]:
        return ["gpt-test", "gpt-test-2"]


@pytest.fixture()
def stub_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        generation, "resolve_task_llm", lambda db, task: ("openai", "gpt-test", "sk-test")
    )
    monkeypatch.setattr(generation, "get_llm_provider", lambda provider: StubProvider())


class CapturingStubProvider(StubProvider):
    """Stub provider that also records the rendered user prompt it was called with,
    so tests can assert on exactly what context reached the (fake) LLM call."""

    def __init__(self, sink: list[str]) -> None:
        self.sink = sink

    async def generate_json(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.sink.append(str(args[3]))
        return dict(STUB_GENERATION)


@pytest.fixture()
def captured_prompts(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sink: list[str] = []
    monkeypatch.setattr(
        generation, "resolve_task_llm", lambda db, task: ("openai", "gpt-test", "sk-test")
    )
    monkeypatch.setattr(
        generation, "get_llm_provider", lambda provider: CapturingStubProvider(sink)
    )
    return sink


def _seed_profile(db: Session) -> None:
    db.add(
        UserProfileModel(
            id="local-user",
            base_resume_text="Ada Lovelace\nada@example.com\n"
            + "Senior Python engineer with backend experience. " * 4,
        )
    )
    db.commit()


def _seed_session(db: Session, **overrides: object) -> JobSessionModel:
    context = JobContext(companyName="Acme", positionTitle="Backend Engineer", confidence=0.8)
    session = JobSessionModel(
        canonical_job_key=overrides.get("key", "https://jobs.example.com/backend"),
        source_url="https://jobs.example.com/backend",
        normalized_url=overrides.get("normalized", "https://jobs.example.com/backend"),
        hostname="jobs.example.com",
        company_name="Acme",
        position_title="Backend Engineer",
        location="Remote",
        job_context_json=context.model_dump(by_alias=True, mode="json"),
        raw_page_snapshot_json={"url": "https://jobs.example.com/backend"},
        extraction_confidence=0.8,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _seed_provider(db: Session, provider: str = "openai", model: str = "gpt-test") -> None:
    db.add(
        LlmProviderConfigModel(
            provider=provider,
            encrypted_api_key=encrypt_secret("sk-secret-123456"),
            key_mask="sk-s...3456",
            default_model=model,
            is_enabled=True,
        )
    )
    db.commit()


# ---------------------------------------------------------------------------
# extract-resume-text
# ---------------------------------------------------------------------------


def test_extract_resume_text_endpoint(client: TestClient) -> None:
    document = Document()
    document.add_paragraph("Senior Python engineer with FastAPI and testing experience. " * 3)
    buffer = BytesIO()
    document.save(buffer)

    response = client.post(
        "/api/extract-resume-text",
        files={
            "file": (
                "resume.docx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 200
    assert "Python engineer" in response.json()["text"]


# ---------------------------------------------------------------------------
# resume / cover-letter / field-answer generation
# ---------------------------------------------------------------------------


def test_generate_session_resume(client: TestClient, db_session: Session, stub_llm: None) -> None:
    _seed_profile(db_session)
    session = _seed_session(db_session)

    response = client.post(f"/api/job-sessions/{session.id}/generate-resume")

    assert response.status_code == 200
    body = response.json()
    assert body["fileName"] == "Ada_Lovelace_Acme_Resume.docx"
    assert body["mimeType"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert body["base64"]


def test_generate_session_resume_requires_base_resume(
    client: TestClient, db_session: Session, stub_llm: None
) -> None:
    session = _seed_session(db_session)
    response = client.post(f"/api/job-sessions/{session.id}/generate-resume")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "NO_BASE_RESUME"


def test_generate_session_resume_missing_session(client: TestClient) -> None:
    response = client.post("/api/job-sessions/does-not-exist/generate-resume")
    assert response.status_code == 404


def test_generate_cover_letter(client: TestClient, db_session: Session, stub_llm: None) -> None:
    _seed_profile(db_session)
    session = _seed_session(db_session)

    response = client.post(f"/api/job-sessions/{session.id}/generate-cover-letter")

    assert response.status_code == 200
    assert response.json()["fileName"].endswith(".docx")


def test_generate_cover_letter_uses_latest_tailored_resume(
    client: TestClient, db_session: Session, captured_prompts: list[str]
) -> None:
    """The cover letter should be grounded in the resume already tailored for this
    job session, not the original base resume, once one has been generated."""
    _seed_profile(db_session)
    session = _seed_session(db_session)
    tailored_resume = {
        "candidateName": "Ada Lovelace",
        "headline": "Distinctive Tailored Headline Marker",
        "summary": "Tailored summary emphasizing this job's requirements.",
        "skills": ["Python"],
        "experience": [{"company": "Acme", "title": "Engineer", "bullets": ["Built APIs"]}],
    }
    db_session.add(
        GeneratedArtifactModel(
            job_session_id=session.id,
            artifact_type="resume",
            content_json=tailored_resume,
        )
    )
    db_session.commit()

    response = client.post(f"/api/job-sessions/{session.id}/generate-cover-letter")

    assert response.status_code == 200
    assert captured_prompts
    assert "Distinctive Tailored Headline Marker" in captured_prompts[-1]


def test_generate_cover_letter_falls_back_to_base_resume(
    client: TestClient, db_session: Session, captured_prompts: list[str]
) -> None:
    """Without a previously generated resume artifact, the cover letter should fall
    back to the profile's base resume text, same as field-answer generation does."""
    _seed_profile(db_session)
    session = _seed_session(db_session)

    response = client.post(f"/api/job-sessions/{session.id}/generate-cover-letter")

    assert response.status_code == 200
    assert captured_prompts
    assert "Senior Python engineer with backend experience" in captured_prompts[-1]


def test_generate_field_answer_via_session(
    client: TestClient, db_session: Session, stub_llm: None
) -> None:
    _seed_profile(db_session)
    session = _seed_session(db_session)

    response = client.post(
        f"/api/job-sessions/{session.id}/generate-field-answer",
        json={
            "field": {
                "fieldId": "f1",
                "tagName": "textarea",
                "label": "Why do you want this role?",
            },
            "maxLength": 500,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == STUB_GENERATION["answer"]
    assert body["needsUserReview"] is True


def test_generate_field_answer_rejects_sensitive(
    client: TestClient, db_session: Session, stub_llm: None
) -> None:
    _seed_profile(db_session)
    session = _seed_session(db_session)

    response = client.post(
        f"/api/job-sessions/{session.id}/generate-field-answer",
        json={
            "field": {
                "fieldId": "f1",
                "tagName": "input",
                "label": "SSN",
                "isSensitive": True,
            }
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SENSITIVE_FIELD"


# ---------------------------------------------------------------------------
# job-session listing / retrieval / deletion
# ---------------------------------------------------------------------------


def test_list_and_delete_job_sessions(client: TestClient, db_session: Session) -> None:
    _seed_session(db_session)

    listed = client.get("/api/job-sessions")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    cleared = client.delete("/api/job-sessions")
    assert cleared.status_code == 204
    assert client.get("/api/job-sessions").json() == []


def test_get_and_delete_single_job_session(client: TestClient, db_session: Session) -> None:
    session = _seed_session(db_session)

    fetched = client.get(f"/api/job-sessions/{session.id}")
    assert fetched.status_code == 200
    assert fetched.json()["companyName"] == "Acme"

    deleted = client.delete(f"/api/job-sessions/{session.id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/job-sessions/{session.id}").status_code == 404


def test_get_missing_job_session_returns_404(client: TestClient) -> None:
    assert client.get("/api/job-sessions/missing").status_code == 404
    assert client.delete("/api/job-sessions/missing").status_code == 404


def test_match_current_page_by_title(client: TestClient, db_session: Session) -> None:
    _seed_session(db_session)
    response = client.post(
        "/api/job-sessions/match-current-page",
        json={
            "url": "https://jobs.example.com/apply",
            "title": "Apply: Backend Engineer role",
        },
    )
    assert response.status_code == 200
    assert response.json()["matched"] is True
    assert response.json()["confidence"] == 0.62


def test_match_current_page_by_title_does_not_cross_hostnames(
    client: TestClient, db_session: Session
) -> None:
    # Regression test: an unrelated posting on a different site can share a generic
    # title fragment (e.g. "Backend Engineer") with an old, already-scanned session.
    # Title matching must stay scoped to the same hostname or the side panel silently
    # jumps to the wrong job.
    _seed_session(db_session)
    response = client.post(
        "/api/job-sessions/match-current-page",
        json={
            "url": "https://elsewhere.example.com/apply",
            "title": "Apply: Backend Engineer role",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"matched": False, "jobSessionId": None, "confidence": 0.0}


def test_match_current_page_no_match(client: TestClient) -> None:
    response = client.post(
        "/api/job-sessions/match-current-page",
        json={"url": "https://nowhere.example.com/x", "title": "Unrelated"},
    )
    assert response.json() == {"matched": False, "jobSessionId": None, "confidence": 0.0}


# ---------------------------------------------------------------------------
# artifacts
# ---------------------------------------------------------------------------


def test_get_and_delete_artifact(client: TestClient, db_session: Session) -> None:
    session = _seed_session(db_session)
    artifact = GeneratedArtifactModel(
        job_session_id=session.id,
        artifact_type="resume",
        title="Resume",
        content_json={"candidateName": "Ada"},
    )
    db_session.add(artifact)
    db_session.commit()
    db_session.refresh(artifact)

    fetched = client.get(f"/api/artifacts/{artifact.id}")
    assert fetched.status_code == 200
    assert fetched.json()["contentJson"]["candidateName"] == "Ada"

    assert client.delete(f"/api/artifacts/{artifact.id}").status_code == 204
    assert client.get(f"/api/artifacts/{artifact.id}").status_code == 404


def test_artifact_not_found(client: TestClient) -> None:
    assert client.get("/api/artifacts/missing").status_code == 404
    assert client.delete("/api/artifacts/missing").status_code == 404


# ---------------------------------------------------------------------------
# admin filters
# ---------------------------------------------------------------------------


def test_admin_job_sessions_filters(client: TestClient, db_session: Session) -> None:
    _seed_session(db_session)

    filtered = client.get(
        "/api/admin/job-sessions",
        params={"provider": "openai", "status_filter": "scanned", "sort": "updated_at_asc"},
    )
    assert filtered.status_code == 200
    # No provider recorded on the seeded session, so the provider filter excludes it.
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"] == []


def test_admin_job_detail_and_missing(client: TestClient, db_session: Session) -> None:
    session = _seed_session(db_session)
    detail = client.get(f"/api/admin/job-sessions/{session.id}")
    assert detail.status_code == 200
    assert detail.json()["relatedLinks"] == []
    assert client.get("/api/admin/job-sessions/missing").status_code == 404
    assert client.get("/api/admin/job-sessions/missing/artifacts").status_code == 404


# ---------------------------------------------------------------------------
# provider settings routes
# ---------------------------------------------------------------------------


def test_set_default_and_task_llm(client: TestClient, db_session: Session) -> None:
    _seed_provider(db_session)

    default = client.post(
        "/api/settings/default-llm", json={"provider": "openai", "model": "gpt-test"}
    )
    assert default.status_code == 200
    assert default.json()["defaultProvider"] == "openai"

    task = client.post(
        "/api/settings/task-llm",
        json={"task": "scan", "provider": "openai", "model": "gpt-test-2"},
    )
    assert task.status_code == 200
    assert task.json()["taskSettings"]["scan"]["model"] == "gpt-test-2"
    assert task.json()["taskSettings"]["scan"]["isCustom"] is True

    cleared = client.delete("/api/settings/task-llm/scan")
    assert cleared.status_code == 200
    assert cleared.json()["taskSettings"]["scan"]["isCustom"] is False


def test_set_default_llm_requires_configured_provider(client: TestClient) -> None:
    response = client.post(
        "/api/settings/default-llm", json={"provider": "gemini", "model": "gemini-x"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "LLM_PROVIDER_NOT_CONFIGURED"


def test_clear_task_llm_rejects_unknown_task(client: TestClient) -> None:
    response = client.delete("/api/settings/task-llm/bogus")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LLM_TASK_ERROR"


def test_update_default_model(client: TestClient, db_session: Session) -> None:
    _seed_provider(db_session)
    response = client.post(
        "/api/settings/llm-providers/openai/default-model",
        json={"defaultModel": "gpt-updated", "availableModels": ["gpt-updated"]},
    )
    assert response.status_code == 200
    assert response.json()["defaultModel"] == "gpt-updated"


def test_update_default_model_requires_provider(client: TestClient) -> None:
    response = client.post(
        "/api/settings/llm-providers/openai/default-model", json={"defaultModel": "x"}
    )
    assert response.status_code == 400


def test_list_saved_provider_models(client: TestClient, db_session: Session) -> None:
    _seed_provider(db_session)
    # Config has no cached available_models, so this reaches the provider (stubbed).
    db_session.query(LlmProviderConfigModel).update({"available_models": ["cached-a", "cached-b"]})
    db_session.commit()
    response = client.get("/api/settings/llm-providers/openai/models")
    assert response.status_code == 200
    assert response.json()["models"] == ["cached-a", "cached-b"]


def test_list_provider_models_with_supplied_key(
    client: TestClient, db_session: Session, stub_llm: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings_router, "get_llm_provider", lambda provider: StubProvider())
    response = client.post(
        "/api/settings/llm-providers/openai/models",
        json={"apiKey": "sk-supplied-123456", "refresh": True},
    )
    assert response.status_code == 200
    assert response.json()["models"] == ["gpt-test", "gpt-test-2"]


def test_test_provider_success(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_provider(db_session)
    monkeypatch.setattr(settings_router, "get_llm_provider", lambda provider: StubProvider())
    response = client.post("/api/settings/llm-providers/openai/test", json={"model": "gpt-test"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_test_provider_failure(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_provider(db_session)

    class FailingProvider:
        async def test_connection(
            self, api_key: str, model: str | None = None
        ) -> dict[str, object]:
            raise RuntimeError("bad key")

    monkeypatch.setattr(settings_router, "get_llm_provider", lambda provider: FailingProvider())
    response = client.post("/api/settings/llm-providers/openai/test", json={"model": "gpt-test"})
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["errorCode"] == "LLM_CONNECTION_TEST_FAILED"


def test_test_provider_requires_key(client: TestClient) -> None:
    response = client.post("/api/settings/llm-providers/openai/test", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "LLM_PROVIDER_NOT_CONFIGURED"


def test_test_provider_claude_without_explicit_model_uses_default(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    class CapturingProvider(StubProvider):
        async def test_connection(
            self, api_key: str, model: str | None = None
        ) -> dict[str, object]:
            captured["model"] = model
            return {"rawTextPreview": "ok"}

    monkeypatch.setattr(settings_router, "get_llm_provider", lambda provider: CapturingProvider())
    response = client.post(
        "/api/settings/llm-providers/claude/test",
        json={"apiKey": "sk-ant-api03-regular-key-1234567890"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert captured["model"] == "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# legacy generate-resume endpoint
# ---------------------------------------------------------------------------


def test_legacy_generate_resume(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.schemas import LegacyTailoredResume, ResumeExperienceItem

    async def fake_create(payload: object) -> LegacyTailoredResume:
        return LegacyTailoredResume(
            candidateName="Ada Lovelace",
            headline="Engineer",
            summary="Summary",
            skills=["Python"],
            experience=[ResumeExperienceItem(company="Acme", title="Eng", bullets=["Work"])],
        )

    monkeypatch.setattr(legacy_router, "create_tailored_resume", fake_create)
    response = client.post(
        "/api/generate-resume",
        json={
            "baseResume": "Ada Lovelace, senior Python engineer. " * 5,
            "jobPage": {"url": "https://x.com", "title": "Engineer", "text": "Build APIs"},
        },
    )
    assert response.status_code == 200
    assert response.json()["fileName"] == "tailored-resume.docx"


def test_legacy_generate_resume_rejects_empty_job_text(client: TestClient) -> None:
    response = client.post(
        "/api/generate-resume",
        json={
            "baseResume": "Ada Lovelace, senior Python engineer. " * 5,
            "jobPage": {"url": "https://x.com", "title": "Engineer", "text": "   "},
        },
    )
    assert response.status_code == 422
