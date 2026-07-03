from datetime import datetime

import app.main as main
import pytest
from app.models import GeneratedArtifactModel, JobRelatedLinkModel, JobSessionModel
from app.schemas import JobContext
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_base_resume_lifecycle(client: TestClient) -> None:
    missing = client.get("/api/profile/base-resume")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NO_BASE_RESUME"

    resume_text = (
        "Senior Python engineer with FastAPI, SQLAlchemy, testing, "
        "and product delivery experience. " * 3
    )
    saved = client.post("/api/profile/base-resume", json={"text": resume_text})
    assert saved.status_code == 200
    assert saved.json()["text"] == resume_text
    assert saved.json()["updatedAt"]

    fetched = client.get("/api/profile/base-resume")
    assert fetched.status_code == 200
    assert fetched.json()["text"] == resume_text

    deleted = client.delete("/api/profile/base-resume")
    assert deleted.status_code == 204
    assert client.get("/api/profile/base-resume").status_code == 404


def test_llm_provider_settings_save_list_and_delete(client: TestClient) -> None:
    saved = client.post(
        "/api/settings/llm-providers/openai",
        json={
            "apiKey": "sk-test-123456",
            "defaultModel": "gpt-test",
            "availableModels": ["gpt-test"],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["provider"] == "openai"
    assert saved.json()["isEnabled"] is True
    assert saved.json()["keyMask"] == "sk-t...3456"
    assert saved.json()["defaultModel"] == "gpt-test"

    settings = client.get("/api/settings/llm-providers")
    assert settings.status_code == 200
    body = settings.json()
    assert body["defaultProvider"] == "openai"
    assert body["defaultModel"] == "gpt-test"
    assert body["taskSettings"]["scan"]["provider"] == "openai"

    deleted = client.delete("/api/settings/llm-providers/openai")
    assert deleted.status_code == 204

    after_delete = client.get("/api/settings/llm-providers")
    assert after_delete.status_code == 200
    openai_config = next(
        item for item in after_delete.json()["providers"] if item["provider"] == "openai"
    )
    assert openai_config["isEnabled"] is False


def test_unsupported_provider_returns_structured_error(client: TestClient) -> None:
    response = client.post(
        "/api/settings/llm-providers/unknown",
        json={"apiKey": "sk-test-123456"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "LLM_PROVIDER_ERROR"


def test_scan_job_uses_mocked_llm_and_upserts_session(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StubProvider:
        async def generate_json(self, *args: object, **kwargs: object) -> dict[str, object]:
            return {
                "companyName": "Acme",
                "positionTitle": "Backend Engineer",
                "location": "Remote",
                "jobDescription": "Build APIs",
                "requirements": ["Python", "SQL"],
                "responsibilities": ["Build services"],
                "keywords": ["Python", "SQL"],
                "confidence": 0.91,
            }

    monkeypatch.setattr(
        main, "resolve_task_llm", lambda db, task: ("openai", "gpt-test", "sk-test")
    )
    monkeypatch.setattr(main, "get_llm_provider", lambda provider: StubProvider())

    payload = {
        "pageSnapshot": {
            "url": "https://jobs.example.com/backend?utm_source=ad",
            "normalizedUrl": "https://jobs.example.com/backend?utm_source=ad",
            "title": "Backend Engineer",
            "hostname": "jobs.example.com",
            "visibleText": "Backend Engineer\nRequirements\nPython\nSQL",
            "links": [
                {"href": "https://jobs.example.com/apply?ref=site", "text": "Apply"},
                {"href": "mailto:jobs@example.com", "text": "Email"},
            ],
        }
    }

    first = client.post("/api/job-sessions/scan", json=payload)
    assert first.status_code == 200
    body = first.json()
    assert body["companyName"] == "Acme"
    assert body["positionTitle"] == "Backend Engineer"
    assert body["extractionConfidence"] == 0.91
    assert body["canonicalJobKey"] == "https://jobs.example.com/backend"

    second = client.post("/api/job-sessions/scan", json=payload)
    assert second.status_code == 200
    assert second.json()["id"] == body["id"]

    db_session.expire_all()
    session = db_session.get(JobSessionModel, body["id"])
    assert session is not None
    assert len(session.related_links) == 1
    assert session.related_links[0].normalized_url == "https://jobs.example.com/apply"


def test_job_session_matching_admin_stats_and_artifacts(
    client: TestClient, db_session: Session
) -> None:
    context = JobContext(
        companyName="Acme", positionTitle="Backend Engineer", location="Remote", confidence=0.8
    )
    session = JobSessionModel(
        canonical_job_key="https://jobs.example.com/backend",
        source_url="https://jobs.example.com/backend?utm_source=ad",
        normalized_url="https://jobs.example.com/backend",
        hostname="jobs.example.com",
        company_name="Acme",
        position_title="Backend Engineer",
        location="Remote",
        job_context_json=context.model_dump(by_alias=True, mode="json"),
        raw_page_snapshot_json={"url": "https://jobs.example.com/backend"},
        extraction_confidence=0.8,
        llm_provider_used="openai",
        llm_model_used="gpt-test",
    )
    db_session.add(session)
    db_session.flush()
    artifact = GeneratedArtifactModel(
        job_session_id=session.id,
        artifact_type="resume",
        title="Resume - Backend Engineer",
        file_name="resume.pdf",
        content_json={"candidateName": "Ada Lovelace"},
        mime_type="application/pdf",
        base64_file="ZmFrZQ==",
        llm_provider="openai",
        llm_model="gpt-test",
        created_at=datetime(2026, 1, 1),
    )
    db_session.add_all(
        [
            artifact,
            JobRelatedLinkModel(
                job_session_id=session.id,
                url="https://jobs.example.com/apply",
                normalized_url="https://jobs.example.com/apply",
                link_type="application_form",
                title="Apply",
            ),
        ]
    )
    db_session.commit()

    exact_match = client.post(
        "/api/job-sessions/match-current-page",
        json={
            "url": "https://jobs.example.com/backend?utm_campaign=newsletter",
            "title": "",
            "visibleTextPreview": "",
        },
    )
    assert exact_match.status_code == 200
    assert exact_match.json() == {"matched": True, "jobSessionId": session.id, "confidence": 1.0}

    admin_list = client.get("/api/admin/job-sessions", params={"search": "Acme"})
    assert admin_list.status_code == 200
    assert admin_list.json()["total"] == 1
    assert admin_list.json()["items"][0]["status"]["resumeGenerated"] is True

    detail = client.get(f"/api/admin/job-sessions/{session.id}")
    assert detail.status_code == 200
    assert detail.json()["relatedLinks"][0]["linkType"] == "application_form"

    artifacts = client.get(f"/api/admin/job-sessions/{session.id}/artifacts")
    assert artifacts.status_code == 200
    assert artifacts.json()[0]["base64File"] == "ZmFrZQ=="

    stats = client.get("/api/admin/stats")
    assert stats.status_code == 200
    assert stats.json()["totalJobSessions"] == 1
    assert stats.json()["totalGeneratedResumes"] == 1
    assert stats.json()["byProvider"]["openai"] == 1
