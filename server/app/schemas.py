from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class DetectedFormField(ApiModel):
    field_id: str = Field(alias="fieldId")
    tag_name: str = Field(alias="tagName")
    type: str | None = None
    name: str | None = None
    id: str | None = None
    label: str | None = None
    placeholder: str | None = None
    aria_label: str | None = Field(default=None, alias="ariaLabel")
    nearby_text: str | None = Field(default=None, alias="nearbyText")
    current_value: str | None = Field(default=None, alias="currentValue")
    selector: str = ""
    is_sensitive: bool = Field(default=False, alias="isSensitive")
    is_likely_application_question: bool = Field(default=False, alias="isLikelyApplicationQuestion")


class PageSnapshot(ApiModel):
    url: str
    normalized_url: str = Field(alias="normalizedUrl")
    title: str = ""
    hostname: str = ""
    captured_at: str | None = Field(default=None, alias="capturedAt")
    visible_text: str = Field(alias="visibleText", max_length=80_000)
    selected_text: str | None = Field(default=None, alias="selectedText", max_length=80_000)
    primary_job_text: str | None = Field(default=None, alias="primaryJobText", max_length=80_000)
    primary_job_source: str | None = Field(default=None, alias="primaryJobSource")
    primary_job_confidence: float | None = Field(default=None, alias="primaryJobConfidence")
    detected_company: str | None = Field(default=None, alias="detectedCompany")
    detected_job_title: str | None = Field(default=None, alias="detectedJobTitle")
    detected_location: str | None = Field(default=None, alias="detectedLocation")
    extraction_warnings: list[str] = Field(default_factory=list, alias="extractionWarnings")
    meta: dict[str, str | None] = Field(default_factory=dict)
    json_ld: list[Any] = Field(default_factory=list, alias="jsonLd")
    headings: list[dict[str, Any]] = Field(default_factory=list)
    links: list[dict[str, str]] = Field(default_factory=list)
    form_fields: list[DetectedFormField] = Field(default_factory=list, alias="formFields")
    dom_blocks: list[dict[str, Any]] = Field(default_factory=list, alias="domBlocks")


class CompanyInfo(ApiModel):
    description: str | None = None
    industry: str | None = None
    size: str | None = None
    mission: str | None = None


class JobContext(ApiModel):
    company_name: str | None = Field(default=None, alias="companyName")
    position_title: str | None = Field(default=None, alias="positionTitle")
    location: str | None = None
    employment_type: str | None = Field(default=None, alias="employmentType")
    seniority: str | None = None
    remote_policy: str | None = Field(default=None, alias="remotePolicy")
    salary_range: str | None = Field(default=None, alias="salaryRange")
    job_description: str | None = Field(default=None, alias="jobDescription")
    responsibilities: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list, alias="niceToHave")
    benefits: list[str] = Field(default_factory=list)
    company_info: CompanyInfo = Field(default_factory=CompanyInfo, alias="companyInfo")
    keywords: list[str] = Field(default_factory=list)
    application_hints: list[str] = Field(default_factory=list, alias="applicationHints")
    confidence: float = Field(default=0.0, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)


class ScanRequest(ApiModel):
    page_snapshot: PageSnapshot = Field(alias="pageSnapshot")


class ArtifactSummary(ApiModel):
    id: str
    artifact_type: str = Field(alias="artifactType")
    title: str
    file_name: str | None = Field(default=None, alias="fileName")
    created_at: datetime = Field(alias="createdAt")
    llm_provider: str | None = Field(default=None, alias="llmProvider")
    llm_model: str | None = Field(default=None, alias="llmModel")


class JobSessionSummary(ApiModel):
    id: str
    canonical_job_key: str = Field(alias="canonicalJobKey")
    source_url: str = Field(alias="sourceUrl")
    company_name: str | None = Field(default=None, alias="companyName")
    position_title: str | None = Field(default=None, alias="positionTitle")
    location: str | None = None
    extraction_confidence: float = Field(alias="extractionConfidence")
    updated_at: datetime = Field(alias="updatedAt")
    artifacts: list[ArtifactSummary] = Field(default_factory=list)


