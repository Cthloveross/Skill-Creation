---
name: python-scala-tokenizer-translation
description: Translate a supplied Python tokenizer module into a directly authored, idiomatic Scala 2.13 source artifact. Use when the runtime supplies a Python implementation and requires behavior-preserving Scala code, especially a tokenizer API using TokenType, Token, tokenizer classes, builders, and camelCase Scala methods.
---

# Python tokenizer module to Scala 2.13

## Purpose and inputs

Produce the requested Scala source file by inspecting the supplied Python module at runtime. This Skill does not assume the Python implementation's constants, token formats, regular expressions, supported temporal formats, metadata rules, or dependencies; those must be taken from the actual source.

Expected runtime inputs for this task are:

- Python source: `/root/Tokenizer.py`
- Build configuration, if supplied: `/root/build.sbt`
- Required output: `/root/Tokenizer.scala`
- Required Scala package: `tokenizer`

The bundled scripts accept JSON on standard input and produce JSON on standard output. They inspect and validate; they do **not** generate the deliverable, because correct translation requires preserving the source module's detailed behavior in directly authored Scala.

## Workflow

1. Read the entire Python source and the supplied build configuration before writing code. Do not infer behavior from names alone.
2. Create a structural inventory:

   ```bash
   python3 scripts/inspect_python.py <<'JSON'
   {"source_path":"/root/Tokenizer.py"}
   JSON
   ```

   The result lists top-level functions, classes, inheritance, constructors, decorators, signatures, defaults, and method source excerpts. Use it as a checklist while also reading the full source.
3. Identify every observable behavior, including:
   - `TokenType` values, parsing/lookup behavior, and string representation;
   - every `Token` field, default, metadata transformation, and equality-relevant field;
   - tokenizer constructor options, preprocessing, split/regex behavior, normalization, numeric parsing, temporal parsing, fallbacks, and error behavior;
   - dispatch precedence in `UniversalTokenizer`;
   - whitespace treatment and empty-input behavior;
   - builder defaults, fluent methods, and the exact tokenizer assembled by `build` or equivalent;
   - module-level `tokenize`, `tokenize_batch`, `to_token`, and `with_metadata` behavior.
4. Author `/root/Tokenizer.scala` directly, starting with `package tokenizer`. Keep the code in one coherent source file unless the runtime expressly asks for another layout. Do not generate Scala through Python string templates.
5. Translate APIs idiomatically while preserving their externally visible behavior:
   - Encode `TokenType` as a `sealed trait` plus `case object` variants and a companion lookup method. Preserve source values and unknown-value behavior.
   - Use immutable `case class` data for `Token` where compatible with the source behavior. Use immutable `Map`, `Vector`, `List`, or `Seq` in public results as appropriate.
   - Model absence as `Option`, not `null`. Convert only at an explicit compatibility boundary when the Python contract demonstrably needs a sentinel-like result.
   - Replace Python runtime type chains with a sealed ADT where the set of inputs is closed, or with clear pattern matching/overloads when the source accepts ordinary JVM values. Keep the public methods named in the task (`tokenize`, `tokenizeBatch`, `toToken`, `withMetadata`) available with signatures justified by the source.
   - Use `Either` or `Try` internally for parsing that can fail, then implement the Python module's observable fallback/raise/skip behavior deliberately. Do not silently discard errors where Python raises, and do not introduce exceptions where Python returns a fallback.
   - Use `java.time` and `DateTimeFormatter` for date/time behavior. Translate each Python format and timezone assumption from the source rather than guessing a single format.
   - Use Scala/JVM regex facilities for source regexes, carefully preserving anchors, flags, capture groups, split semantics, and escaping.
   - Use `BigDecimal` if the source relies on decimal precision; otherwise preserve the source's numerical acceptance and rendered token value semantics.
   - Prefer `val`, pure collection operations, `map`/`flatMap`/`foldLeft`, and exhaustive `match`. Local, tightly-contained mutation is acceptable only when it materially simplifies a builder or is needed for compatibility.
   - Translate `snake_case` APIs to Scala camelCase. Python `__init__` becomes a Scala primary/auxiliary constructor. Preserve other source functions and helpers, including non-public helpers, as Scala methods or companion helpers when they are behaviorally needed.
   - Provide concise Scaladoc for public types and non-obvious parsing decisions. Use PascalCase for types and camelCase for methods/values.
6. Inspect `/root/build.sbt` and use only its declared Scala version and dependencies. Do not invent an sbt layout, libraries, source-directory override, or Scala 3 syntax. Compile using the build mechanism actually supported by the supplied environment, ensuring `/root/Tokenizer.scala` is included as required by that mechanism.
7. Run behavioral checks based on representative values and edge cases found in the Python source: each token category, blanks, punctuation, malformed numeric and temporal strings, empty batches, metadata defaults/overrides, builder configuration, and mixed universal dispatch. Compare rendered token fields and collection ordering, not merely compilation.
8. Perform structural validation after writing the file:

   ```bash
   python3 scripts/verify_translation.py <<'JSON'
   {"python_path":"/root/Tokenizer.py","scala_path":"/root/Tokenizer.scala","required_package":"tokenizer","expected_symbols":["TokenType","Token","BaseTokenizer","StringTokenizer","NumericTokenizer","TemporalTokenizer","UniversalTokenizer","WhitespaceTokenizer","TokenizerBuilder","tokenize","tokenizeBatch","toToken","withMetadata"]}
   JSON
   ```

   `ok: false` identifies missing package declarations, source-derived public symbols, or explicitly required symbols. Treat warnings as review items. This is structural validation only; compilation and behavioral comparison remain required.

## Failure handling

- If the Python or build file is absent or unreadable, report that prerequisite clearly and do not fabricate its behavior.
- If Python relies on a library unavailable to the declared Scala build, preserve behavior with the Scala/JDK standard library when feasible; otherwise identify the unsupported dependency rather than claiming equivalent behavior.
- If Python uses unrestricted dynamic execution, reflection, arbitrary Python callbacks, or values that cannot be represented with a stable Scala API, preserve the supported subset explicitly and surface an actionable incompatibility.
- Do not hardcode input-instance outputs, sample token values, dates, or inferred expected results. All such details must be read from the provided source at execution time.

## Script schemas

`inspect_python.py` input:

```json
{"source_path":"/absolute/or/declared/path/to/module.py"}
```

Output has `ok`, source metadata, imports, module assignments, module functions, and classes. Each function includes a Scala-style expected name for checklist purposes.

`verify_translation.py` input:

```json
{"python_path":"/path/module.py","scala_path":"/path/Tokenizer.scala","required_package":"tokenizer","expected_symbols":["OptionalAdditionalSymbol"]}
```

Output has `ok`, `errors`, `warnings`, the Python-derived expected symbols, and detected Scala declarations. `expected_symbols` is optional.
