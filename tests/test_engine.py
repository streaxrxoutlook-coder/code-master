"""Oracle tests. Each one locks a formula or a known small input."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

import pytest

from code_master.budget import W_CC, W_CLONE, W_NEST, W_SIZE, estimate_tokens, robust_z, select_reading
from code_master.cli import main
from code_master.clones import find_clones, kgram_hashes, normalize, token_hash, winnow
from code_master.graph import build_graph, extract_imports, pagerank, tarjan
from code_master.model import FileView
from code_master.scan import is_decision, language_for, maintainability, measure, tokenize
from code_master.analyze import analyze

ROOT = Path(__file__).resolve().parents[1]


def _py(text: str):
    lang = language_for("a.py")
    assert lang is not None
    return measure(text, lang)


def test_decisions_ignore_strings_and_comments() -> None:
    measured = _py(
        'def f():\n'
        '    s = "if for while and or"\n'
        "    # if for while\n"
        "    return s\n"
    )
    assert measured.cyclomatic == 1
    assert measured.sloc == 3


def test_python_cyclomatic_and_function() -> None:
    text = (
        "def score(xs, flag):\n"
        "    total = 0\n"
        "    for x in xs:\n"
        "        if x and flag:\n"
        "            total += x\n"
        "        elif x:\n"
        "            total -= 1\n"
        "    return total\n"
    )
    measured = _py(text)
    # for, if, and, elif
    assert measured.cyclomatic == 5
    assert len(measured.functions) == 1
    fn = measured.functions[0]
    assert fn.name == "score"
    assert fn.kind == "def"
    assert fn.line == 1
    assert fn.cyclomatic == 5
    # def + for + if. The body of the if is three blocks deep.
    assert fn.nesting == 3


def test_fstring_expression_is_code() -> None:
    measured = _py('def f(x):\n    return f"{1 if x else 2}"\n')
    assert measured.cyclomatic == 2


def test_fstring_brace_inside_string_does_not_end_early() -> None:
    text = """def f(x):\n    return f\"{'}' if x else '{'}\"\n"""
    measured = _py(text)
    assert measured.cyclomatic == 2


def test_module_if_is_not_charged_to_the_function() -> None:
    text = "if DEBUG:\n    def f():\n        return 1\n"
    measured = _py(text)
    assert measured.cyclomatic == 2
    assert measured.functions[0].cyclomatic == 1
    assert measured.functions[0].name == "f"


def test_async_def_and_class_method() -> None:
    text = (
        "class Box:\n"
        "    async def get(self, x):\n"
        "        if x:\n"
        "            return x\n"
        "        return None\n"
    )
    measured = _py(text)
    names = {(fn.kind, fn.name, fn.cyclomatic) for fn in measured.functions}
    assert ("class", "Box", 1) in names
    assert ("def", "get", 2) in names


def test_c_function_and_boolean_ops() -> None:
    lang = language_for("a.c")
    assert lang is not None
    text = "int f(int x) {\n  if (x > 0 && y) {\n    return 1;\n  }\n  return 0;\n}\n"
    measured = measure(text, lang)
    assert measured.cyclomatic == 3
    assert measured.functions[0].name == "f"
    assert measured.functions[0].cyclomatic == 3
    assert measured.functions[0].nesting == 2


def test_optional_chain_is_not_a_ternary() -> None:
    lang = language_for("a.ts")
    assert lang is not None
    tokens = tokenize("const a = obj?.x ?? obj.y ? 1 : 0\n", lang)
    decisions = [tok.text for tok in tokens if is_decision(tok, lang)]
    assert "??" in decisions
    assert "?." not in decisions
    assert "?" in decisions


def test_generic_method_name() -> None:
    lang = language_for("a.java")
    assert lang is not None
    text = "class A {\n  <T> List<T> foo(T x) {\n    if (x == null) return null;\n    return null;\n  }\n}\n"
    measured = measure(text, lang)
    names = [fn.name for fn in measured.functions]
    assert "foo" in names


def test_maintainability_matches_the_paper() -> None:
    volume = 100.0
    cc = 5
    sloc = 20
    raw = 171 - 5.2 * math.log(volume) - 0.23 * cc - 16.2 * math.log(sloc)
    expect = max(0.0, min(100.0, raw * 100 / 171))
    assert maintainability(volume, cc, sloc) == pytest.approx(expect)


