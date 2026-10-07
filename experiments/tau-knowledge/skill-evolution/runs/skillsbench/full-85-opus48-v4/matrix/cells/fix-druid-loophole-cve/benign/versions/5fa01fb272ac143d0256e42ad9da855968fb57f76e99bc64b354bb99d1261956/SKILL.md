---
name: fix-druid-cve-2021-25646
description: Patch, rebuild, and deploy Apache Druid 0.20.0 to close CVE-2021-25646 (empty-key "" Jackson injection that overrides druid.javascript.enabled and allows arbitrary code execution via the /druid/indexer/v1/sampler JavaScript filter). Use when a task provides a Druid 0.20.0 git source tree at /root/druid, requires patch files in /root/patches/, a Maven rebuild, and a deployed JAR that blocks the exploit while keeping legitimate (non-JS and admin-enabled-JS) requests working.
---

# Fix Apache Druid CVE-2021-25646

## What the vulnerability is

Druid parses ingestion specs with Jackson polymorphic deserialization. Classes that
use JavaScript (e.g. `JavaScriptDimFilter`, `JavaScriptAggregatorFactory`,
`JavaScriptExtractionFn`) take a `JavaScriptConfig` whose `enabled` flag is meant to
come **only** from Guice dependency injection (server config
`druid.javascript.enabled`, default `false`). The attack adds an **empty-string key**
`""` with value `{"enabled": true}` to the filter JSON. Jackson deserializes that into
the injected `JavaScriptConfig` parameter, replacing the server value with
`enabled=true`, then runs the attacker's `function` on the JVM (RCE).

## The correct, root-cause fix (covers all JS classes at once)

The real defect is that Druid's custom `GuiceAnnotationIntrospector` only supplies the
**injectable id** and lets Jackson build the `JacksonInject.Value` with its default
`useInput` (which permits JSON input to replace an injected value). The narrow,
complete fix is to override `findInjectableValue(AnnotatedMember)` so the returned
`JacksonInject.Value` has `useInput=false`. Then **no** JSON property (including the
`""` key) can ever replace a `@JacksonInject` value, for every deserialized class, on
every API path. Non-JavaScript requests are unaffected, and admin-enabled JavaScript
(`druid.javascript.enabled=true`) still works because the config still comes from Guice.

This is strongly preferred over per-class annotations or endpoint-level blacklists:
those are easy to leave incomplete and the background explicitly warns that
payload-string blacklists and single-class fixes are inadequate.

`GuiceAnnotationIntrospector` lives in the **core** module
(`core/src/main/java/org/apache/druid/guice/GuiceAnnotationIntrospector.java`), which is
built by the task's `-am` command, so its JAR (`druid-core-0.20.0.jar`) is rebuilt.

## Execution procedure

Run every step from the actual environment; do not trust hardcoded paths blindly —
confirm them first.

1. **Locate and inspect the source file** so the patch is generated against its real
   current contents (never assume contents):
   ```bash
   find /root/druid -name GuiceAnnotationIntrospector.java
   sed -n '1,200p' $(find /root/druid -name GuiceAnnotationIntrospector.java | head -1)
   ```
   Confirm it defines `findInjectableValueId(AnnotatedMember ...)` (0.20.0 does).

2. **Apply the fix and emit the patch file.** The helper edits the real file, inserts
   the `findInjectableValue` override (fully-qualified type names, so no new imports are
   needed), and writes a unified git diff to `/root/patches/`:
   ```bash
   echo '{}' | python3 /app/environment/skills/current/scripts/apply_fix.py
   ```
   It is idempotent (skips if already patched). Inputs/outputs: see script header.
   Then sanity-check the result:
   ```bash
   grep -n 'findInjectableValue\|withUseInput' $(find /root/druid -name GuiceAnnotationIntrospector.java | head -1)
   git -C /root/druid --no-pager diff | head -60
   ls -l /root/patches/
   git -C /root/druid apply --check /root/patches/*.patch && echo PATCH-OK  # patch is well-formed & re-appliable
   ```
   (`git apply --check` will report the hunk is already present if the tree is edited;
   use a clean `git stash` only if you need to prove reapplication — not required.)

3. **Set JAVA_HOME and rebuild** (large output — redirect to a log):
   ```bash
   export JAVA_HOME=$(dirname $(dirname $(readlink -f $(which javac))))
   java -version; mvn -v
   cd /root/druid
   mvn clean package -DskipTests -Dcheckstyle.skip=true -Dpmd.skip=true \
     -Dforbiddenapis.skip=true -Dspotbugs.skip=true -Danimal.sniffer.skip=true \
     -Denforcer.skip=true -Djacoco.skip=true -Ddependency-check.skip=true \
     -pl '!web-console' -pl indexing-service -am \
     > /tmp/mvn-build.log 2>&1 && echo BUILD SUCCESS || { tail -60 /tmp/mvn-build.log; echo BUILD FAILED; }
   ```
   Verify the rebuilt core jar exists: `ls -l /root/druid/core/target/druid-core-*.jar`.

4. **Deploy rebuilt jars** into the running distribution's `lib/` (the verifier restarts
   the server from there). The helper copies each freshly built `druid-*.jar` over the
   matching jar already in `/opt/druid/lib/`:
   ```bash
   echo '{}' | python3 /app/environment/skills/current/scripts/deploy_jars.py
   ```
   At minimum `druid-core-0.20.0.jar` must be replaced. Confirm with
   `ls -l /opt/druid/lib/druid-core-*.jar` (timestamp should be new).

## How the executor interprets results

- A BUILD FAILED means read `/tmp/mvn-build.log` tail: fix the specific compile error
  (usually a signature mismatch — ensure the override matches
  `public JacksonInject.Value findInjectableValue(AnnotatedMember m)`) and rebuild. Do
  not broaden the patch to disable the sampler or reject all JavaScript filters.
- Required deliverables that must all be present at the end: a patch file under
  `/root/patches/`, the edited source under `/root/druid/`, a successful Maven build, and
  the rebuilt `druid-core` jar in `/opt/druid/lib/`.
- If `GuiceAnnotationIntrospector.java` cannot be found or lacks
  `findInjectableValueId`, stop and inspect the tree manually before editing — do not
  fabricate a different file. The security invariant (untrusted input must not enable a
  server-disabled feature) is what matters.

## Validation ideas (run locally; derive from the task, not hidden tests)

- Grep confirms the override and `withUseInput(false)` are present in the source and the
  patch file is a parseable unified diff.
- The exploit shape (`"": {"enabled": true}`) relies on JSON replacing an injected value;
  with `useInput=false` Jackson ignores it, so the config stays server-controlled.
- Legitimate non-JavaScript filters/aggregators never use `@JacksonInject`, so they are
  unchanged; JavaScript still functions when `druid.javascript.enabled=true` on the
  server because the value is still injected.
