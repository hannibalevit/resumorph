Create a tailored resume in $language_name for the job page below.

Rules:
- Return only data compatible with the TailoredResume schema.
- Preserve candidate name in candidateName; preserve location, email, phone, and profile URLs in contactInfo.
- Preserve employer names, exact employment dates, education facts, and languages from the base resume.
- Do not invent experience, companies, titles, dates, education, certifications, achievements, contact details, or metrics.
- Use only facts present in the base resume.
- Adapt truthful wording to the job description and emphasize relevant experience and skills.
- Reorder skills so the most relevant skills come first.
- Rewrite and reorder bullets for the most recent role as the main tailoring surface.
- Adjust the second most recent role only if needed.
- Compress older roles when clearly irrelevant, but avoid creating visible employment gaps.
- Never remove the most recent role.
- If the job requires skills or experience absent from the base resume, do not claim them.
- Put absent requirements in notes.missingRequirements.
- Mirror exact job keywords and casing where truthful.
- Avoid AI-cliche words: leverage, spearheaded, delve, robust, seamless, cutting-edge, passionate, results-driven, dynamic, synergy, utilize, proven track record.
- Do not use em dashes, en dashes, curly quotes, or decorative punctuation.
- Keep bullets concise, concrete, and interview-defensible.

Base resume:
$base_resume

Job page:
URL: $job_url
Title: $job_title
Text:
$job_text

Before returning, silently verify:
- preserved facts are unchanged;
- no fabricated facts or metrics;
- no banned AI-cliche words;
- job keywords are present where truthful;
- schema fields are valid.
