# Algorithms

The numbers in a report are defined here. If this file and the code disagree, the code is wrong.

## Scanner

`code_master.scan` is a scanner. It keeps comments, strings, and identifiers from leaking into each other. It does not build an AST.

Python `match` and `case` are soft keywords and stay identifiers, so a variable named `case` is not a branch. Structural pattern matching is under-counted. A Rust `match` or a Kotlin `when` counts as one decision, not one per arm. JavaScript regular-expression literals are not recognized; a keyword-shaped ident between slashes can be over-counted.

## Cyclomatic complexity

McCabe, IEEE TSE, 1976, in the usual decision-count form.

A file with no source lines has complexity 0. Otherwise the file is `1 +` the number of decision tokens. A function starts at 1 and adds the decisions in its own body. A nested function's decisions count for the nested function, and still count once for the file.

Decision tokens are the language's decision keywords (`if`, `elif`, `for`, `while`, `case`, `catch`, `except`, …), the boolean operators of that language (`&&`, `||`, and the keyword forms `and` / `or` where those are real keywords), `??`, and a bare `?` in languages that have a ternary. `?.` is optional chaining and is not a decision. Rust's `?` is the try operator and is not a decision.

## Nesting

Python: indentation unit is the greatest common divisor of the positive code-line indents, or 4 when the file is flat. A tab is eight spaces. File nesting is the deepest code line's indent divided by that unit. Function nesting is the same gap measured from the `def` or `class` line. A body three blocks under the `def` (function, `for`, `if`) is nesting 3.

Brace languages: file nesting is the maximum brace depth. Function nesting is the maximum depth reached inside the function, minus the function's own brace depth, plus one. A flat function is 1. An `if` inside it is 2.

Ruby and SQL report nesting 0. Their block structure is not brace-reliable, and pretending otherwise would be a fake number.

## Halstead

Halstead, *Elements of Software Science*, 1977, on the token stream with comments removed.

- Operators: keywords and symbols. Each distinct text is one operator.
- Operands: identifiers and literals.
- `n1`, `n2`: distinct operators, distinct operands. `N1`, `N2`: totals.
- Volume `V = N · log2(n)` with `n = n1 + n2` and `N = N1 + N2`.
- Difficulty `D = (n1 / 2) · (N2 / n2)`.

Empty or single-token files report volume 0 and difficulty 0.

## Maintainability index

Coleman, Ash, Lowther, and Oman, IEEE Computer, 1994, in the Visual Studio scaling:

```
MI_raw = 171 - 5.2·ln(V) - 0.23·G - 16.2·ln(SLOC)
MI     = clamp(MI_raw · 100 / 171, 0, 100)
```

`ln` is the natural logarithm. SLOC is physical source lines, blanks and comment-only lines removed.

The formula takes one cyclomatic number. Feeding it the *sum* across a thousand-line module drives the index to 0, which is the aggregation, not the module. The file's reported MI is the median of its per-function values. A file with no functions falls back to one application of the formula on the whole file.

## Clones

Schleimer, Wilkerson, and Aiken, "Winnowing: Local Algorithms for Document Fingerprinting", SIGMOD 2003.

Normalization is type-2. Identifiers become `ID`, literals become `LIT`, keywords and operators stay. Comments and newlines drop out.

Each token is hashed with FNV-1a to 64 bits. k-gram hashes (`k = 6` by default) use the polynomial rolling hash modulo 2^64:

```
h = (h - out · BASE^(k-1)) · BASE + inn
BASE = 911382323
```

`BASE` is odd, so it is invertible modulo 2^64. In every window of `w = 8` k-gram hashes the minimum is kept, ties broken toward the rightmost position (a deque does this in one pass; the tests check it against the direct definition).

A shared fingerprint is expanded backward and forward while the k-gram hashes match. The reported length is the token span, which is longer than the fingerprint. Fingerprints that occur more than 40 times are dropped; they are stop-words. A run is kept when it is at least `--min-tokens` long (default 24) and contains at least two control-flow keywords, so a repeated table of string literals is not a clone. Overlapping runs on the same file are collapsed after sorting by length: a later run that shares 60% of the shorter span is dropped.

Same-file matches require the two spans not to overlap, and a fingerprint is not paired with itself.

## Imports, cycles, rank, instability

Resolution is syntactic.

- Python: absolute and relative imports, dotted modules, `from . import name` as a submodule. A module suffix that maps to two files is left unresolved rather than guessed.
- JavaScript and TypeScript: the last string in an `import` / `export` statement, plus `require("…")` and `import("…")`. Only relative specifiers become internal edges.
- Go: import strings. A path whose first element contains a dot can match a directory suffix in the tree. The standard library (`fmt`, no dot) stays external.
- Rust: `crate::` from `src/`, and `super::`. The longest existing `foo.rs` or `foo/mod.rs` wins.
- Java and Kotlin: `import a.b.C` matches a unique `a/b/C.java` (or `.kt`) suffix.

An edge `A → B` means A depends on B.

Cycles are Tarjan's strongly connected components (SIAM J. Comput., 1972). A component of size one is reported only when the node has a self-loop. Components are sorted for a stable report.

PageRank (Page, Brin, Motwani, Winograd, 1999) uses damping 0.85. Rank flows along the edge, so it collects on modules other modules import. Dangling mass is spread evenly. The iteration stops at a change below `1e-12` or after 100 steps.

Instability, in Martin's sense, uses internal edges only: `I = Ce / (Ca + Ce)`, and 0 when a file has neither. Abstractness and the distance from the main sequence are not computed; this scanner cannot see abstract classes reliably, and a half-computed main sequence would be a fake one.

## Risk

Inside one repository, on code files with at least one source line:

```
risk = 0.45·z(CC / SLOC) + 0.25·z(nesting) + 0.20·z(ln SLOC) + 0.10·clone
```

`clone` is 1 when the file is in a reported run, else 0. `z` is a median/MAD z-score:

```
z(x) = 0.6744897501960817 · (x - median) / MAD
```

The constant is `1 / Φ⁻¹(0.75)`, so that MAD estimates a standard deviation on a normal sample. When MAD is 0, `z` is 0. The score is comparative inside this repository. It is not a probability, and it is not comparable to another repository's score.

PageRank is not in the score. A stable hub is supposed to be imported. Hubs are reported by `graph`.

## Tokens and the reading list

The token estimate is not a model tokenizer. An ASCII word costs about one token per 3.6 characters, any other ASCII character costs one, and a non-ASCII code point costs one below U+0800 and two otherwise. Use it to rank files and to see whether a tree fits a window.

The reading list pins the shallowest `README.md` that fits the window, then fills the rest by value per token. Value prefers entry points (`cli.py`, `main.go`, `lib.rs`, …) and hubs, adds the risk score, and down-weights tests. The fill is the greedy 0/1 heuristic, not an exact knapsack. Ties break by path, so the list is deterministic.