class JobSessionDetail(JobSessionSummary):
    normalized_url: str = Field(alias="normalizedUrl")
    hostname: str
    job_context: JobContext = Field(alias="jobContext")
    raw_page_snapshot: dict[str, Any] = Field(alias="rawPageSnapshot")
    created_at: datetime = Field(alias="createdAt")
    last_used_at: datetime = Field(alias="lastUsedAt")


class PageMatchRequest(ApiModel):
    url: str
    title: str = ""
    visible_text_preview: str = Field(default="", alias="visibleTextPreview")


class PageMatchResponse(ApiModel):
    matched: bool
    job_session_id: str | None = Field(default=None, alias="jobSessionId")
    confidence: float = 0.0


class BaseResumeUpload(ApiModel):
    text: str = Field(min_length=20, max_length=150_000)


class BaseResumeResponse(ApiModel):
    text: str
    updated_at: datetime | None = Field(default=None, alias="updatedAt")


class FieldAnswerRequest(ApiModel):
    field: DetectedFormField
    tone: str = "professional"
    max_length: int = Field(default=1200, alias="maxLength", ge=30, le=5000)


class FieldAnswerResponse(ApiModel):
    answer: str
    confidence: float
    needs_user_review: bool = Field(default=True, alias="needsUserReview")
    warnings: list[str] = Field(default_factory=list)


class GenerationNotes(ApiModel):
    keywords_used: list[str] = Field(default_factory=list, alias="keywordsUsed")
    missing_requirements: list[str] = Field(default_factory=list, alias="missingRequirements")
    warnings: list[str] = Field(default_factory=list)


class ArtifactResponse(ApiModel):
    artifact_id: str = Field(alias="artifactId")
    file_name: str = Field(alias="fileName")
    mime_type: str = Field(alias="mimeType")
    base64: str
    notes: GenerationNotes


ProviderName = Literal["openai", "gemini", "claude"]
LlmTaskName = Literal["scan", "resume", "field_answer"]


class ProviderConfigInput(ApiModel):
    api_key: str = Field(alias="apiKey", min_length=8, max_length=500)
    default_model: str | None = Field(default=None, alias="defaultModel", max_length=255)
    available_models: list[str] | None = Field(default=None, alias="availableModels")
    test_after_save: bool = Field(default=False, alias="testAfterSave")


class ProviderModelUpdateInput(ApiModel):
    default_model: str = Field(alias="defaultModel", min_length=1, max_length=255)
    available_models: list[str] | None = Field(default=None, alias="availableModels")


class ProviderTestRequest(ApiModel):
    api_key: str | None = Field(default=None, alias="apiKey")
    model: str | None = None


class ProviderModelsRequest(ApiModel):
    """An API key supplied here is used only for this model-list request."""

    api_key: str | None = Field(default=None, alias="apiKey", min_length=8, max_length=500)
    refresh: bool = False


class ProviderPublicConfig(ApiModel):
    provider: ProviderName
    is_enabled: bool = Field(alias="isEnabled")
    key_mask: str | None = Field(default=None, alias="keyMask")
    default_model: str | None = Field(default=None, alias="defaultModel")
    available_models: list[str] = Field(default_factory=list, alias="availableModels")
    models_updated_at: datetime | None = Field(default=None, alias="modelsUpdatedAt")
    last_test_status: str = Field(alias="lastTestStatus")
    last_test_error: str | None = Field(default=None, alias="lastTestError")
    last_tested_at: datetime | None = Field(default=None, alias="lastTestedAt")
    # "subscription" when the stored Claude secret is a Claude Code OAuth token
    # (CLI subprocess path) rather than a regular Anthropic API key. Always
    # None for providers other than "claude".
    auth_mode: str | None = Field(default=None, alias="authMode")


class TaskLlmSetting(ApiModel):
    task: LlmTaskName
    provider: ProviderName
    model: str
    is_custom: bool = Field(default=False, alias="isCustom")


class ProviderSettingsResponse(ApiModel):
    providers: list[ProviderPublicConfig]
    default_provider: ProviderName | None = Field(default=None, alias="defaultProvider")
    default_model: str | None = Field(default=None, alias="defaultModel")
    task_settings: dict[LlmTaskName, TaskLlmSetting] = Field(
        default_factory=dict, alias="taskSettings"
    )


class SetDefaultLlmRequest(ApiModel):
    provider: ProviderName
    model: str = Field(min_length=1, max_length=255)


