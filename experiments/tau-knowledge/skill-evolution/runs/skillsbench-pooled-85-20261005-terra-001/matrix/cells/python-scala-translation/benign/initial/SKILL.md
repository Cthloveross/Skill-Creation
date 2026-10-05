---
name: python-to-scala-tokenizer-translation
description: Translate a supplied Python tokenizer module into a directly authored, idiomatic Scala 2.13 source file. Use when a task requires behavioral parity with a Python implementation, a fixed Scala package/output path, and compilation against the supplied sbt build.
---

# Python tokenizer module to Scala 2.13

## Inputs and deliverable

This skill operates on paths supplied by the task environment. For the current task, inspect:

- Python specification: `/root/Tokenizer.py`
- Build definition: `/root/build.sbt`
- Required deliverable: `/root/Tokenizer.scala`

The deliverable must be authored as Scala source directly (not generated through Python string templates) and begin with `package tokenizer`.

Use `scripts/inspect_python_api.py` first to obtain a concise API inventory. It is an aid, not a replacement for reading the complete Python source: inspect every class, method, constant, regex, branch, default, exception handler, and data conversion in the source before implementing it.

```bash
python3 scripts/inspect_python_api.py <<'JSON'
{"source_path":"/root/Tokenizer.py","include_source":false}
JSON
```

The script writes one JSON object containing `classes`, `functions`, imports, assignments, and a suggested snake_case-to-camelCase mapping. Its input schema is `{ "source_path": string, "include_source": boolean? }`; its output is a JSON analysis report or `{ "ok": false, "error": string }` for an unreadable or invalid source file.

## Translation procedure

1. **Establish the actual contract.** Read `Tokenizer.py` in full and inspect `build.sbt` before deciding imports, source placement, or dependencies. The Python module is the behavioral specification. Preserve token fields, enum values, defaults, normalization rules, ordering, regex behavior, date/numeric parsing, metadata handling, batch behavior, and externally observable failure behavior. Do not infer behaviors that the source does not implement.
2. **Create the required file directly.** Write `/root/Tokenizer.scala`, with `package tokenizer`, rather than adding an invented sbt project hierarchy. The requested root-level path is authoritative even if it differs from conventional `src/main/scala` layout.
3. **Model domain types idiomatically.**
   - Encode `TokenType` as a `sealed trait TokenType` with `case object` members and a companion object. Give cases their source-compatible values and provide an `Option`-returning lookup when the Python source performs value/name lookup.
   - Translate Python dataclasses and immutable records to `case class`es. Use `val` fields and immutable standard collections such as `Map`, `Vector`, `Seq`, or `List` unless source-compatible mutable builder state is genuinely necessary.
   - Translate the Python base tokenizer abstraction to a `trait` or abstract class and make concrete tokenizer classes explicitly implement its operations.
   - If Python dispatches across several input kinds, prefer a sealed input ADT and exhaustive pattern matching internally, or carefully selected overloads at the public boundary when that best preserves the required callable API. Avoid a broad `Any` implementation unless parity makes it unavoidable.
4. **Translate APIs into Scala naming.** Define the required types `TokenType`, `Token`, `BaseTokenizer`, `StringTokenizer`, `NumericTokenizer`, `TemporalTokenizer`, `UniversalTokenizer`, `WhitespaceTokenizer`, and `TokenizerBuilder`. Define all source operations as well, mapping ordinary Python snake_case APIs to camelCase; in particular the required Scala names are `tokenize`, `tokenizeBatch`, `toToken`, and `withMetadata`. Constructors replace Python `__init__`; do not create a literal `__init__` method. Keep public names and parameter/default semantics compatible with the task and source.
5. **Use Scala error and absence types deliberately.** Represent an optional result with `Option`, not `null`. For fallible parsing, use `Try`, `Either`, or an explicitly documented `Option` depending on what Python does for malformed input. If the Python API deliberately raises at a public boundary, preserve that observable behavior only at that boundary; avoid exception-driven internal control flow. Do not silently turn source errors into empty values.
6. **Preserve parsing details exactly.** Port Python regular expressions carefully into Scala literals; use triple-quoted Scala strings where that reduces escaping ambiguity, while preserving the pattern itself. Use `java.time` and `DateTimeFormatter` for temporal logic when applicable, and `BigDecimal` for decimal behavior where the source requires precision. Confirm distinctions such as full-match versus substring search, trimming order, case handling, signs, decimal scale, timezone/default-date behavior, and token ordering from the Python source.
7. **Implement batch processing without hidden mutation.** Select the return collection/laziness based on the Python contract and expected Scala API. Use collection operations (`map`, `flatMap`, iterators, or folds) and immutable output collections. Ensure batch processing applies the same rules and errors as single-item tokenization.
8. **Use a companion object for factories and constants.** Put `apply`/factory alternatives, token type lookup, and stateless helpers in appropriate companions. Builder fluent methods should return a new builder when immutability is practical, or clearly encapsulate narrowly scoped mutable state while exposing immutable completed tokenizers.
9. **Document public Scala APIs.** Add concise Scaladoc to public domain types and operations, especially the meaning of token fields, unsupported input behavior, and parsing failure behavior. Use two-space indentation, PascalCase types, camelCase terms, and `private` for implementation details.

## Validation

After writing the source, run the packaged structural check:

```bash
python3 scripts/validate_translation.py <<'JSON'
{"source_path":"/root/Tokenizer.py","scala_path":"/root/Tokenizer.scala","package":"tokenizer"}
JSON
```

Input schema is `{ "source_path": string, "scala_path": string, "package": string? }`. Output schema is:

```json
{
  "ok": true,
  "errors": [],
  "warnings": [],
  "python_symbols": {"classes": [], "functions": []},
  "expected_scala_names": [],
  "found_scala_declarations": []
}
```

`ok: false` identifies structural omissions such as an absent package, required task API, or source-derived public declaration. Warnings flag review items only. This lexical validation does not prove compilation or behavioral parity.

Then use the actual compile/test entry point indicated by `/root/build.sbt` and the task environment. If the supplied build does not include `/root/Tokenizer.scala` automatically, use a compiler invocation or supported build configuration that includes this exact required file; do not duplicate the deliverable into invented source locations. Resolve all Scala 2.13 compilation errors. Finally, compare representative normal, empty, malformed, boundary numeric/temporal, metadata, and batch cases against the Python semantics by reading the source and using the task's available validation mechanism.

## Failure handling

- If the Python source or build file is absent/unreadable, report the missing prerequisite rather than fabricating its behavior.
- If a Python dependency has no supplied Scala dependency, implement only the source-required behavior with Scala/JDK standard facilities where feasible; otherwise state the unsupported dependency and preserve compilation rather than adding unapproved libraries.
- If a source construct cannot be represented exactly due to Scala static typing, isolate the compatibility boundary, document it, and keep the typed internal model exhaustive and null-free.
- Do not claim completion based only on the structural checker. Compilation and behavior validation remain required executor steps.
