Write a cover letter for $role at $company and return it as JSON matching the schema. Today's date is $today; use it in the dateline as "D Month YYYY". Copy the candidate's name and contact details from the resume exactly. Before returning JSON, silently verify: every skill/tool/achievement mentioned is grounded in a quoted resume phrase (else omit it), no invented metrics, no fused metrics or fused JD/industry concepts, no banned words (and any substitution is a full phrase rewrite, re-checked for grammatical completeness), no JD sentence structure/list order/verb mirroring, no 3+ word connective phrase repeated within the letter or copied from the job description, no em/en dashes, body 350-420 words, 2-4 achievement bullets each with a real metric, closing is a real non-empty 1-2 sentence close (never blank, never omitted - the letter must not stop right after achievements/problems), schema complete.

<output_schema>
$cover_letter_schema
</output_schema>

<job>
$job_context_json
</job>

<resume>
$resume
</resume>
