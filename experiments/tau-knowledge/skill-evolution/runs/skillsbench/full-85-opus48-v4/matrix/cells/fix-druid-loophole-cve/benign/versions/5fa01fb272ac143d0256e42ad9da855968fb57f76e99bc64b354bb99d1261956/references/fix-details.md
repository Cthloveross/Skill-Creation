# CVE-2021-25646 fix details and rationale

## Mechanism recap
The JavaScript filter/aggregator/extraction classes receive a `JavaScriptConfig`
via a Jackson creator parameter annotated for injection. Druid intends this to be
filled only from Guice (server flag `druid.javascript.enabled`, default false).
The exploit adds an empty-string key `""` whose value `{"enabled": true}` is
deserialized into that parameter, flipping JavaScript on and enabling RCE.

## Why fix GuiceAnnotationIntrospector
In Jackson 2.x, `AnnotationIntrospector.findInjectableValue(AnnotatedMember)`
returns a `JacksonInject.Value` carrying both the injectable id AND a `useInput`
flag. When `useInput` is not `false`, a matching JSON property is allowed to
replace the injected value. Druid's `GuiceAnnotationIntrospector` historically
supplied only the id (via `findInjectableValueId`), so Jackson built the Value
with default `useInput` and allowed the override.

Overriding `findInjectableValue` to return
`JacksonInject.Value.forId(id).withUseInput(false)` makes every `@JacksonInject`
value immune to JSON replacement. This is a single config-level control point
that covers `JavaScriptDimFilter`, `JavaScriptAggregatorFactory`,
`JavaScriptExtractionFn`, and any other injected-config consumer, on the Sampler
and every other deserialization path. It uses no payload/string blacklist.

## Why it preserves functionality
- Non-JavaScript filters/aggregators/extraction fns do not use `@JacksonInject`
  for security config, so they are unaffected.
- Legitimate JavaScript still works when the administrator sets
  `druid.javascript.enabled=true`, because the value is still injected by Guice
  (only the ability of *input* to override it is removed).
- The Sampler endpoint keeps working for all normal specs.

## Pitfalls to avoid (from background)
- Do NOT disable the Sampler endpoint or reject all `type:javascript` filters
  regardless of server config \u2014 that over-broadly breaks functionality.
- Do NOT blacklist JavaScript function text / dangerous class names \u2014 attackers
  can use alternative payloads; the empty-key override is the real boundary.
- Do NOT patch only one class \u2014 the aggregator/extraction paths stay exploitable.
- A green build/unit test does not prove the deployed artifact runs the fix:
  confirm the rebuilt `druid-core` jar landed in the distribution `lib/` and the
  server restarted. The GuiceAnnotationIntrospector lives in the `core` module,
  which the `-am` build recompiles.

## Build/deploy notes
- Set `JAVA_HOME` to the installed JDK before `mvn`.
- Redirect the huge Maven log to a file; keep only tail on failure.
- The exact task build command is:
  `mvn clean package -DskipTests -Dcheckstyle.skip=true -Dpmd.skip=true
   -Dforbiddenapis.skip=true -Dspotbugs.skip=true -Danimal.sniffer.skip=true
   -Denforcer.skip=true -Djacoco.skip=true -Ddependency-check.skip=true
   -pl '!web-console' -pl indexing-service -am`
- Deliverables: patch file(s) in /root/patches/, edited source in /root/druid/,
  successful build, and rebuilt druid-core jar deployed into /opt/druid/lib/.