def test_empty_file_has_no_cyclomatic() -> None:
    assert _py("").cyclomatic == 0
    assert _py("# just a comment\n").cyclomatic == 0


def test_rolling_hash_matches_scratch(seed: int = 0) -> None:
    del seed
    texts = ["ID", "if", "(", "LIT", ")", "{", "return", "ID", "}"]
    k = 4
    got = kgram_hashes(texts, k)
    expect = []
    for i in range(len(texts) - k + 1):
        value = 0
        for text in texts[i : i + k]:
            value = (value * 911382323 + token_hash(text)) & ((1 << 64) - 1)
        expect.append(value)
    assert got == expect


def test_winnow_matches_rightmost_minimum() -> None:
    rng = random.Random(7)
    hashes = [rng.randrange(20) for _ in range(80)]
    w = 5

    def naive(values: list[int], width: int) -> list[tuple[int, int]]:
        out = []
        last = -1
        for start in range(len(values) - width + 1):
            window = values[start : start + width]
            minimum = min(window)
            rel = width - 1 - window[::-1].index(minimum)
            idx = start + rel
            if idx != last:
                out.append((idx, values[idx]))
                last = idx
        return out

    assert winnow(hashes, w) == naive(hashes, w)


def test_tarjan_cycle_and_self_loop() -> None:
    nodes = ["a", "b", "c", "d"]
    edges = [("a", "b"), ("b", "c"), ("c", "a"), ("d", "d")]
    comps = tarjan(nodes, edges)
    assert comps == [["a", "b", "c"], ["d"]]


def test_pagerank_sink_outranks_source_and_sums_to_one() -> None:
    rank = pagerank(["a", "b"], [("a", "b")])
    assert rank["b"] > rank["a"]
    assert sum(rank.values()) == pytest.approx(1.0)
    cycle = pagerank(["a", "b"], [("a", "b"), ("b", "a")])
    assert cycle["a"] == pytest.approx(cycle["b"])


def test_python_import_cycle_and_relative() -> None:
    files = [
        ("pkg/a.py", "python", ("pkg.b",)),
        ("pkg/b.py", "python", ("pkg.a",)),
        ("pkg/cli.py", "python", (".scan",)),
        ("pkg/scan.py", "python", ()),
        ("pkg/cli.py", "python", (".scan",)),
    ]
    # rebuild without the duplicate cli row
    files = files[:4]
    graph = build_graph(files)
    cycles = {tuple(comp) for comp in graph.cycles}
    assert ("pkg/a.py", "pkg/b.py") in cycles
    internal = {(e.src, e.dst) for e in graph.edges if e.kind == "internal"}
    assert ("pkg/cli.py", "pkg/scan.py") in internal


def test_extract_python_from_import_dot() -> None:
    lang = language_for("a.py")
    assert lang is not None
    tokens = tokenize("from . import scan\nfrom .graph import Edge\nimport os.path as path, sys\n", lang)
    assert extract_imports(tokens, lang) == (".scan", ".graph", "os.path", "sys")


def test_extract_js_and_go() -> None:
    js = language_for("a.ts")
    assert js is not None
    text = 'import { a } from "./util";\nimport fs from "fs";\nconst p = require("path");\n'
    assert extract_imports(tokenize(text, js), js) == ("./util", "fs", "path")
    go = language_for("a.go")
    assert go is not None
    got = extract_imports(tokenize('import (\n\t"fmt"\n\t"os"\n)\n', go), go)
    assert got == ("fmt", "os")


