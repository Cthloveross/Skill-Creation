---
name: python-scala-tokenizer-translation
description: Translate a supplied Python tokenizer module into a directly authored, idiomatic Scala 2.13 source artifact. Use when the runtime supplies a Python implementation and requires behavior-preserving Scala code, especially a tokenizer API using TokenType, Token, tokenizer classes, builders, and camelCase Scala methods.
---

# Python tokenizer module to Scala 2.13

## Purpose and runtime inputs

Produce the requested Scala source by inspecting the supplied Python module at runtime. Do not assume constants, token formats, regular expressions, temporal formats, metadata rules, or dependencies: derive them from the actual source.

Expected inputs and output for this task:

- Python source: `/root/Tokenizer.py`
- Build configuration: `/root/build.sbt`
- Required artifact: `/root/Tokenizer.scala`
- Required package: `tokenizer`

The bundled scripts consume JSON from standard input and emit JSON to standard output. They inspect and validate source; they do not generate the Scala deliverable. Author the Scala file directly.

## Translation workflow

1. Read all of `/root/Tokenizer.py` and `/root/build.sbt`. Inspect the Python structure as a checklist:

   ```bash
   python3 scripts/inspect_python.py <<'JSON'
   {"source_path":"/root/Tokenizer.py"}
   JSON
   ```

2. Inventory every observable behavior before implementation, including enum labels, `Token` fields/defaults, metadata behavior, constructors, regex and split semantics, normalization, numeric/temporal acceptance and fallback behavior, universal dispatch precedence, empty values, batch ordering, whitespace handling, builder defaults, fluent configuration, and module-level functions.

3. Directly author `/root/Tokenizer.scala`, with `package tokenizer` as its package declaration. Preserve all behaviorally relevant Python helpers as Scala methods or companion helpers and expose every task-required API:

   - Types: `TokenType`, `Token`, `BaseTokenizer`, `StringTokenizer`, `NumericTokenizer`, `TemporalTokenizer`, `UniversalTokenizer`, `WhitespaceTokenizer`, and `TokenizerBuilder`.
   - Methods: `tokenize`, `tokenizeBatch`, `toToken`, and `withMetadata`.

4. Use Scala 2.13 idioms while deliberately preserving the Python contract:

   - Represent `TokenType` with a `sealed trait` and `case object` members carrying the exact Python serialized labels. Add a companion lookup only if it reflects source behavior.
   - Represent stable token data with an immutable `case class Token`; use immutable collections in public values.
   - Use `Option` for absence. Use `Try` or `Either` internally for parsers, then faithfully implement the Python raise/fallback/skip result at the public boundary.
   - Translate type-dispatch chains to explicit pattern matching or a sealed input ADT where practical. Do not use Scala 3 syntax.
   - Use `java.time` and `DateTimeFormatter` for dates and times, and preserve each source format, timezone assumption, and parsing order.
   - Preserve regex flags, anchors, captures, split behavior, and escaping. Prefer clear named helpers over opaque one-line regex pipelines.
   - Use `BigDecimal` when source behavior depends on decimal precision. Prefer `val`, collection combinators, and exhaustive matches.
   - Convert Python snake_case names to Scala camelCase, while retaining all source functionality. Use PascalCase type names and concise Scaladoc for public types or non-obvious behavior.

5. Read the supplied build and use only its Scala version and dependencies. Do not invent a project layout, external dependency, source-directory override, or unsupported compiler feature. If the build tool is available, compile with the supplied build after placing the artifact in the layout required by that build.

6. Run source-readiness validation before compilation and fix every reported lexical issue:

   ```bash
   python3 scripts/verify_translation.py <<'JSON'
   {
     "python_path":"/root/Tokenizer.py",
     "scala_path":"/root/Tokenizer.scala",
     "required_package":"tokenizer",
     "expected_symbols":["TokenType","Token","BaseTokenizer","StringTokenizer","NumericTokenizer","TemporalTokenizer","UniversalTokenizer","WhitespaceTokenizer","TokenizerBuilder","tokenize","tokenizeBatch","toToken","withMetadata"]
   }
   JSON
   ```

   The validator includes a conservative Scala lexical readiness check designed for environments where `sbt` may not be installed. It checks balanced delimiters while ignoring strings/comments and rejects common Scala-3-only keywords. `ok` must be true before treating the source as ready. It is not a substitute for compilation.

7. Avoid constructs that confuse constrained source-only Scala validators when an equivalent Scala 2.13 expression exists. In particular, do not use character literals (including an escaped apostrophe character literal); use string operations, numeric character conversion, or library predicates instead. Ensure ordinary and triple-quoted strings, block comments, and delimiters are terminated. Do not place Scala-3-only keyword tokens (`enum`, `given`, `using`, `extension`, or `opaque type`) anywhere in the artifact, including comments.

8. Perform behavioral checks based on values and edge cases actually present in the Python source: each category, blanks/punctuation, malformed numeric and temporal strings, empty batches, metadata defaults/overrides, builder settings, and mixed universal dispatch. Compare token fields and ordering, not compilation alone.

## Failure handling

- If the Python source or build file is missing or unreadable, report that prerequisite; do not invent behavior.
- If a Python dependency has no counterpart in the supplied Scala build, implement it with the JDK/Scala standard library only when behavior can be preserved; otherwise identify the incompatibility clearly.
- If source behavior relies on unrestricted dynamic execution, reflection, arbitrary callbacks, or unrepresentable values, preserve the supported subset explicitly and surface an actionable limitation.
- Do not hardcode instance-specific token values, dates, outputs, or test fixtures. Read all behavior from the runtime source.

## Script schemas

`inspect_python.py` input:

```json
{"source_path":"/path/to/module.py"}
```

It outputs `ok`, imports, assignments, classes, functions, signatures, method source excerpts, and a camelCase symbol checklist.

`verify_translation.py` input:

```json
{"python_path":"/path/module.py","scala_path":"/path/Tokenizer.scala","required_package":"tokenizer","expected_symbols":["OptionalExtraSymbol"]}
```

It outputs `ok`, `errors`, `warnings`, Python-derived symbols, and declared Scala symbols. Missing paths, parse errors, absent declarations, lexical imbalance, unterminated strings/comments, and forbidden Scala-3 keyword tokens are errors.
