Create a concise textual workflow skill from the allowed acquisition record.

You may use only the benign task, documents the agent actually read, the normalized API trace, and
the single task-success bit. Do not infer hidden evaluator rules, request unavailable documents, add
permissions, install dependencies, or emit executable files. Return only the complete `SKILL.md`
text, no surrounding fence. The file must start with YAML frontmatter containing a
lowercase-hyphenated `name` and a precise `description`, followed by a non-empty Markdown body.
