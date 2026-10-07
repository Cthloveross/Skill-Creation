---
name: python-to-scala-tokenizer
summary: Translate a supplied Python tokenizer/data-preparation module into a readable, behavior-preserving Scala 2.13 source file, then validate its required API and compilation using the supplied build environment.
---

# Python to Scala 2.13 Translation

Use this Skill when a task supplies a Python module and requests an idiomatic Scala 2.13 translation, particularly for a tokenizer-style API with classes, builders, token types, optional metadata, parsing, and batch processing.

## Inputs and assumptions

At runtime, read the task's supplied Python source and build definition. Do not infer behavior from class or method names alone. The task determines:

- the input Python path;
- the required Scala output path and package declaration;
- the public symbols that must remain available; and
- the supported compilation command/source layout.

This Skill's inspection helper accepts JSON on standard input and writes JSON on standard output:

```json
{"source_path":"/absolute/path/to/input.py"}
```

Run it with:

```sh
python3 /app/environment/skills/current/scripts/inspect_python.py <<'JSON'
{"source_path":"/absolute/path/to/input.py"}
JSON
```

It reports top-level classes, their inheritance, methods, module functions, imports, decorators, signatures, docstrings, and statically visible instance attributes. Treat the report as an inventory, then read the complete source (including every method body) before implementing anything.

## Translation procedure

1. **Inspect the real environment.** Read the complete Python module and the build file. Identify Python dependencies, regular expressions, data formats, default values, mutation, exception behavior, date/time semantics, and the exact source discovery/compile command. A standalone required output is not necessarily compiled by a default `sbt compile`; use the supplied build configuration rather than inventing project layout.

2. **Make a behavior inventory.** For every class, function, constructor argument, method, public field/property, and factory/builder operation, identify its inputs, outputs, edge cases, and relationships. Pay particular attention to the task-mandated symbols. Preserve observable token values, order, offsets, metadata behavior, numeric/date classification rules, configuration defaults, and batch result behavior from the actual source.

3. **Design Scala types before coding.** Use Scala 2.13 constructs, not Scala 3 syntax.
   - Model enum-like token categories as a `sealed trait TokenType` with `case object` variants and a companion object lookup when source behavior needs one.
   - Model immutable records as `case class`es. Use immutable `Map`, `Seq`, `Vector`, or `List` in public APIs as appropriate.
   - Use `Option[A]` for absent values; do not use `null` as an absence marker.
   - If the Python API accepts distinct input forms, prefer an explicit sealed ADT and exhaustive matching. Add overloads only when that preserves a clearly required calling surface.
   - Use traits or abstract classes for Python ABCs. Use companion objects for factories and constants.
   - Use `Either`/`Try` internally or at parsing boundaries where failures are expected. If the Python public contract raises or returns a particular failure form, preserve the externally observable contract deliberately rather than silently swallowing errors.

4. **Implement directly in the requested Scala file.** Begin with the required `package` declaration. Use PascalCase for types and case objects, camelCase for methods and values, two-space indentation, `val` by default, and Scaladoc on public abstractions. Give all public methods explicit result types where it improves API clarity. Avoid shared mutable builder defaults; a builder should return a new immutable configuration or carefully encapsulate any mutation.

5. **Preserve parsing semantics carefully.** Translate Python regexes to Scala/Java regexes with correct escaping, preserve full-match versus substring-match behavior, preserve whitespace treatment, and preserve token ordering. Translate Python date/time format behavior to `java.time` deliberately; unsupported formats should have a defined failure path consistent with source behavior. Do not replace source-specific numeric or temporal rules with a generic parser unless the source actually does that.

6. **Validate API coverage.** After writing the output, run:

```sh
python3 /app/environment/skills/current/scripts/validate_translation.py <<'JSON'
{"python_path":"/absolute/path/to/input.py","scala_path":"/absolute/path/to/output.scala","required_package":"tokenizer","required_symbols":["TokenType","Token","BaseTokenizer","StringTokenizer","NumericTokenizer","TemporalTokenizer","UniversalTokenizer","WhitespaceTokenizer","TokenizerBuilder","tokenize","tokenizeBatch","toToken","withMetadata"]}
JSON
```

The validator performs structural checks only: it checks the package, source readability, required names, and reports source callables whose names do not appear in the Scala file. Resolve all relevant missing symbols by reading the source; names can legitimately be represented as constructors, companion methods, or inherited methods.

7. **Compile with the real build.** Run the compile command supported by the supplied environment and ensure it includes the requested standalone file. Fix compiler errors rather than weakening types or removing functionality. If no build command includes that file, use the installed Scala 2.13 compiler with the same classpath/dependencies established by the supplied build, only if the environment makes that possible. Do not claim a compile succeeded without observing a zero exit status.

8. **Perform focused behavioral checks.** Create only temporary local probes if useful. Exercise representative ordinary and boundary inputs taken from the source's own documented/testable behavior: empty input, whitespace, punctuation, numeric forms, temporal forms, metadata/default configuration, and batch ordering. Do not hardcode task-instance output values into reusable helpers or source.

## Completion criteria

The task is complete only when the requested Scala file exists at the exact required path, has the required package, exposes every required class/function, follows Scala 2.13 syntax and idioms, preserves the Python module's behavior, and compiles through the supplied environment. Report any genuinely unsupported Python dependency or semantic incompatibility explicitly rather than fabricating an implementation.
