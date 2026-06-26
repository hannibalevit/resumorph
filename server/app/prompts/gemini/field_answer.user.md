Answer: "$question"

Detect question type: technical (tools/code/methods) → specific tech answer from resume | behavioral → one brief concrete example | motivational → 1-2 genuine facts | factual → exact value or placeholder.

Rules: answer this question only | max $max_length chars | every sentence = concrete fact, no abstract phrases | no em dashes (use hyphen) | no AI filler ("Certainly", "passionate about", "proven track record", "leverage") | natural prose, no bullet lists | vary sentence starts (not all "I") | evidence missing → short editable placeholder + warning

Schema:
$field_answer_schema

Type: $field_type | Hint: $placeholder | Nearby: $nearby_text | Current: $current_value

Job:
$job_context_json

Tailored resume:
$resume