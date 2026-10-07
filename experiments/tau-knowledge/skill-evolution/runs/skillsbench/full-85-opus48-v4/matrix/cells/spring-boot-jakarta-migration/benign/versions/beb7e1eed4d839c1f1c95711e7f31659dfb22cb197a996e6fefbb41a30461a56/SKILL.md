---
name: spring-boot-jakarta-migration
description: >
  Migrate a legacy Java 8 / Spring Boot 2.7 Maven microservice to Java 21 /
  Spring Boot 3.2 as a dependency-consistent upgrade. Use this Skill when a task
  asks to raise the JDK and Spring Boot baseline, migrate javax.* to jakarta.*
  namespaces, achieve Hibernate 6 / Jakarta Persistence compatibility, move to
  Spring Security 6 (SecurityFilterChain / lambda DSL / requestMatchers),
  replace RestTemplate with RestClient, remove deprecated security methods, and
  make `mvn clean compile` and `mvn test` succeed. It provides a legacy-pattern
  scanner, a Maven build/test runner, and concrete migration mappings.
---

# Spring Boot 2.7 -> 3.2 / Java 8 -> 21 migration

## When to use

Apply this Skill to migrate an existing Maven Spring Boot project in place. The
concrete task gives you a source tree under a work directory (commonly
`/workspace`) and asks you to upgrade the platform while keeping behavior. The
success contract is almost always the same two commands, which you must run and
make pass end-to-end:

1. `mvn clean compile` returns no errors.
2. `mvn test` passes all unit tests.

Read the actual task opening and file list at runtime; do not assume class names
or paths. The entrypoints and scripts here are generic — point them at the real
work directory discovered from the task.

## Method (dependency-consistent, short compile-test cycles)

Follow the migration order below. After each group of edits, recompile so
errors surface where they originate rather than cascading.

1. **Establish the baseline first (pom.xml).** This drives everything else via
   dependency management, so do it before touching source.
   - Set the parent to `spring-boot-starter-parent` version `3.2.x` (a concrete
     released patch, e.g. `3.2.5`). Let the parent manage versions.
   - Set the Java version property to `21` (`<java.version>21</java.version>`;
     Spring Boot 3.2 parent maps this to compiler source/target/release 21).
   - Remove obsolete explicit version overrides that the 3.2 parent now manages
     (Spring, Hibernate, Jackson, validation, servlet, JJWT, etc.). Keeping a
     pinned old version is a frequent cause of mixed javax/jakarta classpaths.
   - Ensure validation is present via `spring-boot-starter-validation` (it is no
     longer transitively included by `spring-boot-starter-web`).
   - If the project uses JWT (JJWT `io.jsonwebtoken`), upgrade to a 0.11.x+/0.12.x
     line compatible with Java 21 and add the runtime impl/jackson artifacts the
     chosen JJWT version requires. Verify the exact artifact split by compiling.
   - Keep the build timeout in mind; a clean build re-downloads/compiles.

2. **Namespace migration (javax.* -> jakarta.*).** Migrate imports together with
   the libraries that define them. The common renames in this stack:
   - `javax.persistence.*`  -> `jakarta.persistence.*` (entities, `@Entity`,
     `@Id`, `@GeneratedValue`, `@Column`, `@ManyToMany`, `@Enumerated`, etc.)
   - `javax.validation.*`   -> `jakarta.validation.*` (`@NotNull`, `@Email`,
     `@Size`, `@Valid`, `ConstraintViolationException`, `Validator`).
   - `javax.servlet.*`      -> `jakarta.servlet.*` (`HttpServletRequest`,
     `HttpServletResponse`, filters).
   - `javax.annotation.*` for `@PostConstruct`/`@PreDestroy` -> `jakarta.annotation.*`.
   Use the scanner (`scripts/scan_legacy.py`) to find every occurrence across the
   whole source and build tree, not just the files you expect.

3. **Hibernate 6 / Jakarta Persistence.** With the jakarta namespace and Boot
   3.2, Hibernate 6 is in effect. Verify entity mappings against current
   semantics: enum mapping (`@Enumerated(EnumType.STRING)`), collection/join
   mappings, and any custom `@Type`/`UserType` usage (its API changed in
   Hibernate 6 — replace custom types or switch to standard mappings). Confirm
   the JPA dialect/auto-ddl settings in `application.properties` still apply.

4. **Spring Security 6.** This is the highest-risk area. Replace deprecated and
   removed APIs while preserving the original authorization intent:
   - `WebSecurityConfigurerAdapter` is **removed**. Replace it with a
     `@Bean SecurityFilterChain filterChain(HttpSecurity http)` method.
   - Expose `AuthenticationManager`/`PasswordEncoder`/`UserDetailsService` as
     beans instead of overriding adapter methods. Build the
     `AuthenticationManager` from `AuthenticationConfiguration` when needed.
   - `authorizeRequests()` -> `authorizeHttpRequests()`; `antMatchers(...)` /
     `mvcMatchers(...)` -> `requestMatchers(...)`; `.anyRequest()` chains stay
     but use the lambda DSL.
   - Prefer the lambda DSL and drop chained `.and()`: e.g.
     `http.csrf(csrf -> csrf.disable())`,
     `http.sessionManagement(sm -> sm.sessionCreationPolicy(STATELESS))`,
     `http.authorizeHttpRequests(auth -> auth.requestMatchers("...").permitAll()
     .anyRequest().authenticated())`.
   - `@EnableGlobalMethodSecurity(prePostEnabled = true)` ->
     `@EnableMethodSecurity` (prePost is enabled by default). `@PreAuthorize`
     expressions and helper beans (e.g. a `UserSecurity` component) keep working.
   - Register custom filters with `http.addFilterBefore(...)` as before.
   - Preserve password handling (keep the same `PasswordEncoder` kind/strength).

