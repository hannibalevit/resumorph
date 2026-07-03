---
name: chrome-extension-review
description: Use for extension changes involving MV3 entry points, content scripts, job extraction, storage, side panel UI, inline field assistance, manifest permissions, or backend API calls.
---

# Chrome Extension Review

## Workflow

1. Identify the MV3 entry point affected: background service worker, content script, popup, upload UI, or side panel.
2. Use `extension/src/shared/apiClient.ts` for backend calls and `extension/src/shared/storage.ts` for persisted preferences.
3. Preserve `apiBaseUrl` configurability through `getApiBaseUrl()`.
4. For job extraction changes, follow the cascade in `content/jobExtraction/extractJobFromPage.ts`: selected text, JSON-LD, site extractor, DOM scoring, visible text.
5. For a new job site, add a site extractor under `siteExtractors/` and register it in `siteExtractors/index.ts`.
6. Preserve explicit user action before page scanning and inline AI assistance.
7. Preserve sensitive-field exclusions in `formDetector.ts`, `inlineAssistant.ts`, and the backend endpoint.
8. Avoid new manifest permissions unless required and documented.
9. Keep React UI state local unless an existing shared helper is the right boundary.

## Validation

Run from `extension/`:

```bash
npm test
npm run build
```

If backend API contracts changed, also run the backend checks from `server/`.

## Common Failure Modes

- Direct `fetch` calls bypass `apiClient.ts`.
- The backend URL is hardcoded.
- A content script scans without user intent.
- Form assistance appears on sensitive fields.
- A new site extractor is not registered.
- `npm run build` fails because TypeScript strict mode catches unused symbols or contract drift.

## Expected Output

Report changed entry points, data-flow changes, permissions impact, tests/build results, and any manual Chrome reload or smoke-test notes.
