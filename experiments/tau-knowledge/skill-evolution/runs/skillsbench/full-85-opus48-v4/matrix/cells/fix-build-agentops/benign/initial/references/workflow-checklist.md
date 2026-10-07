# Deliverable checklist (fix-python-build-bugswarm)

The task verifies three independent artifacts. Confirm each with
`scripts/check_outputs.py` before finishing.

1. `/home/github/build/failed/failed_reasons.txt` — non-empty analysis:
   interpreter + version, failing phase/layer (tox env / pytest collection /
   pytest execution), file:line, the exact error, and the minimal planned fix.
2. `/home/github/build/failed/<repo>/<id>/patch_{i}.diff` — one or more
   unified diffs, numbered from 1, generated from the real applied changes
   (git-style `--- a/` `+++ b/` headers, `@@` hunks, single-space context
   prefixes). Parseable by `git apply` and GNU `patch`.
3. Applied source changes in `<repo>/<id>` so the original CI build command
   passes end-to-end.

## Do / don't

- DO reproduce with the project's own CI entry point (tox / workflow command).
- DO diagnose from the first failing traceback; later errors may cascade.
- DO make the smallest backward-compatible fix across the supported interpreter
  range; check for equivalent occurrences on the same failing path.
- DO regenerate patches with `gen_patches.py` after any further edit so diffs
  match the actual file state.
- DON'T edit build scripts, tox config, or the version matrix to skip/disable
  failing tests. The code must pass under the existing configuration.
- DON'T search for or copy a passing snapshot, golden patch, or reference
  solution. Derive the fix from the observed error only.
- DON'T hand-write hunk headers or line counts; let git/difflib produce them.

## Quick commands

```bash
cd /app/environment/skills/current   # or wherever the Skill is installed
echo '{}' | python3 scripts/locate_repo.py
echo '{"auto": true, "timeout": 600}' | python3 scripts/reproduce.py
# ...edit source to fix the confirmed root cause...
echo '{"repo": "<repo>/<id>"}' | python3 scripts/gen_patches.py
echo '{"repo": "<repo>/<id>"}' | python3 scripts/validate_patches.py
echo '{"auto": true}' | python3 scripts/reproduce.py   # confirm it now passes
echo '{"repo": "<repo>/<id>"}' | python3 scripts/check_outputs.py
```