class SetTaskLlmRequest(ApiModel):
    task: LlmTaskName
    provider: ProviderName
    model: str = Field(min_length=1, max_length=255)


class ProviderTestResponse(ApiModel):
    provider: ProviderName
    model: str
    status: Literal["success", "failed"]
    latency_ms: int = Field(alias="latencyMs")
    message: str
    raw_text_preview: str | None = Field(default=None, alias="rawTextPreview")
    error_code: str | None = Field(default=None, alias="errorCode")
    details: str | None = None


class RelatedLink(ApiModel):
    id: str
    url: str
    normalized_url: str = Field(alias="normalizedUrl")
    link_type: str = Field(alias="linkType")
    title: str | None = None
    created_at: datetime = Field(alias="createdAt")


class AdminJobStatus(ApiModel):
    scanned: bool
    resume_generated: bool = Field(alias="resumeGenerated")
    cover_letter_generated: bool = Field(alias="coverLetterGenerated")
    field_answers_generated: bool = Field(alias="fieldAnswersGenerated")


class AdminJobSessionItem(ApiModel):
    id: str
    title: str
    company_name: str | None = Field(default=None, alias="companyName")
    position_title: str | None = Field(default=None, alias="positionTitle")
    location: str | None = None
    source_url: str = Field(alias="sourceUrl")
    hostname: str
    status: AdminJobStatus
    llm_provider_used: str | None = Field(default=None, alias="llmProviderUsed")
    llm_model_used: str | None = Field(default=None, alias="llmModelUsed")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class AdminJobListResponse(ApiModel):
    items: list[AdminJobSessionItem]
    total: int


class AdminJobDetail(JobSessionDetail):
    related_links: list[RelatedLink] = Field(default_factory=list, alias="relatedLinks")


class ArtifactDetail(ArtifactSummary):
    content_json: dict[str, Any] = Field(alias="contentJson")
    mime_type: str | None = Field(default=None, alias="mimeType")
    base64_file: str | None = Field(default=None, alias="base64File")


class AdminStats(ApiModel):
    total_job_sessions: int = Field(alias="totalJobSessions")
    total_generated_resumes: int = Field(alias="totalGeneratedResumes")
    total_generated_cover_letters: int = Field(alias="totalGeneratedCoverLetters")
    total_generated_field_answers: int = Field(alias="totalGeneratedFieldAnswers")
    by_provider: dict[str, int] = Field(alias="byProvider")


# Legacy schemas retained for the original /api/generate-resume endpoint.
class JobPage(ApiModel):
    url: str
    title: str
    text: str


class GenerateOptions(ApiModel):
    target_format: Literal["docx"] = Field(default="docx", alias="targetFormat")
    language: Literal["en", "ru"] = "en"


class GenerateResumeRequest(ApiModel):
    base_resume: str = Field(alias="baseResume", min_length=100, max_length=100_000)
    job_page: JobPage = Field(alias="jobPage")
    options: GenerateOptions = Field(default_factory=GenerateOptions)


class ResumeExperienceItem(ApiModel):
    company: str
    title: str
    dates: str | None = None
    location: str | None = None
    bullets: list[str]


class ResumeProjectItem(ApiModel):
    title: str
    badge: str | None = None
    description: str
    tech: str | None = None


class ResumeEducationItem(ApiModel):
    institution: str
    degree: str
    year: str | None = None
    description: str | None = None


class ResumeCertificationItem(ApiModel):
    title: str
    org: str
    year: str | None = None


class ResumeLanguageItem(ApiModel):
    language: str
    proficiency: str | None = None


