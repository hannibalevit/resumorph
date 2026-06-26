Create an ATS-optimized tailored resume in English.

Schema:
$tailored_resume_schema

Job context:
$job_context_json

Base resume:
$base_resume

---
Preserve exactly (zero changes allowed):
- Candidate name in candidateName
- Location, email, phone, and all profile URLs in contactInfo
- Every company name — exact spelling and casing
- All employment dates and year ranges
- Education: institutions, degrees, graduation years

Editing scope:
- headline: rewrite to align with the target role
- summary: rebuild around the job's top priorities using only resume facts
- skills: reorder by job relevance; include only skills demonstrably in the experience
- Most recent role bullets: primary tailoring surface — rewrite and reorder to match requirements
- Second most recent role bullets: adjust only if the most recent alone is insufficient
- Older positions: compress or remove entirely if clearly irrelevant; never remove the most recent role
- Metrics: reuse and reframe only numbers already in the original resume; never invent new ones

Human voice:
- Vary bullet opening verbs; do not start consecutive bullets with the same word
- One or two concrete lines per bullet; no filler
- The result must read as a human professional wrote it, not an AI

Before returning JSON, silently verify: company names and dates unchanged, contactInfo contains the original contact data, no fabricated facts, no banned words, no em dashes or smart quotes, job keywords present where truthful, schema complete.
