---
name: spring-boot-3-jakarta-java21-migration
description: Migrate a Maven Spring Boot 2.x application to a Java 21 and Spring Boot 3.2 baseline. Use for projects requiring Jakarta EE, Hibernate 6, Spring Security 6, and RestClient migration while preserving application behavior and passing clean Maven compile/test validation.
---

# Spring Boot 3 / Java 21 migration

Use this Skill on the editable Maven project root supplied by the task. It is an evidence-driven migration: inspect the actual POM, production sources, and tests before editing. Do not bypass compilation or tests by changing the requested Maven commands, disabling test execution, or weakening authorization merely to compile.

## Runtime inputs and helper

`scripts/scan_migration.py` accepts JSON on stdin:

```json
{"root":"/workspace","target_boot":"3.2","target_java":"21"}
```

It emits JSON with discovered POM properties/dependencies and occurrences of migration-sensitive APIs in text source files. Run it before changes and again after changes:

```sh
python3 /path/to/skill/scripts/scan_migration.py <<'JSON'
{"root":"/workspace","target_boot":"3.2","target_java":"21"}
JSON
```

The report is an inventory, not a substitute for compiler diagnostics. It deliberately reports only patterns that are meaningful for this migration, and excludes generated build output.

## Migration procedure

1. **Establish the real build baseline.**
   - Read the root `pom.xml`, any active parent/module POMs, application properties, all Java sources, and tests. Determine whether the root is multi-module and run Maven from the root or with the active POM.
   - Set the project Java release/property and compiler configuration to Java 21. Set the Spring Boot parent or dependency-management baseline to the requested Boot 3.2 release line.
   - Let Spring Boot dependency management select versions for starters and managed libraries. Remove legacy explicit versions that override its compatible dependency graph unless a dependency is genuinely unmanaged and its API requires an explicit compatible version.
   - Keep the required starters corresponding to the actual application: web, data JPA, validation, security, test, and its real database driver. Update non-managed libraries only after checking their imports and APIs (for example JWT libraries) rather than retaining a Java-8-era version by default.
   - Preserve database-driver scope and test database configuration. Do not add network-dependent build steps; the supplied runtime may have no network access.

2. **Perform Jakarta migration by API family.**
   - In application and test source, migrate Java EE imports used by the application from `javax.persistence`, `javax.validation`, `javax.servlet`, and related Spring-supported EE APIs to their corresponding `jakarta.*` packages.
   - Do not mechanically replace every `javax.*` import: Java SE APIs such as cryptography can remain under `javax` when they are not Jakarta EE APIs.
   - Check entity annotations, relationship ownership, column/table names, enum mappings, ID generation, lazy associations, and validation annotations after import migration. Hibernate 6 behavior must be validated through the project tests and actual persistence startup; retain mappings unless a concrete Hibernate 6 incompatibility requires a targeted change.
   - Update imports in exception handlers, controllers, filters, DTO constraints, repositories, and tests consistently. Ensure the POM contains the libraries defining the migrated annotations and servlet classes through Boot starters.

3. **Migrate Spring Security to Security 6 while retaining policy.**
   - Replace removed `WebSecurityConfigurerAdapter` configuration with explicit beans, normally a `SecurityFilterChain` and a `PasswordEncoder`; expose an authentication manager only if application code requires one.
   - Translate request rules to `authorizeHttpRequests` and `requestMatchers`. Use lambda-based configuration for CSRF, session management, exception handling, HTTP Basic/form login, and other configurers. Do not use removed `antMatchers`, `authorizeRequests`, or chained `and()` configuration styles.
   - Preserve the pre-existing public endpoints, authentication endpoints, role/authority conventions (`ROLE_` prefix behavior), JWT filter ordering, stateless/session behavior, password encoding, and 401/403 behavior. A successful compile is not authorization equivalence.
   - Update servlet/filter imports to Jakarta and inspect custom `UserDetailsService`, filters, and authentication-provider wiring for Security 6 signature changes.

4. **Replace RestTemplate usage with RestClient.**
   - Locate every `RestTemplate` field, constructor argument, bean, mock, and invocation, including tests. Replace it with Spring Framework's `RestClient`, normally injecting/configuring a `RestClient.Builder` bean or a configured `RestClient` appropriate to the existing base URL behavior.
   - Translate each call semantically: preserve URI template variables/query encoding, HTTP method, headers, request body, authentication, response body type, and error handling. Typical operations use `restClient.get()/post()/method(...)`, `.uri(...)`, `.headers(...)` or `.header(...)`, `.body(...)`, `.retrieve()`, and `.body(ResponseType.class)`.
   - Recreate intentional non-2xx handling with `onStatus` or the application’s established exception strategy. Do not silently convert failures to successful/null responses. Update tests to mock or exercise the new client boundary rather than leaving obsolete `RestTemplate` mocks.

5. **Resolve concrete compiler and test failures minimally.**
   - Run `mvn clean compile` exactly as requested. Start with the earliest concrete compiler error, especially in a multi-module build; downstream missing-symbol errors may be cascades.
   - Make the smallest source/POM change that resolves the observed incompatibility while preserving behavior. Common follow-up areas are changed Spring Security DSL methods, Jakarta imports, validation exception classes, Hibernate type/mapping usage, and dependency versions.
   - Run `mvn test`. Repair test compilation, application-context configuration, persistence mapping failures, security behavior, validation behavior, and external-client error-path tests. Do not mask failures through `skipTests`, permissive security rules, or changing the task’s quality commands.

## Completion criteria

Before reporting completion, rerun the scan helper and inspect its remaining findings. Remaining Java EE `javax.*`, `RestTemplate`, `WebSecurityConfigurerAdapter`, `antMatchers`, `authorizeRequests`, or Spring Boot 2 baseline findings require an explicit determination: migrate them when application-related, or document why they are a deliberate Java SE/non-applicable occurrence.

Then execute from the active project root:

```sh
mvn clean compile
mvn test
```

Success requires both commands to return successfully within the task environment. Report the files changed, the behavior-preserving migration decisions (security rules and HTTP-client semantics), and the actual results of both commands. If Maven fails due to unavailable dependencies or another environmental prerequisite, distinguish that observable prerequisite failure from source failures and do not claim validation passed.
