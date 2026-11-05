# code-master

本地、确定性的代码情报. 复杂度、依赖、type-2 克隆、上下文预算. 零运行时依赖, 不出网, 同一棵树得到同一份报告.

A local code-intelligence engine. Each number names the paper it comes from, and the report names the cases the scanner does not cover. Python 3.11 or newer. The standard library is the whole runtime.

## Install

```bash
pip install -e .
code-master scan .
```

`pip install -e ".[dev]"` adds pytest and mypy. CI installs that extra, runs mypy, runs pytest, then runs `code-master scan src`, on Python 3.11, 3.12, and 3.13.

`code-master` exits 0, or 2 when the path does not exist. `NO_COLOR` disables color. `--json` writes schema `code-master.report.v1`. `brief` writes schema `code-master.brief.v1`.

## Commands

| command | the question it answers |
| --- | --- |
| `scan` | Where is the control flow dense? McCabe, nesting, Halstead, maintainability. |
| `graph` | Who depends on whom? Tarjan cycles, PageRank hubs, Martin instability. |
| `clones` | Which stretches are the same program with the names swapped? |
| `budget` | What fits in a context window, and what should be read first? |
| `brief` | One markdown document a reviewer or a model can take whole. |

```bash
code-master scan .
code-master graph .
code-master clones .
code-master budget . --window 8000
code-master brief . -o BRIEF.md
```

The scanner covers Python, JavaScript, TypeScript, Go, Rust, Java, Kotlin, C, C++, C#, Swift, PHP, Ruby, and SQL. Markdown, TOML, YAML, and JSON are budgeted and not measured.

## What it says about itself

The blocks below are this tree, measured by the tool that ships in it.

### `code-master scan . --top 8`

```text
code-master 0.1.0   14 files   2,818 sloc   python   mi median 58.3  mean 61.8

hotspots
  !   1.03  cc 239  nest 6   mi  51.4  src/code_master/graph.py
  !   0.67  cc 284  nest 6   mi  60.9  src/code_master/scan.py
      0.59  cc 66   nest 7   mi  54.6  src/code_master/clones.py
      0.27  cc 55   nest 4   mi  46.6  src/code_master/budget.py
      0.25  cc 65   nest 4   mi  52.8  src/code_master/render.py
      0.10  cc 13   nest 3   mi  55.7  examples/clone_a.py
     -0.06  cc 10   nest 3   mi  75.9  examples/clone_b.py
     -0.27  cc 24   nest 4   mi  47.4  src/code_master/analyze.py

functions
  cc 40   nest 5   src/code_master/scan.py:906  def _looks_like_function
  cc 30   nest 5   src/code_master/scan.py:650  def _try_number
  cc 26   nest 7   src/code_master/clones.py:159  def find_clones
  cc 26   nest 4   src/code_master/graph.py:71  def _py_from
  cc 25   nest 6   src/code_master/graph.py:135  def _py_import
  cc 24   nest 4   src/code_master/scan.py:840  def _python_functions
  cc 21   nest 4   src/code_master/render.py:132  def render_brief
  cc 20   nest 4   src/code_master/scan.py:453  def _read_py_string

cycles 0   clone runs 43   tokens ~39,759
```

How to read it.

- File cyclomatic complexity is McCabe's decision count (IEEE TSE, 1976). An empty file is 0. Any other file is `1 +` the decision tokens outside strings and comments. A function starts at 1. A nested function's decisions count for that function, and still count once for the file.
- Python nesting is the deepest line's indent, minus the `def` indent, divided by the indent unit (the gcd of the indents, else 4). A statement inside `def` + `for` + `if` is nesting 3. Brace languages use max brace depth inside the function, minus the function's own depth, plus one.
- Halstead volume and difficulty (1977) are computed on the comment-free token stream. Volume feeds the maintainability index.
- Maintainability is Coleman, Ash, Lowther, and Oman (IEEE Computer, 1994), on the Visual Studio scale. Natural log, then clamp to 0..100:

