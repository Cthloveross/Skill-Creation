---
name: patch-druid-javascript-injection
version: 1.0.0
description: Patch Apache Druid source trees affected by CVE-2021-25646, where request JSON can override injected JavaScriptConfig values, then produce a reviewable unified diff and guide the required Maven rebuild.
---

# Patch Druid JavaScript configuration injection

Use this Skill for an Apache Druid source checkout where JavaScript must remain usable when enabled by the administrator, but untrusted Jackson input must never replace the injected `JavaScriptConfig` (including through an empty JSON property name).

## Security invariant

Every reachable Jackson-created consumer of `JavaScriptConfig` must take that value only from the trusted injection context. In particular, `@JacksonInject` metadata for `JavaScriptConfig` must specify `useInput = OptBoolean.FALSE`. Do not solve this by filtering JavaScript source strings, rejecting only the empty property name at an endpoint, or disabling all JavaScript functionality.

## Procedure

1. Confirm the checkout is the required Druid release and clean enough that its diff can be reviewed:
   ```sh
   cd /root/druid
   git status --short
   git describe --tags --always
   ```
2. Run the patch generator. It edits only source files that inject `JavaScriptConfig`, verifies that every such parameter is protected, and writes a standard git unified diff:
   ```sh
   python3 /app/environment/skills/current/scripts/patch_javascript_config.py <<'JSON'
   {"source_root":"/root/druid","patch_path":"/root/patches/druid-cve-2021-25646.patch"}
   JSON
   ```
   The script reads one JSON object from stdin and emits one JSON result on stdout. `source_root` is a Git checkout; `patch_path` is the desired patch file. It fails rather than producing a partial patch when it finds an unrecognized `JavaScriptConfig` injection declaration.
3. Inspect the emitted `changed_files`, `protected_parameters`, `mapper_review_files`, and `unprotected_parameters`. A successful result has a nonempty patch (unless the checkout was already fixed), no unprotected parameters, and no source-generated error. Review the patch with:
   ```sh
   git -C /root/druid diff --check
   git -C /root/druid apply --check /root/patches/druid-cve-2021-25646.patch
   ```
4. Inspect every reported mapper/introspector file. This is mandatory because an application-specific `AnnotationIntrospector` can discard `JacksonInject.Value` metadata while preserving only its identifier. Trace the configured mapper and ensure it returns/delegates the full injectable value, including `useInput=FALSE`; do not retain an override that only returns an injectable ID if it bypasses the annotation's input-use setting. Make the smallest compatible source correction if necessary, regenerate the patch using the same script, and repeat the checks.
5. Add a regression test using Druid's configured mapper (not merely a default `ObjectMapper`): with injected JavaScript disabled, deserialize an exploit-shaped JavaScript filter/aggregator/extraction object containing an explicit empty-name property whose value enables JavaScript. Assert its effective configuration remains disabled or deserialization rejects it. Also retain controls for ordinary non-JavaScript specs and JavaScript when server configuration is enabled.
6. Build with the task-required dependency closure and retain build output in a log:
   ```sh
   cd /root/druid
   mvn clean package -DskipTests -Dcheckstyle.skip=true -Dpmd.skip=true -Dforbiddenapis.skip=true -Dspotbugs.skip=true -Danimal.sniffer.skip=true -Denforcer.skip=true -Djacoco.skip=true -Ddependency-check.skip=true -pl '!web-console' -pl indexing-service -am > /tmp/druid-build.log 2>&1
   ```
   On failure, inspect the tail and the first compiler errors in `/tmp/druid-build.log`; do not change the Maven contract just to suppress a failure. Ensure the generated processing and dependent artifacts are the JARs deployed to the Druid distribution.

## Input/output schema for the helper

Input:

```json
{"source_root":"/path/to/druid","patch_path":"/path/to/output.patch"}
```

Optional `write_patch:false` performs edits and reports the resulting diff without writing it. Output contains `ok`, `changed_files`, `protected_parameters`, `unprotected_parameters`, `mapper_review_files`, `patch_path`, and `error` when applicable. The helper invokes `git diff` to generate the patch, so headers and hunk counts reflect the actual checkout.

## Failure handling

- If the checkout is not a Git work tree, the helper fails; create patches from the actual repository rather than hand-writing stale paths.
- If a `JavaScriptConfig` constructor parameter has no recognizable nearby `@JacksonInject`, stop and inspect its construction path. Do not assume it is safe or silently skip it.
- If imports or annotation syntax differ from the supported Jackson form, make a version-compatible manual correction, then use `git diff` to create the patch.
- A patch that protects only `JavaScriptDimFilter` is insufficient: all discovered JavaScript configuration consumers, including aggregators and extraction functions, need the same invariant.
