Answer this application field: "$question"

<rules>
- Max $max_length characters
- If evidence is missing, return a short editable placeholder with a warning
</rules>

<context>
Field type: $field_type
Placeholder hint: $placeholder
Nearby form text: $nearby_text
Current value: $current_value
</context>

<output_schema>
$field_answer_schema
</output_schema>

<job>
$job_context_json
</job>

<resume>
$resume
</resume>