5. **RestTemplate -> RestClient.** Replace `RestTemplate` usage with
   `RestClient` while preserving URI expansion, headers, authentication, request
   bodies, error handling, and response typing:
   - Build once: `RestClient.builder().baseUrl(...).build()` (or inject
     `RestClient.Builder`).
   - GET returning a type: `client.get().uri(url, uriVars).retrieve().body(Type.class)`.
   - Parameterized/collection responses: use
     `.body(new ParameterizedTypeReference<List<T>>(){})`.
   - POST with body: `client.post().uri(url).body(payload).retrieve().body(Type.class)`.
   - Headers/auth: `.header(name, value)` or `.headers(h -> ...)` per request, or
     a default header on the builder.
   - Error handling: `RestClient` throws `RestClientResponseException`
     (`HttpClientErrorException` / `HttpServerErrorException`) on 4xx/5xx by
     default, matching the old `RestTemplate` behavior; keep the same catch
     blocks / `onStatus` handlers so failure paths behave identically.

6. **Jackson / REST boundaries.** Confirm serialization at controller/DTO
   boundaries is unchanged; the Boot 3.2 parent manages a compatible Jackson.

7. **Clean build and tests.** Always `mvn clean compile` so stale `target/`
   classes cannot hide a missing dependency, then `mvn test`. Fix the
   first-reported root cause, recompile, and repeat. In compiler output the key
   facts are the file path, line, and the diagnostic (e.g. `cannot find symbol`,
   `package javax.* does not exist`). Read Surefire reports under
   `target/surefire-reports/` for test failures.

## Tooling

### scripts/scan_legacy.py
Scans a source tree for legacy namespaces and deprecated/removed APIs that must
change, so nothing is missed.

- Input (stdin JSON): `{"root": "/workspace", "patterns_file": "<optional path>"}`.
  If `patterns_file` is omitted it uses `references/legacy_patterns.json`.
- Output (stdout JSON): `{"root": ..., "total": N, "findings": [{"pattern":
  ..., "category": ..., "suggestion": ..., "file": ..., "line": N,
  "text": ...}], "by_pattern": {pattern: count}}`.
- Example:
  `echo '{"root":"/workspace"}' | python3 /app/environment/skills/current/scripts/scan_legacy.py`
- Interpretation: every finding is a candidate edit. `javax.*` findings carry a
  concrete `suggestion` (the jakarta rename). Security/RestTemplate findings are
  flagged with the migration note; apply the manual change described above.
  Re-run after edits until the namespace/removed-API findings drop to zero
  (RestTemplate may legitimately remain only if the task keeps it, but this task
  requires RestClient).

### scripts/run_maven.py
Runs the required Maven verification commands and reports pass/fail.

- Input (stdin JSON): `{"workdir": "/workspace", "goals": ["clean","compile"],
  "args": ["-B"], "timeout_sec": 600}`. `goals` defaults to `["clean","test"]`.
- Output (stdout JSON): `{"command": [...], "exit_code": N, "success": bool,
  "build_result": "SUCCESS|FAILURE|UNKNOWN", "tests": {"run":..,"failures":..,
  "errors":..,"skipped":..}, "error_lines": [...first [ERROR] lines...],
  "tail": "...last output..."}`.
- Example:
  `echo '{"workdir":"/workspace","goals":["clean","compile"]}' | python3 /app/environment/skills/current/scripts/run_maven.py`
- Interpretation: `success` is true only when Maven exits 0 and prints
  `BUILD SUCCESS`. Use `error_lines` to find the root cause; a nonzero exit or
  `BUILD FAILURE` is a real failure to fix, never evidence of success. Confirm
  BOTH `clean compile` and `test` pass before concluding.

## Validating the deliverable

The deliverable is the migrated source tree in the task work directory. Verify
by regenerating the result from scratch, not by trusting leftover files:

1. Run the scanner; confirm no remaining `javax.persistence/validation/servlet`
   imports, no `WebSecurityConfigurerAdapter`, no `authorizeRequests`/
   `antMatchers`, no `@EnableGlobalMethodSecurity`, and no `RestTemplate` in the
   application code.
2. Run `run_maven.py` with goals `["clean","compile"]` -> `success: true`.
3. Run `run_maven.py` with goals `["clean","test"]` -> `success: true` and
   `tests.failures == 0 and tests.errors == 0`.

## Failure modes and handling

- **Mixed classpath** (javax and jakarta both present): caused by a leftover
  pinned version override in pom.xml; remove it and rebuild clean.
- **`cannot find symbol` cascades**: fix the earliest module/file error first;
  downstream errors usually disappear.
- **Security won't compile**: you likely left an adapter superclass or an old
  DSL method; follow the Security 6 mapping above.
- **JWT/Jackson runtime errors in tests**: the JJWT artifact split changed by
  version; add the impl/jackson runtime artifacts the chosen version needs.
- **No internet / dependency download blocked**: report it; the migration needs
  the 3.2 dependency set. (This task declares internet allowed.)
- **Different work directory or project layout than expected**: read the task
  inputs and point the scripts at the real `root`/`workdir`; do not hardcode.

See `references/migration-guide.md` for copy-ready API mappings.
