Write a cover letter for $role at $company as JSON matching the schema. Today's date is $today; use it in the dateline as "D Month YYYY". Copy name and contact details from the resume exactly. Ground every skill/achievement in the resume; never invent metrics; keep closing non-empty.

<output_schema>
$cover_letter_schema
</output_schema>

<job>
$job_context_json
</job>

<resume>
$resume
</resume>