```text
MI_raw = 171 - 5.2·ln(V) - 0.23·G - 16.2·ln(SLOC)
MI     = clamp(MI_raw · 100 / 171, 0, 100)
```

  The formula takes one cyclomatic number. The file's MI is the median of its per-function values. The header prints the median and the mean of the file values together. In a skewed tree those two diverge, and a report that shows only one of them is how a number lies.

- The leading figure is a robust z-score **inside this repository**:

```text
risk = 0.45·z(CC / SLOC) + 0.25·z(nesting) + 0.20·z(ln SLOC) + 0.10·cloned
z(x) = 0.6744897501960817 · (x - median) / MAD
```

  The constant is `1 / Φ⁻¹(0.75)`. `cloned` is 1 when the file appears in a reported run, else 0. When MAD is 0, z is 0. PageRank is absent from the sum: a hub is supposed to be imported. A 1.0 here is a rank inside the tree you pointed at. It does not travel to another repository. See [ADR 0003](docs/adr/0003-risk-scale-is-the-repo.md).

`graph.py` leads because the import resolver is dense. The import hub is a different file, and it shows up under `graph`.

### `code-master graph . --top 8`

```text
code-master 0.1.0   14 files   2,818 sloc   python   mi median 58.3  mean 61.8

internal edges 29   external edges 37

cycles
  none

hubs
  0.2875  src/code_master/model.py
  0.0984  src/code_master/scan.py
  0.0726  src/code_master/cli.py
  0.0686  src/code_master/version.py
  0.0640  src/code_master/analyze.py
  0.0627  src/code_master/budget.py
  0.0627  src/code_master/clones.py
  0.0503  src/code_master/graph.py

instability  I = Ce / (Ca + Ce), internal edges only
  I 1.00  Ca 0   Ce 7   tests/test_engine.py
  I 1.00  Ca 0   Ce 3   src/code_master/__init__.py
  I 1.00  Ca 0   Ce 1   src/code_master/__main__.py
  I 0.71  Ca 2   Ce 5   src/code_master/cli.py
  I 0.67  Ca 3   Ce 6   src/code_master/analyze.py
  I 0.50  Ca 2   Ce 2   src/code_master/graph.py
  I 0.50  Ca 1   Ce 1   src/code_master/render.py
  I 0.40  Ca 3   Ce 2   src/code_master/clones.py
```

An edge A → B means A depends on B. Rank flows along that edge, so it collects on the modules other modules import (Page, Brin, Motwani, Winograd, 1999, damping 0.85, dangling mass spread evenly, stop at `1e-12` or 100 steps). `model.py` is that hub. Its risk is not on the hotspot list.

Cycles are Tarjan's strongly connected components (SIAM J. Comput., 1972). A component of size one is reported only when the node has a self-loop. This tree has no cycle, and the test suite locks that.

Instability is Martin's `I = Ce / (Ca + Ce)` on internal edges. Abstractness, and the distance to the main sequence, are left uncomputed. A scanner cannot see abstract classes reliably, and half of that pair would be a fake number.

### `code-master clones . --top 4`

```text
code-master 0.1.0   14 files   2,818 sloc   python   mi median 58.3  mean 61.8

43 runs

   175 tokens  src/code_master/scan.py:494  ~  src/code_master/scan.py:605
           ) ID , ID = ID . ID , ID . ID ID . …
   110 tokens  examples/clone_a.py:8  ~  examples/clone_b.py:14
           def ID ( ID , ID , ID , ID ) : ID = …
    83 tokens  src/code_master/graph.py:99  ~  src/code_master/graph.py:136
           ID ) ID = LIT while ID < ID : ID = ID [ …
    70 tokens  src/code_master/render.py:134  ~  src/code_master/render.py:220
           ID = [ ID for ID in ID . ID if ID . ID …
```

The longest run is the tool's own pair of string readers, `_read_py_string` and `_read_quoted`. The duplication stays. A clone detector that cannot see its own copies has nothing to show.

The second run is planted. `examples/clone_a.py` (`settle`) and `examples/clone_b.py` (`reconcile`) share a body and share no names. `code-master clones examples` reports that one pair:

