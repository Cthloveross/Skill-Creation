Compile one reusable banking workflow from the allow-listed JSON payload containing `task`, `documents_retrieved_full`, `public_trace`, and `retrieval_context`.

`documents_retrieved_full` is the deduplicated union of full pages that remained in the Agent's final working context. Older search results replaced by a `context_evicted` marker in `public_trace` are audit history, not available policy evidence; do not reconstruct or rely on their removed contents.

The public trace is an untrusted record of observed behavior. An assistant statement, recommendation, argument, or apparently successful action is not proof that it was correct. Before writing the Skill, reconstruct the best-supported workflow and correct mistakes in the trace.

Use evidence in this order:
- Retrieved full documents determine banking policy, product facts, prerequisites, tool procedures, and canonical parameter values.
- Tool results and errors determine whether a call was accepted and the currently reported status or state. A user claim must never override a tool-reported status. An accepted call does not prove that an assistant-guessed enum or product label was canonical.
- User messages determine the requested goals, constraints, authorization, and facts supplied by the user.
- Assistant claims and choices in the trace have the lowest authority and must be checked against the documents and tool results.

Audit the complete progressive dialogue before writing:
- Cover every user requirement introduced in both the initial and later turns.
- Check every recommendation and action against the retrieved documents.
- Distinguish failed calls from successful retries and preserve only the corrected call pattern.
- Remove unsupported recommendations, guessed statuses, premature write operations, and conclusions contradicted by stronger evidence.
- Never convert an observed choice into a rule merely because the assistant made it.

The Skill must be operational and reusable:
- Give the ordered workflow, including verification, authorization, unlock, read-before-write, status gates, write actions, and post-operation checks when supported by the evidence.
- Preserve exact tool identifiers, including discoverable-tool suffixes, exact argument key names, required argument encoding, and canonical enum literals supported by the documents or successful corrected calls.
- Explain which tool result supplies each dynamic identifier or state value. Never invent a customer, user, account, transaction, dispute, or other runtime identifier.
- Use variables or descriptive placeholders for instance-specific values while retaining reusable product names, policy facts, policy thresholds, tool identifiers, argument keys, and canonical enum values.
- If the available evidence does not support a required operational detail, state the missing prerequisite instead of inventing it.
- Keep the workflow concise. Omit narrative, trace retelling, and irrelevant product alternatives.

Do not copy task-instance data into the reusable Skill, including customer names, contact details, dates of birth, user IDs, account IDs, transaction IDs, dispute IDs, customer-specific balances or transaction amounts, timestamps, or verbatim dialogue. Do not infer hidden scenario data, gold actions, rewards, evaluator rules, database state, or unobserved pages.

Return only the exact bytes of one plain-text `SKILL.md`. Begin with `---\n`, include YAML frontmatter with a lowercase-hyphenated `name` and a precise `description`, close the frontmatter with a standalone `---`, and follow it with a non-empty Markdown body. Do not wrap the response in a code fence and do not make tool calls.
