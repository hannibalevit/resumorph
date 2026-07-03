Create an ATS-optimized tailored resume. Detect the job's language and write the resume in it; detect the paper-format market from the job's location.

Preserve exactly: candidate name in candidateName; location, contacts, and all URLs in contactInfo; every company name (exact casing), all employment dates, education facts (institution/degree/year values, though the JSON shape is now structured).

Editing scope:
- headline and summary: rewrite for the target role using resume facts
- competencies: 6-8 short JD-derived phrases, grounded in real experience
- skills: reorder by job relevance
- Most recent role bullets: primary surface — rewrite to match requirements
- Second most recent bullets: only if most recent alone is insufficient
- Older positions: remove if clearly irrelevant; never remove the most recent role
- projects: top 3-4 most relevant only, structured (title/description/badge?/tech?)
- certifications: only ones explicitly in the base resume, structured (title/org/year?)
- education: structured (institution/degree/year?/description?)

Rules: mirror job keywords where truthful | standard section order Professional Summary, Core Competencies, Work Experience, Projects, Education, Certifications, Skills | missing requirements → notes.missingRequirements only | no invented metrics or skills | no em dashes (use hyphen) | no AI buzzwords (leverage, synergy, spearheaded, passionate, robust, cutting-edge, results-driven, dynamic, utilize, proven track record, innovative, transformative, facilitated, best practices, etc.) | vary bullet openings | human-sounding prose | zero spelling or grammar errors

Schema:
$tailored_resume_schema

Job:
$job_context_json

Resume:
$base_resume
