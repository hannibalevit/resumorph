Create an ATS-optimized tailored resume in English. Put original location, email, phone, and profile URLs in contactInfo. Before returning JSON, silently verify: company names and dates unchanged, contactInfo contains original contact details, no fabricated facts, no banned words, no em dashes, job keywords present where truthful, schema complete.

<output_schema>
$tailored_resume_schema
</output_schema>

<job>
$job_context_json
</job>

<resume>
$base_resume
</resume>
