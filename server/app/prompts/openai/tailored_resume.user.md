Create an ATS-optimized tailored resume. Detect the job description's language and write the resume in it; detect the hiring company's paper-format market as instructed.

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
- Education: institutions, degrees, graduation years (only the JSON shape changes — see education_structuring)

Editing scope:
- headline: rewrite to align with the target role
- summary: rebuild around the job's top priorities using only resume facts
- competencies: generate 6-8 short JD-derived phrases, each grounded in real experience
- skills: reorder by job relevance; include only skills demonstrably in the experience
- Most recent role bullets: primary tailoring surface — rewrite and reorder to match requirements
- Second most recent role bullets: adjust only if the most recent alone is insufficient
- Older positions: compress or remove entirely if clearly irrelevant; never remove the most recent role
- Metrics: reuse and reframe only numbers already in the original resume; never invent new ones
- Projects: select only the 3-4 most relevant, structured into title/description/optional badge/optional tech
- Certifications: extract only ones explicitly present in the base resume, structured into title/org/year
- Education: split each entry into institution/degree/year/optional description

Role framing: infer the job's core function/domain fresh from its own text — no fixed archetype list.
Recruiter risk map: silently reason through likely recruiter doubts and the strongest matching evidence for each before drafting; do not include this reasoning in the output JSON.
Six-second clarity gate: the top third (summary + competencies + first job's opening bullets) must make the target role, strongest fit, and one proof point obvious on a skim.

Human voice:
- Vary bullet opening verbs; do not start consecutive bullets with the same word
- One or two concrete lines per bullet; no filler
- The result must read as a human professional wrote it, not an AI

Before returning JSON, silently verify: company names and dates unchanged, contactInfo contains the original contact data, no fabricated facts, no banned words, no em dashes or smart quotes, job keywords present where truthful, competencies/projects/certifications/education populated in the structured shape, language and pageFormat set, schema complete.
