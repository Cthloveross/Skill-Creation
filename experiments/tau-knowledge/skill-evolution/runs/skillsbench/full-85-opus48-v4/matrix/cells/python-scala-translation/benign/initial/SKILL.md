---
name: python-to-scala-translation
description: Translate a Python module (data-preparation/tokenizer code) into one idiomatic Scala 2.13 source file that preserves behaviour and all public types/functions, declares a required package, and compiles. Use when the task supplies a Python file and asks for an idiomatic, compilable Scala deliverable at a specified path.
---

# Python → idiomatic Scala 2.13 translation

## What this task requires

The public task gives a Python source file (e.g. `/root/Tokenizer.py`) and a
`build.sbt` (e.g. `/root/build.sbt`). You must write a single Scala file (e.g.
`/root/Tokenizer.scala`) that:

1. Declares the required package (the opening states `package tokenizer`).
2. Contains **every** class/function the task names (for the current instance:
   `TokenType, Token, BaseTokenizer, StringTokenizer, NumericTokenizer,
   TemporalTokenizer, UniversalTokenizer, WhitespaceTokenizer, TokenizerBuilder,
   tokenize, tokenizeBatch, toToken, withMetadata`). Always re-read the opening
   to confirm the exact required names and output path for the instance you are
   running — do not assume this list.
3. Does the same thing as the Python code.
4. Compiles with Scala 2.13.
5. Follows idiomatic Scala (functional, immutable, type-safe) rather than a
   word-for-word translation.

The actual Python contents are instance-specific. **Read the supplied Python
file at runtime** and translate its real definitions — never rely on remembered
or example contents.

## Method (executor steps)

1. **Read inputs.**
   - `cat` the opening/task to confirm the output path, package name, and the
     exact required identifier list.
   - `cat` the Python source (path from the manifest, e.g. `/root/Tokenizer.py`)
     and read it in full. Note every `class`, `def`, enum, dataclass, default
     argument, exception path, and `None`/`Optional` usage.
   - `cat /root/build.sbt` to learn the Scala version, dependencies (e.g. circe),
     and how sources are compiled.

2. **Translate directly into the Scala file.** Write `/root/Tokenizer.scala`
   (or the instance's required path) by hand/editor — do **not** generate Scala
   via Python string templates/f-strings (multi-layer escaping of regex like
   `\\.` / `\\s+` and char literals is a common compile-failure source). Apply
   the mappings in `references/translation-guide.md`:
   - Python `Enum` → `sealed trait` + `case object`s (with value field) and a
     companion `object` holding `values` and `fromString`.
   - `Union[...]`/`isinstance` dispatch → sealed-trait ADT + exhaustive `match`.
   - `Optional[T]`/`None` → `Option[T]` (`Some`/`None`); never use `null`.
   - exceptions → `Try`/`Either`/`Option`, composed with `map`/`flatMap`/`recover`.
   - `@dataclass` → `case class` (immutable `val` fields, `copy`), default empty
     dict → default immutable `Map`.
   - fluent builder returning `self` → default immutable-collection params +
     `copy`/returned builder; abstract base → `abstract class`/`trait`.
   - `classmethod` factories/constants → companion `object` with `apply`.
   - snake_case methods → camelCase; types PascalCase; package lowercase;
     2-space indent; Scaladoc `/** ... */` for public APIs.
   - prefer `val` over `var`, immutable collections, `map`/`filter`/`flatMap`/
     `for`-comprehensions over imperative loops.
   - Preserve observable behaviour exactly (same tokenization output, same
     ordering, same numeric/temporal/whitespace rules). Idiomatic restructuring
     must not change results.

3. **Static self-check.** Run `scripts/validate.py` (schema below) to confirm the
   package declaration, every required identifier, Python-vs-Scala coverage, and
   idiom signals (no `null`, Option/Try usage, low `var` ratio). Fix anything it
   flags before compiling.

4. **Compile.** Run `scripts/compile.py` to build with the project's own
   `build.sbt` (internet is allowed for dependency download; build timeout is
   generous). Treat a non-zero exit or any `error:` lines as failure, read the
   captured output, correct the Scala, and recompile until it compiles cleanly.
   If `sbt` is unavailable the script falls back to `scalac`; if neither is
   present, report that compilation could not be verified and still deliver the
   best idiomatic file.

5. **Deliver.** Leave the finished Scala file at the required path. The file
   itself is the deliverable; the scripts only assist and verify.

## Scripts

### scripts/validate.py
Static checker. Does not need a compiler.
- stdin JSON: `{"scala_path": "/root/Tokenizer.scala", "python_path": "/root/Tokenizer.py", "package": "tokenizer", "required": ["TokenType", ...]}`
  - `python_path`, `package`, `required` are optional. If `required` is omitted
    the script still cross-checks against names parsed from `python_path`.
- stdout JSON: `{"ok": bool, "errors": [..], "warnings": [..], "missing_required": [..], "python_names_absent": [..], "var_count": int, "val_count": int, "uses_option": bool, "uses_try_or_either": bool, "uses_null": bool}`
- `ok` is false when the file is missing, the package line is wrong, or any
  required identifier is absent. `warnings` carry idiom concerns (null usage,
  high var ratio, `return`/`throw` usage, missing Option/Try) that you should
  address but which are not hard failures.

### scripts/compile.py
Compilation wrapper.
- stdin JSON: `{"workdir": "/root", "scala_path": "/root/Tokenizer.scala"}` (both optional; defaults shown).
- Behaviour: if `build.sbt` exists and `sbt` is on PATH, runs `sbt compile` in
  `workdir`; else tries `scalac` on the file; reports which was used.
- stdout JSON: `{"ok": bool, "tool": "sbt|scalac|none", "returncode": int, "has_error_lines": bool, "output_tail": "...", "cmd": "..."}`
- `ok` requires return code 0 and no `error:` lines. Inspect `output_tail` on
  failure.

## Running the scripts
```
echo '{"scala_path":"/root/Tokenizer.scala","python_path":"/root/Tokenizer.py","package":"tokenizer"}' | python3 scripts/validate.py
echo '{"workdir":"/root","scala_path":"/root/Tokenizer.scala"}' | python3 scripts/compile.py
```
(Adjust paths to the current instance's manifest.)

## Failure handling
- If a Python construct has no clean idiomatic Scala form, choose the closest
  type-safe encoding (ADT/Option/Try) and keep behaviour identical; document the
  choice with a brief Scaladoc/inline comment rather than inventing new APIs.
- Do not add dependencies not present in `build.sbt`. If the translation needs
  JSON/date handling, use what `build.sbt` already provides (e.g. circe,
  `java.time`); otherwise stay on the standard library.
- Never hardcode a previously seen translation — regenerate from the Python that
  is present now.