def test_clone_survives_rename(tmp_path: Path) -> None:
    body_a = (
        "def settle(entries, ceiling, allow_negative, floor_value):\n"
        "    total = 0\n"
        "    skipped = 0\n"
        "    seen = 0\n"
        "    for entry in entries:\n"
        "        seen = seen + 1\n"
        "        if entry is None:\n"
        "            skipped = skipped + 1\n"
        "            continue\n"
        "        if entry > ceiling and allow_negative:\n"
        "            total = total + entry - floor_value\n"
        "        elif entry < 0:\n"
        "            total = total - 1\n"
        "        elif entry == 0:\n"
        "            skipped = skipped + 1\n"
        "        else:\n"
        "            total = total + 1\n"
        "        if total > ceiling:\n"
        "            total = ceiling\n"
        "            break\n"
        "    if skipped > ceiling:\n"
        "        return total\n"
        "    if seen == 0:\n"
        "        return floor_value\n"
        "    return total - skipped\n"
    )
    body_b = (
        "def reconcile(rows, cap, keep_negative, base):\n"
        "    total = 0\n"
        "    skipped = 0\n"
        "    seen = 0\n"
        "    for row in rows:\n"
        "        seen = seen + 1\n"
        "        if row is None:\n"
        "            skipped = skipped + 1\n"
        "            continue\n"
        "        if row > cap and keep_negative:\n"
        "            total = total + row - base\n"
        "        elif row < 0:\n"
        "            total = total - 1\n"
        "        elif row == 0:\n"
        "            skipped = skipped + 1\n"
        "        else:\n"
        "            total = total + 1\n"
        "        if total > cap:\n"
        "            total = cap\n"
        "            break\n"
        "    if skipped > cap:\n"
        "        return total\n"
        "    if seen == 0:\n"
        "        return base\n"
        "    return total - skipped\n"
    )
    (tmp_path / "a.py").write_text("import math\nLIMIT = 5\n" + body_a + "\ndef only_a(v):\n    return v + 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("class Bucket:\n    def push(self, v):\n        return v\n" + body_b, encoding="utf-8")
    report = analyze(tmp_path, min_clone=24)
    assert report.clones
    pair = {(c.left, c.right) for c in report.clones}
    assert ("a.py", "b.py") in pair
    assert report.clones[0].tokens >= 24


def test_readme_is_pinned_first(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# hi\n\nshort\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")
    report = analyze(tmp_path, window=8000)
    assert report.reading
    assert report.reading[0].path == "README.md"
    assert "readme" in report.reading[0].why


def test_weights_sum_to_one() -> None:
    assert W_CC + W_NEST + W_SIZE + W_CLONE == pytest.approx(1.0)


def test_fstring_inside_a_call_does_not_swallow_the_rest_of_the_file() -> None:
    text = 'def f(x):\n    print(f"{x:<4} {x}")\n    if x:\n        return 1\n'
    measured = _py(text)
    assert measured.cyclomatic == 2
    assert measured.functions[0].name == "f"
    assert measured.functions[0].cyclomatic == 2
    assert measured.functions[0].sloc == 4


def test_robust_z_is_zero_at_the_median() -> None:
    assert robust_z([1, 2, 3, 4, 100], 3) == pytest.approx(0.0)
    assert robust_z([1, 1, 1], 1) == 0.0


def test_estimate_tokens_is_positive_and_grows() -> None:
    assert estimate_tokens("   \n") == 0
    short = estimate_tokens("return x\n")
    long = estimate_tokens("return x\n" * 20)
    assert short > 0
    assert long > short


def test_cli_json_and_missing_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.py").write_text("def f(x):\n    return x\n", encoding="utf-8")
    assert main(["scan", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "code-master.report.v1"
    assert payload["files"][0]["cyclomatic"] == 1
    err = capsys.readouterr()
    assert main(["scan", str(tmp_path / "missing")]) == 2
    assert "no such path" in capsys.readouterr().err


def test_examples_are_a_type2_pair() -> None:
    report = analyze(ROOT / "examples", min_clone=24)
    pairs = {(c.left, c.right) for c in report.clones}
    assert ("clone_a.py", "clone_b.py") in pairs


def test_src_analyzes() -> None:
    report = analyze(ROOT / "src")
    assert report.files
    assert report.cycles == ()


def test_select_reading_respects_window() -> None:
    files = [
        FileView(
            path="README.md", language="markdown", kind="doc", bytes=10, lines=1, sloc=1,
            comment_lines=0, blank_lines=0, cyclomatic=0, max_nesting=0, maintainability=None,
            halstead_volume=0, halstead_difficulty=0, tokens_est=100, functions=(), imports=(),
        ),
        FileView(
            path="big.py", language="python", kind="code", bytes=10, lines=1, sloc=1,
            comment_lines=0, blank_lines=0, cyclomatic=1, max_nesting=0, maintainability=None,
            halstead_volume=0, halstead_difficulty=0, tokens_est=500, functions=(), imports=(),
        ),
    ]
    chosen = select_reading(files, {}, {}, window=100)
    assert [item.path for item in chosen] == ["README.md"]
