# Python → Scala 2.13 translation reference

Distilled mappings for producing idiomatic, compilable Scala 2.13. Apply to the
actual Python definitions read at runtime.

## Type system

| Python | Idiomatic Scala 2.13 |
|--------|----------------------|
| `class X(Enum)` with string/int values | `sealed trait X { def value: String }` + `case object`s carrying `value`; companion `object X { val values: List[X] = List(...); def fromString(s: String): Option[X] = values.find(_.value == s) }` |
| `Union[A, B]` param + `isinstance` dispatch | `sealed trait Base`; `case class`/`case object` variants; exhaustive `match` |
| `Optional[T]` / `None` | `Option[T]` with `Some`/`None`; no `null`; use `map`/`flatMap`/`getOrElse`/pattern match |
| plain `TypeVar` | invariant `[A]` |
| covariant `TypeVar` | `[+A]` (only out/return positions) |
| contravariant `TypeVar` | `[-A]` (only in/argument positions) |
| `Protocol` (duck typing) | type class: `trait Capable[A]` + implicit instances in companion |
| `@dataclass` | `case class` (fields are `val`), `copy` for modified copies |
| default empty dict/list | default parameter `= Map.empty` / `= List.empty` (immutable) |
| `ABC` + `@abstractmethod` | `abstract class` or `trait` with abstract (bodiless) members; generic base → add type param |
| `classmethod` factory / class constants | companion `object` with `apply`/constants |

## Behaviour / FP idioms

- Prefer `val`; use `var` only for genuine local/builder mutation. A high
  `var:val` ratio signals a non-idiomatic literal port.
- Default collections are immutable (`List`, `Map`, `Set`, `Vector`). Use
  `scala.collection.mutable` only for internal builder state, exposing immutable
  types in public APIs.
- Replace `for` loops that accumulate into a list with `map`/`flatMap`/
  `for`-yield/`foldLeft`.
- Replace `isinstance` chains with `match` on a sealed hierarchy (exhaustive,
  compiler-checked — keep the base trait `sealed`).
- Error handling: `Try[T]` for throwing computations, `Either[L, R]` for explicit
  success/failure, `Option[T]` for presence/absence. Compose with `map`,
  `flatMap`, `recover`. Throwing is a last resort; avoid `return`.
- Every Python `None` → `Option.empty`/`None`; `None` checks → `Option` combinators.

## Naming & structure

- Types (class/trait/object): `PascalCase`.
- Methods/vals: `camelCase` — `tokenize_batch` → `tokenizeBatch`, `to_token` →
  `toToken`, `with_metadata` → `withMetadata`.
- Package: all lowercase (`package tokenizer`).
- Indentation: 2 spaces.
- Visibility: use `private`/`protected`/package-private, not underscore naming.
- Document public APIs with Scaladoc `/** ... @param ... @return ... @throws */`;
  inline comments with `//`.

## External libraries (only if build.sbt provides them)

- JSON: circe — dedicated `Json` type, parse returns `Either`, explicit
  encoders/decoders; do not use raw collections as JSON.
- Date/time: `java.time.LocalDateTime`/`LocalDate` + `DateTimeFormatter`
  (`yyyy-MM-dd'T'HH:mm:ss`).
- Decimals: `BigDecimal` with `setScale(n, roundingMode)`.
- Add no dependency absent from `build.sbt`.

## Writing the file

Write the `.scala` source **directly** (editor/heredoc), never via Python string
templates. Scala regex literals need doubled backslashes (`"\\."`, `"\\s+"`);
generating them through Python f-strings compounds escaping and breaks
compilation. Keep one package declaration at the top matching the required name.

## Correctness rule

Idiomatic restructuring must not change observable results: same tokens, same
ordering, same numeric/temporal/whitespace handling, same metadata. Mirror the
Python semantics precisely while expressing them in Scala style.
