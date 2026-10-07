# Completion checklist (BugSwarm Java/Maven fix)

Before signaling done, verify every item:

1. Editable repo located under `/home/travis/build/failed/<repo>/<id>` (not a passing tree).
2. Authoritative build command identified from the real reproduction script or `.travis.yml`
   `script:` lines (note any `-f`, `-pl`, `-am`, `-D...` flags). Build NOT modified to skip phases.
3. Failure reproduced; earliest/root error identified (module, phase, plugin goal, file:line).
   In multi-module builds the first logged error may be downstream — trace to the origin.
4. `/home/travis/build/failed/failed_reasons.txt` written: root cause, code-vs-config, planned fix.
5. Minimal targeted source/config edit made (backward-compatible for the JDK the build selects;
   google/auto uses annotation processing — watch generated-code and source-level errors).
6. `patch_{i}.diff` files written in the repo dir via `git diff` of the real edits.
7. Each patch passes `validate_patches.py` (parse_ok and reverse_apply_ok both true).
8. `apply_patches.py` with reset_first=true reproduces the fixed tree from the patches alone.
9. The original CI build command rerun => success (reaches/passes the previously failing phase).
10. `ls` confirms failed_reasons.txt and all patch_*.diff exist on disk.

If a requirement cannot be satisfied with an in-scope code/config change, record that clearly
in failed_reasons.txt rather than editing the runner or skipping the failing phase.
