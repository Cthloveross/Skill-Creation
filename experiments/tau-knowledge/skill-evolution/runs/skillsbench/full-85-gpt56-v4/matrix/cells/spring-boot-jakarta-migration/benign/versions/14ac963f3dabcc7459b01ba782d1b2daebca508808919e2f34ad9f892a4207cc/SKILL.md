---
name: spring-boot-3-jakarta-migration
description: Migrate an existing Maven Spring Boot 2.x Java service to Spring Boot 3.x and a modern JDK, including Jakarta APIs, Hibernate 6, Spring Security 6, and RestTemplate-to-RestClient changes. Use when the editable workspace contains the service source and Maven is the required validation path.
---

# Spring Boot 3 / Jakarta migration

Use this Skill to make a dependency-consistent, source-compatible migration of an existing service. Work from the actual workspace contents and compiler/test output; do not assume every legacy API occurs or replace APIs that are not present.

## Inputs and prerequisites

* The service root contains `pom.xml`, `src/main`, and normally `src/test`.
* Maven and the requested JDK must be available. Confirm with `mvn -version` before interpreting language-level failures.
* Run commands from the directory containing the active `pom.xml`. If a wrapper or CI script is supplied, inspect it and use its authoritative Maven invocation as well.
* This Skill modifies application source and Maven configuration, not generated output under `target/` and not a build command merely to skip failures.

An optional static inventory can be produced before editing:

```sh
python3 /app/environment/skills/current/scripts/audit_spring_migration.py <<'JSON'
{"root":"/workspace"}
JSON
```

The script reads JSON from standard input and writes JSON to standard output. Input has required `root` (service root) and optional `extensions` (list, default `[".java", ".xml", ".properties", ".yml", ".yaml"]`). Output contains `files_scanned`, `matches`, and `summary`; matches identify only migration-relevant text and are not proof that every finding needs a change.

## Migration procedure

1. **Establish a single managed platform baseline.** Inspect the current POM before changing it. Set the Spring Boot parent/BOM to the required 3.x release and set the compiler/JDK property to the requested release (for this task, Boot 3.2.x and Java 21). Prefer Spring Boot dependency management for Boot, Spring, Hibernate, validation, Jackson, and logging modules. Remove old explicit versions that override the managed compatible versions unless an independently required library has a documented compatible version. Retain functional dependencies such as JPA, validation, security, test, database driver, and JWT support.

   Do not combine incompatible Boot parents/BOMs or retain a direct `javax.*` API dependency to paper over source errors. For libraries outside Boot management (for example JWT libraries), select one release compatible with the target JDK/Jakarta ecosystem and ensure all modules from that library use the same version.

2. **Migrate namespaces as a coherent source change.** Search all production and test code, plus configuration where relevant, for `javax.`. Replace Jakarta EE APIs with their `jakarta.*` equivalents, including persistence, validation, servlet, and annotation imports. Typical mappings include `javax.persistence` to `jakarta.persistence`, `javax.validation` to `jakarta.validation`, and `javax.servlet` to `jakarta.servlet`.

   Do not blindly change non-Jakarta APIs such as `javax.crypto`, `javax.sql`, or `javax.xml` solely because of their package prefix. Use the import and compiler diagnostics to distinguish them. Confirm JPA annotations, validation annotations, exception-handler servlet types, and test sources are migrated consistently.

3. **Review Hibernate/JPA mappings rather than only imports.** Keep entities using `jakarta.persistence` annotations and let the Boot 3 Hibernate version be managed. Inspect custom SQL, ID generation, enum mappings, column definitions, lazy relationships, and repository method signatures for Hibernate 6 incompatibilities revealed by compilation or tests. Preserve schema/table/column names and application behavior unless a Hibernate 6 change requires an explicit mapping adjustment. Avoid adding legacy Hibernate artifacts that conflict with the Boot-managed ORM stack.

4. **Convert security configuration to Spring Security 6.** Replace obsolete adapter-based configuration with beans, normally a `SecurityFilterChain` built from `HttpSecurity` and a `PasswordEncoder` where password hashing is used. Use the current lambda DSL and `authorizeHttpRequests`, then express equivalent authorization rules with `requestMatchers`. Preserve public endpoints, role/authority conventions, stateless/session behavior, CSRF/CORS intent, authentication provider, and filter ordering.

   Update custom filters and authentication classes to Jakarta servlet types. Do not broaden access rules merely to make tests pass. If existing code uses roles such as `ADMIN`, preserve whether callers use `hasRole` (without `ROLE_` prefix) or `hasAuthority` (exact authority) and keep the corresponding stored authority behavior consistent.

5. **Replace `RestTemplate` usage with `RestClient` without changing request semantics.** Define a Spring-managed `RestClient` bean (or inject a builder and build it) and inject it into services rather than creating clients ad hoc. Translate each call preserving URI template variables, query parameters, HTTP method, request entity/body, headers, authentication, response type, and error policy. The normal simple pattern is `client.get().uri(...).retrieve().body(TargetType.class)`; use the corresponding request specification for POST/PUT/DELETE and bodies. If previous code treated non-2xx responses specially, add explicit status handling instead of silently changing that behavior.

6. **Compile first, then resolve root causes minimally.** Run:

```sh
mvn clean compile
```

Treat the earliest compiler diagnostics as primary. Correct the responsible imports, dependency declarations, or source API usages, then repeat the same command. Do not infer success from a stale `target` directory.

7. **Run all tests under the migrated application.** Execute:

```sh
mvn test
```

If the application-context test fails, inspect its first causal exception. Check test profile properties, datasource configuration, security beans, and external-client beans. Keep tests meaningful; do not disable tests or change them to avoid exercising the migrated configuration. For a service with external HTTP calls, tests should not require an uncontrolled live endpoint unless the original test contract explicitly does so.

8. **Perform final checks.** Re-run both required commands after the final edit:

```sh
mvn clean compile
mvn test
```

Also search the source tree for unintended legacy Jakarta EE imports, while excluding build artifacts:

```sh
grep -RIn --exclude-dir=target --include='*.java' '^import javax\.' src || true
```

Investigate every remaining result; standard-library namespaces may be legitimate. Review the final diff to ensure changes are limited to the POM, application/test source, and needed configuration, with no generated binaries or dependency caches committed.

## Failure handling

* If dependency resolution fails, inspect the effective POM and conflicting explicit versions before changing source.
* If the configured JDK is not the required target JDK, report that prerequisite distinctly; do not lower the compiler target to conceal it.
* If a library has no Boot-3-compatible release, identify the incompatible dependency and replace or upgrade it only after preserving the service interface and behavior.
* If tests fail because a removed API is still referenced, fix the migrated production/test configuration rather than adding an obsolete `javax` compatibility dependency.
* If an external call’s expected behavior is unclear, preserve the old method/URI/header/body/response contract as closely as possible and let focused tests or code context determine the needed RestClient API form.