class ResumeSelfCheck(ApiModel):
    """Mirrors the tailored_resume prompts' <self_check_output> contract.

    Declared as real fields (rather than left to model_config's default
    extra="ignore" behavior) so a false boolean or a detected verbatim-reuse
    phrase is actually visible in the persisted artifact JSON instead of being
    silently dropped on validation.
    """

    companies_and_dates_unchanged: bool = Field(default=True, alias="companiesAndDatesUnchanged")
    contact_info_complete: bool = Field(default=True, alias="contactInfoComplete")
    no_fabricated_facts: bool = Field(default=True, alias="noFabricatedFacts")
    no_employment_gap_created: bool = Field(default=True, alias="noEmploymentGapCreated")
    dates_normalized_mmyyyy: bool = Field(default=True, alias="datesNormalizedMMYYYY")
    language_and_page_format_set: bool = Field(default=True, alias="languageAndPageFormatSet")
    no_repeated_phrase_bridges: bool = Field(default=True, alias="noRepeatedPhraseBridges")
    no_metric_or_concept_fusion: bool = Field(default=True, alias="noMetricOrConceptFusion")
    banned_word_edits_grammatical: bool = Field(default=True, alias="bannedWordEditsGrammatical")
    top_keywords_covered: list[str] = Field(default_factory=list, alias="topKeywordsCovered")
    banned_words_used_from_jd: list[str] = Field(
        default_factory=list, alias="bannedWordsUsedFromJD"
    )
    verbatim_jd_phrases_reused: list[str] = Field(
        default_factory=list, alias="verbatimJdPhrasesReused"
    )


class ResumeNotes(ApiModel):
    detected_job_title: str | None = Field(default=None, alias="detectedJobTitle")
    detected_company: str | None = Field(default=None, alias="detectedCompany")
    keywords_used: list[str] = Field(default_factory=list, alias="keywordsUsed")
    missing_requirements: list[str] = Field(default_factory=list, alias="missingRequirements")
    self_check: ResumeSelfCheck = Field(default_factory=ResumeSelfCheck, alias="selfCheck")


class TailoredResume(ApiModel):
    candidate_name: str = Field(alias="candidateName")
    contact_info: str | None = Field(default=None, alias="contactInfo")
    headline: str
    summary: str
    competencies: list[str] = Field(default_factory=list)
    skills: list[str]
    languages: list[ResumeLanguageItem] = Field(default_factory=list)
    experience: list[ResumeExperienceItem]
    projects: list[ResumeProjectItem] = Field(default_factory=list)
    education: list[ResumeEducationItem] = Field(default_factory=list)
    certifications: list[ResumeCertificationItem] = Field(default_factory=list)
    language: str = "en"
    page_format: Literal["letter", "a4"] = Field(default="a4", alias="pageFormat")
    notes: ResumeNotes = Field(default_factory=ResumeNotes)


class CoverLetterAchievement(ApiModel):
    # "Bold lead phrase, impact sentence with a metric" — the career-ops bullet shape.
    lead: str
    impact: str


class CoverLetter(ApiModel):
    candidate_name: str = Field(alias="candidateName")
    contact_info: str | None = Field(default=None, alias="contactInfo")
    credentials: list[str] = Field(default_factory=list)
    role_title: str = Field(alias="roleTitle")
    company: str | None = None
    dateline: str | None = None
    # min_length on these required fields turns an empty/near-empty LLM response into a
    # loud validation error instead of a silently truncated letter (missing closing/
    # signature but no visible error) - see docx_generator's cover letter renderer.
    greeting: str = Field(min_length=3)
    opening: str = Field(min_length=20)
    profile_intro: str = Field(alias="profileIntro", min_length=20)
    achievements: list[CoverLetterAchievement] = Field(default_factory=list)
    problems: str | None = None
    closing: str = Field(min_length=10)
    language_closing: str | None = Field(default=None, alias="languageClosing")
    page_format: Literal["letter", "a4"] = Field(default="a4", alias="pageFormat")


# Frozen copy of the pre-PDF-port TailoredResume shape, used exclusively by the
# legacy /api/generate-resume endpoint (openai_client.py, resume_generator.py,
# document_generator.py's DOCX renderer) so that endpoint keeps working
# unmodified while TailoredResume evolves for the new HTML/PDF flow.
class LegacyTailoredResume(ApiModel):
    candidate_name: str = Field(alias="candidateName")
    contact_info: str | None = Field(default=None, alias="contactInfo")
    headline: str
    summary: str
    skills: list[str]
    experience: list[ResumeExperienceItem]
    education: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    notes: ResumeNotes = Field(default_factory=ResumeNotes)


class GenerateResumeResponse(ApiModel):
    file_name: str = Field(alias="fileName")
    mime_type: str = Field(alias="mimeType")
    base64: str
    notes: ResumeNotes


class ExtractResumeTextResponse(ApiModel):
    text: str
