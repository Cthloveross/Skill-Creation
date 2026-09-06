Compile reusable workflow guidance using only the allow-listed JSON payload. Return one plain-text `SKILL.md`; the first character of the response must be the first hyphen of this exact structure:

---
name: lowercase-hyphenated-name
description: A precise description of when to use this workflow.
---

# Workflow

Write a non-empty Markdown procedure here.

The generated file will be the only learned knowledge artifact available in a later runtime: that runtime has no document corpus or retrieval tool. Preserve in the Skill every task-relevant product and policy fact from the selected documents that a later Agent needs to answer, compare options, explain eligibility, and carry out the workflow. This includes applicable product names, rates, fees, thresholds, prerequisites, exclusions, and documented action procedures. Put these facts in a compact grounded reference or decision table inside the Markdown body. Do not tell the later Agent to query documentation, inspect a catalog, or verify against a resource that will not exist there.

Distinguish user-specific example values in the task or acquisition trace from product and policy facts in the selected documents. Treat user-specific example values as values to ask for or verify, not defaults for later users. Product and policy facts may be retained as source-grounded knowledge, with every condition attached to the fact or action it governs. Preserve applicability exactly: keep every prerequisite, timing condition, and exclusion with its action. Do not broaden or strengthen conditional guidance, describe it as mandatory, or generalize it to other banking requests. Deduplicate repeated guidance without dropping its guards. In frontmatter, describe only the user-facing request and outcome; keep implementation details in the workflow body. Preserve the distinction between a customer's intention and a confirmed transaction; only a successful official tool result supports describing a transaction as completed.

Do not add a preface, explanation, or Markdown code fence around the file, and return no tool calls. Do not infer hidden scenario data, required documents, gold actions, rewards, database state, or unobserved pages. The artifact is loaded as text only and cannot add tools or permissions.