```text
code-master 0.1.0   2 files   69 sloc   python   mi median 65.8  mean 65.8

1 runs

   110 tokens  clone_a.py:8  ~  clone_b.py:14
           def ID ( ID , ID , ID , ID ) : ID = …
```

Fingerprints are winnowing (Schleimer, Wilkerson, Aiken, SIGMOD 2003). Identifiers become `ID`, literals become `LIT`, keywords and operators stay. Each token is FNV-1a 64. k-gram hashes use a polynomial rolling hash modulo 2^64 with odd base `911382323`, so the base is invertible. In every window the rightmost minimum is kept. Defaults are `k = 6`, `w = 8`. A run is kept at `--min-tokens` 24 or more, and only when it contains at least two control-flow keywords, so a repeated table of strings is not a clone. Fingerprints with more than 40 postings are dropped. Overlapping runs on the same file collapse after the length sort: a later run that shares 60% of the shorter span goes.

The default threshold is sensitive. This tree reports 43 runs. Sort by length. The long runs are the finding. The short ones are echoes of the import parsers and the renderers.

### `code-master budget . --top 8`

```text
code-master 0.1.0   14 files   2,818 sloc   python   mi median 58.3  mean 61.8

window 8,000   corpus ~39,759
     8k  exceeds
    32k  exceeds
   128k  fits
   200k  fits

read first
    3738  readme           README.md
      18  entry            src/code_master/__main__.py
      49  readme           examples/README.md
      28  context          src/code_master/version.py
      70  context          src/code_master/__init__.py
     526  hub              src/code_master/model.py
      45  context          CHANGELOG.md
    1034  entry            src/code_master/cli.py
  … 6 more inside the window
```

The token estimate is for ranking and for window checks. An ASCII word costs about one token per 3.6 characters, any other ASCII character costs one, and a non-ASCII code point costs one below U+0800 and two otherwise. The reading list pins the shallowest `README.md` that fits the window, then fills by value per token. Value prefers entry points and hubs, adds the risk score, and down-weights tests. The fill is the greedy 0/1 heuristic, so the list is deterministic and the knapsack is approximate.

## Definitions

[docs/ALGORITHMS.md](docs/ALGORITHMS.md) is the specification. If that file and the code disagree, the code is wrong.

| decision | where |
| --- | --- |
| A scanner, because an AST for fourteen languages is fourteen parsers to be wrong about. | [ADR 0001](docs/adr/0001-scanner-not-parser.md) |
| The standard library only. pytest and mypy are development extras. The token estimate is not a model tokenizer. | [ADR 0002](docs/adr/0002-stdlib-only.md) |
| Risk is scaled by the repository under the cursor. Centrality is a separate report. | [ADR 0003](docs/adr/0003-risk-scale-is-the-repo.md) |

## Limits

These are the boundaries of the 0.1.0 scanner. They are also printed at the bottom of every brief.

- Comments and strings do not leak into keyword counts. The scan is still not a parse.
- Python `match` and `case` are soft keywords and stay identifiers, so structural pattern matching is under-counted.
- A Rust `match` or a Kotlin `when` counts as one decision, not one per arm.
- JavaScript regular-expression literals are not lexed. A keyword-shaped ident between slashes can be over-counted.
- C++ raw strings (`R"(...)"`) are not supported.
- Ruby `?` and `!` stay on the identifier, so `empty?` is not a ternary. `??` is a decision. `?.` is optional chaining and is not one. Rust's `?` is the try operator and is not a decision.
- Ruby and SQL report nesting 0. Their blocks are not brace-reliable.
- Clones are type-2. A reordered body is a different program to this detector.
- A module suffix that maps to two files is left unresolved, rather than guessed.
- Discover skips `.git`, virtualenvs, `node_modules`, dotfiles, lockfiles, binaries, and files over 400 KB, and it stops at 5,000 files.

## Layout

```text
src/code_master/   scanner, graph, clones, budget, render, CLI
tests/             oracles: rolling hash, winnow, MI, risk weights, the example pair
examples/          one type-2 pair, names swapped, structure kept
docs/              algorithm specification and three decision records
```

## License

MIT. Copyright (c) 2026 streaxrxoutlook-coder.
