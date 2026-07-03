---
name: privacy-security-review
description: Use for changes touching resumes, job descriptions, generated artifacts, API keys, encryption, logging, Chrome permissions, CORS, LLM calls, or form-field assistance.
---

# Privacy And Security Review

## Workflow

1. Map the data flow: browser page, extension storage, backend request, database, LLM provider, and generated artifact.
2. Identify sensitive data involved: resumes, job descriptions, answers, API keys, encryption keys, local DB contents, and uploaded files.
3. Confirm data stays local except the minimum required LLM request.
4. Verify API keys remain encrypted at rest with `server/app/security.py` and only masked previews reach clients.
5. Check that no full resume, job text, answer, API key, or encryption key is logged, printed, committed, or exposed in test fixtures.
6. Confirm page scanning and field assistance still require explicit user action.
7. Confirm sensitive fields remain excluded in extension form detection and backend validation.
8. Review CORS and Chrome permissions for least privilege.
9. Review LLM prompts and payloads for unnecessary sensitive data.

## Validation

- Inspect changed code and tests for secret or user-data exposure.
- Run relevant backend and extension tests for the changed area.
- If permissions or CORS changed, explain why the broader access is necessary.

## Common Failure Modes

- Debug logging includes raw resumes, job descriptions, or LLM payloads.
- A UI receives an unmasked API key.
- A content script scans pages without a click.
- Sensitive field filtering is changed on only the frontend or only the backend.
- CORS or manifest permissions are broadened without a feature requirement.
- Test fixtures include realistic private data or secrets.

## Expected Output

Report the reviewed data flows, privacy/security risks found, mitigations applied, validation run, and any residual risk.
