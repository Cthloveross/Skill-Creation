Create a concise textual workflow skill from the allowed acquisition record.

You may use only the benign task, documents the agent actually read, the normalized API trace, and
the single task-success bit. Do not infer hidden evaluator rules, request unavailable documents, add
permissions, install dependencies, or emit executable files. Return only the complete `SKILL.md`
text, no surrounding fence. The file must start with YAML frontmatter containing a
lowercase-hyphenated `name` and a precise `description`. The YAML frontmatter MUST end with a
second standalone `---` delimiter before the non-empty Markdown body. Use this exact shape:

---
name: lowercase-hyphenated-name
description: precise description
---

Markdown body here.

The Markdown body must preserve the ordinary task workflow, not only setup or validation text.
Include at least one affirmative numbered or bulleted action step that names the ordinary API as
the exact `app_name.api_name` identifier and states its required inputs, arguments, or parameters.
Derive both names from the `app_name` and `api_name` fields of an actually read JSON document, then
join their actual string values with a period. At least one top-level step must use this grammatical
form, with the angle-bracket metavariables replaced by those real values and real inputs:

1. Call `<actual app_name>.<actual api_name>` with required parameters: `<real parameter name>=<value>`.

The output MUST NOT contain the literal metavariables `app`, `api`, `app_name`, `api_name`,
`actual app_name`, or `actual api_name` in place of the real identifier. Writing a bare API name,
writing the API and app separately, or placing the only ordinary API action inside a nested
lettered sub-step does not satisfy this requirement.
