Write a cover letter for $role at $company and return it as JSON matching the schema. Today's date is $today; use it in the dateline as "D Month YYYY". Copy the candidate's name and contact details from the resume exactly. Before returning JSON, silently verify: only resume facts used, no invented metrics, no banned words, no em/en dashes, body 350-420 words, 2-4 achievement bullets each with a real metric, schema complete.

<output_schema>
$cover_letter_schema
</output_schema>

<job>
$job_context_json
</job>

<resume>
$base_resume
</resume>
