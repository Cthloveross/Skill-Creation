---
name: python-to-scala-tokenizer
version: "1.0"
description: Translate a Python tokenizer module into an idiomatic, behavior-preserving Scala 2.13 source file. Use when the input Python file, target Scala path, and (optionally) sbt build definition are supplied at runtime.
---

# Python tokenizer module to Scala 2.13

Translate the supplied Python source into a Scala source file directly. This skill is intended for a complete module translation, not a wrapper that calls Python at runtime.

## Runtime inputs and output

Read these paths from the task request. Typical paths are `/root/Tokenizer.py`, `/root/build.sbt`, and `/root/Tokenizer.scala`; do not assume their contents or hardcode source behavior.

Required output:

- A UTF-8 Scala 2.13 source file at the requested destination.
- Its first declaration must be the requested package (for example, `package tokenizer`).
- It must expose every public class and function required by the task, with Scala-conventional method names when the task requests them.

The helper scripts accept a JSON object on standard input and emit a JSON object on standard output. They are inspection/validation aids only; the executor must write the Scala source itself.

## Procedure

1. **Inspect the actual inputs before designing types.** Read the complete Python file and build definition. Run `scripts/source_inventory.py` with `{"source":"/path/to/source.py"}` to get a structural inventory, then manually inspect all method bodies, defaults, regexes, type checks, exception paths, imports, and public/module-level functions. The AST inventory is incomplete for runtime semantics and must not replace reading the file.

2. **Establish the public Scala API from the Python behavior and task contract.** Account for constructors, inherited methods, static/class methods, fluent builder methods, defaults, aliases, return values, and batch behavior. Preserve observable token values, metadata behavior, ordering, normalization, parsing rules, and invalid-input behavior. If Python supports several input kinds, design an explicit Scala API that remains convenient for the requested callers rather than erasing all types to `Any`.

3. **Map Python constructs to idiomatic Scala 2.13.**
   - Implement a Python enum as a `sealed trait` with `case object` variants and a companion `values`/lookup method where needed.
   - Use `case class` for immutable data records such as tokens. Use immutable `Map`, `Vector`, `List`, and `Set` in public values.
   - Use traits or abstract classes for tokenizer abstractions, with concrete tokenizer implementations extending them.
   - Replace `None` with `Option`; use `map`, `flatMap`, `getOrElse`, or pattern matches rather than `null`.
   - Model expected parse/conversion failures with `Either[String, A]`, `Try[A]`, or `Option[A]`, choosing the representation compatible with the required public behavior. Do not silently discard errors that Python exposed.
   - Use sealed ADTs and exhaustive pattern matching where Python dispatches with `isinstance` or type tags.
   - Put alternative constructors, lookup functions, constants, and `apply` factories in companion objects.
   - Translate snake_case identifiers to camelCase where the task explicitly requires Scala naming (for example `tokenizeBatch`, `toToken`, `withMetadata`). Retain externally significant string keys and token text exactly unless the Python implementation transforms them.

4. **Implement behavior, not a line-by-line transcription.** Use standard-library collection operations (`map`, `flatMap`, `collect`, `foldLeft`, `mkString`) and `java.time` parsing/formatting where applicable. Compile regexes with Scala/JVM facilities and preserve Python regex flags and match-vs-search semantics deliberately. Avoid mutable public state and avoid shared mutable defaults. A builder may use an immutable case class with `copy`, or tightly scoped internal mutable state, but its resulting tokenizer configuration must not leak shared state.

5. **Handle Python dynamic inputs deliberately.** When a Python function accepts strings, numbers, dates, or existing token objects, inspect exactly which types and coercions it supports. Prefer overloads, a sealed input ADT, and/or narrowly scoped conversion helpers. If compatibility requires a broad entry point, validate values with a total pattern match and return a defined failure representation; never use an unchecked cast.

6. **Write Scala directly to the requested target.** Do not generate Scala through a Python string template. Include concise Scaladoc on public abstractions and non-obvious conversion rules. Use two-space indentation, PascalCase type names, camelCase methods/values, explicit visibility where useful, and no `null`.

7. **Compile using the actual build setup.** Inspect `build.sbt` to determine Scala version, dependencies, source directories, and the intended compile command. Because a requested standalone destination may not be under sbt's conventional `src/main/scala`, use the environment's supported compilation/validation route or temporarily place/copy only for local validation if necessary; preserve the required final destination. Do not invent dependencies absent from the build.

8. **Validate both structure and behavior.** Run `scripts/validate_scala_structure.py` with a JSON request containing the output file, package, and required symbols. Then compile with the discovered Scala 2.13 build command. Exercise representative source-derived cases: each tokenizer subtype, batch ordering, missing metadata/defaults, malformed numeric/temporal values, whitespace/empty input, and builder configuration. Correct compiler errors and semantic discrepancies in the source file, then recompile. Do not claim success based only on textual symbol presence.

## Unsupported or missing information

If the Python input cannot be read, the target cannot be written, required dependency APIs are unavailable, or the build reports a Scala version other than 2.13, report the concrete blocker rather than inventing source behavior. If the source has dynamic behavior that cannot be represented with the task's required API, preserve the supported behavior with an explicit ADT or `Either` and document the compatibility decision in Scaladoc.

## Example helper calls

```sh
python3 scripts/source_inventory.py <<'JSON'
{"source":"/root/Tokenizer.py"}
JSON

python3 scripts/validate_scala_structure.py <<'JSON'
{"source":"/root/Tokenizer.scala","package":"tokenizer","required":["TokenType","Token","BaseTokenizer","StringTokenizer","NumericTokenizer","TemporalTokenizer","UniversalTokenizer","WhitespaceTokenizer","TokenizerBuilder","tokenize","tokenizeBatch","toToken","withMetadata"]}
JSON
```

The structural validator only checks obvious declarations and balanced delimiters. A passing result is necessary evidence of delivery structure, not proof of compilation or behavioral equivalence.
