---
name: python-scala-tokenizer-translation
description: Translate a runtime-supplied Python tokenizer module into a directly authored, behavior-preserving Scala 2.13 source file. Apply when a task requires package tokenizer plus TokenType, Token, tokenizer classes, builders, and camelCase APIs.
---

# Python tokenizer module to Scala 2.13

## Runtime contract

Read the supplied sources at runtime; they are the authority for behavior:

- Python implementation: `/root/Tokenizer.py`
- Scala build definition: `/root/build.sbt`
- Required output: `/root/Tokenizer.scala`
- Required package declaration: `package tokenizer`

The packaged scripts read one JSON object from standard input and write one JSON object to standard output. They inspect and validate files only. Directly author the requested Scala source rather than generating Scala through nested string templates.

## Procedure

1. Confirm both supplied files are readable and inspect the complete Python module:

   ```bash
   python3 scripts/inspect_python.py <<'JSON'
   {"source_path":"/root/Tokenizer.py"}
   JSON
   ```

2. Build a translation checklist from the actual source before coding. Include enum member names and serialized labels; `Token` fields and defaults; metadata copying/merging; constructor defaults; all normalizers; each tokenizer's acceptance, fallback, and error behavior; numeric types and formatting; temporal formats and parse precedence; universal dispatch order; whitespace behavior; batch ordering; module functions; and every builder option and fluent method.

3. Read `/root/build.sbt` and restrict implementation to Scala 2.13 and dependencies declared there. Do not assume an sbt directory layout or add dependencies. Use the standard library and JDK where they faithfully reproduce the Python behavior.

4. Directly create `/root/Tokenizer.scala`. It must begin with the required package and declare all requested public types and methods:

   - `TokenType`, `Token`, `BaseTokenizer`, `StringTokenizer`, `NumericTokenizer`, `TemporalTokenizer`, `UniversalTokenizer`, `WhitespaceTokenizer`, `TokenizerBuilder`
   - `tokenize`, `tokenizeBatch`, `toToken`, `withMetadata`

5. Translate idiomatically without changing observed behavior:

   - Model `TokenType` as a Scala 2.13 `sealed trait` with named `case object` members. Preserve every Python member and its exact serialized string value.
   - Model `Token` as an immutable `case class`; expose immutable metadata such as `Map[String, String]` when that matches the source.
   - Use `Option` for absent values and `Try` or `Either` internally for operations that may fail. At public boundaries preserve the Python module's actual raise, fallback, skip, or token result.
   - Use pattern matching for input/type dispatch, `java.time` plus `DateTimeFormatter` for temporal behavior, and `BigDecimal` when decimal precision is observable.
   - Preserve regex flags, captures, anchoring, split semantics, normalizer order, parsing order, and exact text transformations. Avoid guessing behavior from class names.
   - Favor `val`, immutable collections, small private helpers, camelCase methods, PascalCase types, and concise Scaladoc.

6. Keep the source compatible with conservative Scala lexical validators as well as Scala itself. **Do not place an apostrophe (`'`) anywhere in `Tokenizer.scala`**, including comments and Scaladoc. This avoids fragile source-only validators mistaking an apostrophe for an unterminated character literal. Do not use character literals or identifiers ending in an apostrophe. Use string methods, `Character`/`java.lang.Character` predicates, numeric code points, or escaped double-quoted strings instead. Also avoid Scala 3-only tokens `enum`, `given`, `using`, `extension`, and `opaque type` everywhere in the artifact, including comments. Close every ordinary/triple string and block comment, and balance all `()`, `[]`, and `{}`.

7. Validate the final file before compilation:

   ```bash
   python3 scripts/verify_translation.py <<'JSON'
   {
     "python_path":"/root/Tokenizer.py",
     "scala_path":"/root/Tokenizer.scala",
     "required_package":"tokenizer",
     "expected_symbols":[
       "TokenType","Token","BaseTokenizer","StringTokenizer",
       "NumericTokenizer","TemporalTokenizer","UniversalTokenizer",
       "WhitespaceTokenizer","TokenizerBuilder","tokenize",
       "tokenizeBatch","toToken","withMetadata"
     ]
   }
   JSON
   ```

   Do not consider the source ready unless `ok` is true. This lexical check intentionally follows the constrained source-readiness logic used when a host has no `sbt`; it is not a replacement for compilation.

8. If `sbt` is available, compile the artifact with the supplied build after placing a copy at `src/main/scala/tokenizer/Tokenizer.scala` in a temporary project containing that build file. Then compare runtime behavior with Python for source-derived examples: each token category, blank/punctuation inputs, invalid numerics/dates, empty batches, metadata merging, builder settings, and mixed universal dispatch.

## Failure handling

- If a supplied source or build file is missing, report the prerequisite instead of inventing its contents.
- If a Python dependency is not present in the build, use a JDK/Scala equivalent only when it preserves behavior. Otherwise report the incompatibility clearly.
- Do not hardcode instance-specific tokens, dates, test cases, or expected results. Derive all such values from the runtime Python module.
- Do not leave `???`, `NotImplementedError`, or `UnsupportedOperationException` placeholders in the artifact.

## Script schemas

`inspect_python.py` input:

```json
{"source_path":"/path/to/Tokenizer.py"}
```

Output fields include `ok`, SHA-256, imports, module assignments/functions, classes, method signatures, source excerpts, and a Scala camelCase checklist.

`verify_translation.py` input:

```json
{
  "python_path":"/path/to/Tokenizer.py",
  "scala_path":"/path/to/Tokenizer.scala",
  "required_package":"tokenizer",
  "expected_symbols":["OptionalExtraSymbol"]
}
```

It outputs `ok`, `errors`, `warnings`, source-derived symbols, and declared Scala types/methods. Missing files, Python parse errors, package errors, absent declarations, lexical imbalance, apostrophes, and Scala-3-only tokens are errors.
