# Copy-ready API mappings (Spring Boot 2.7 -> 3.2, Java 8 -> 21)

These are concrete, commonly-needed transformations. Confirm exact artifact
versions and the final shape by compiling against the real project.

## pom.xml

```xml
<parent>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-parent</artifactId>
  <version>3.2.5</version>  <!-- any released 3.2.x -->
  <relativePath/>
</parent>

<properties>
  <java.version>21</java.version>
</properties>
```

- Remove explicit `<version>` overrides for Spring, Hibernate, Jackson,
  validation, servlet, and other artifacts managed by the parent BOM.
- Add `spring-boot-starter-validation` if validation annotations are used.
- JJWT: if present as `io.jsonwebtoken:jjwt`, split/upgrade to
  `jjwt-api` + `jjwt-impl` (runtime) + `jjwt-jackson` (runtime) at a
  Java 21-compatible version (0.11.5 or 0.12.x). Adjust parser/builder calls to
  the chosen version's API.

## Namespace renames (imports)

| Legacy (Java EE)                  | Jakarta EE 9+                      |
|-----------------------------------|------------------------------------|
| `javax.persistence.*`             | `jakarta.persistence.*`            |
| `javax.validation.*`              | `jakarta.validation.*`             |
| `javax.servlet.*`                 | `jakarta.servlet.*`                |
| `javax.annotation.PostConstruct`  | `jakarta.annotation.PostConstruct` |
| `javax.annotation.PreDestroy`     | `jakarta.annotation.PreDestroy`    |
| `javax.transaction.Transactional` | `jakarta.transaction.Transactional`|

## Spring Security 6

Before (2.7):
```java
@Configuration
@EnableGlobalMethodSecurity(prePostEnabled = true)
public class SecurityConfig extends WebSecurityConfigurerAdapter {
  @Override protected void configure(HttpSecurity http) throws Exception {
    http.csrf().disable()
        .authorizeRequests()
        .antMatchers("/api/auth/**").permitAll()
        .anyRequest().authenticated()
        .and()
        .sessionManagement().sessionCreationPolicy(SessionCreationPolicy.STATELESS);
    http.addFilterBefore(jwtFilter, UsernamePasswordAuthenticationFilter.class);
  }
  @Override protected void configure(AuthenticationManagerBuilder auth) {...}
  @Bean @Override public AuthenticationManager authenticationManagerBean() {...}
}
```

After (6.x):
```java
@Configuration
@EnableMethodSecurity
public class SecurityConfig {

  @Bean
  SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    http
      .csrf(csrf -> csrf.disable())
      .authorizeHttpRequests(auth -> auth
          .requestMatchers("/api/auth/**").permitAll()
          .anyRequest().authenticated())
      .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
      .addFilterBefore(jwtFilter, UsernamePasswordAuthenticationFilter.class);
    return http.build();
  }

  @Bean
  AuthenticationManager authenticationManager(AuthenticationConfiguration cfg) throws Exception {
    return cfg.getAuthenticationManager();
  }

  @Bean
  PasswordEncoder passwordEncoder() { return new BCryptPasswordEncoder(); }
  // UserDetailsService stays a bean; AuthenticationManager uses it + the encoder.
}
```

Notes:
- `@PreAuthorize` and helper beans referenced in SpEL (e.g. `@userSecurity`)
  keep working under `@EnableMethodSecurity`.
- If the old config wired `UserDetailsService` + `PasswordEncoder` into the
  `AuthenticationManagerBuilder`, Spring Security 6 auto-wires a
  `DaoAuthenticationProvider` from those beans; usually no explicit provider is
  needed.

## RestTemplate -> RestClient

Before:
```java
RestTemplate rt = new RestTemplate();
UserDTO u = rt.getForObject(baseUrl + "/users/{id}", UserDTO.class, id);
List<UserDTO> list = rt.exchange(baseUrl + "/users", HttpMethod.GET, null,
    new ParameterizedTypeReference<List<UserDTO>>(){}).getBody();
ResponseEntity<UserDTO> resp = rt.postForEntity(baseUrl + "/users", body, UserDTO.class);
```

After:
```java
RestClient client = RestClient.builder().baseUrl(baseUrl).build();

UserDTO u = client.get().uri("/users/{id}", id).retrieve().body(UserDTO.class);

List<UserDTO> list = client.get().uri("/users")
    .retrieve().body(new ParameterizedTypeReference<List<UserDTO>>(){});

UserDTO created = client.post().uri("/users")
    .contentType(MediaType.APPLICATION_JSON)
    .body(body)
    .retrieve().body(UserDTO.class);
```

Error handling parity:
- `RestClient#retrieve()` throws `HttpClientErrorException` (4xx) /
  `HttpServerErrorException` (5xx) by default, like `RestTemplate`. Keep the same
  catch blocks, or add `.onStatus(HttpStatusCode::isError, (req, res) -> {...})`
  to translate to the project's domain exceptions.
- Headers/auth: `.header("Authorization", token)` per request, or set defaults
  on the builder with `.defaultHeader(...)`.
- To get status/headers, use `.retrieve().toEntity(Type.class)`.

## Hibernate 6 / entities

- Namespace already handled by the renames above.
- Enum columns: `@Enumerated(EnumType.STRING)` is unchanged and recommended.
- Custom `org.hibernate.annotations.Type` / `UserType`: the SPI changed in
  Hibernate 6. Prefer removing custom types in favor of standard mappings; if a
  custom type is required, implement the Hibernate 6 `UserType` SPI.
- Verify `spring.jpa.hibernate.ddl-auto` and dialect settings in
  `application.properties` / test properties still make sense.

## Verification

Run `scripts/run_maven.py` for `["clean","compile"]` then `["clean","test"]`.
Both must report `success: true` with zero test failures/errors.
