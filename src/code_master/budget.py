"""Risk and reading order.

Risk is a weighted sum of robust z-scores inside this repository, plus a
0/1 clone flag. It is not a probability and it is not comparable across
repositories: the scale is the repo's own median and MAD.

The reading list pins the shallowest README that fits, then fills the
remaining window by value density. That is the greedy 0/1 heuristic, not
the exact knapsack.
"""

from __future__ import annotations

import math
import posixpath
import statistics

from code_master.model import Clone, FileView, Reading

# Weights sum to 1. Centrality is not in here: a stable hub is supposed to
# be imported, and `graph` already reports it. The clone term is a flag,
# not a z-score, so one cloned file still moves when MAD would be 0.
W_CC = 0.45
W_NEST = 0.25
W_SIZE = 0.20
W_CLONE = 0.10

# 1 / Φ⁻¹(0.75). MAD × this estimates σ on a normal sample. We use it so a
# z-score is on a familiar scale; the score is still comparative, not a
# claim that the repository is normal.
_MAD_K = 0.6744897501960817

DEFAULT_WINDOW = 8_000

_ENTRY = frozenset(
    {
        "main.py",
        "__main__.py",
        "cli.py",
        "app.py",
        "server.py",
        "index.js",
        "index.ts",
        "main.js",
        "main.ts",
        "main.go",
        "main.rs",
        "lib.rs",
        "mod.rs",
        "main.java",
        "program.cs",
        "app.swift",
    }
)


def estimate_tokens(text: str) -> int:
    """Order-of-magnitude token estimate. Not a billing figure.

    An ASCII word costs about one token per 3.6 characters. Any other ASCII
    character costs one. A non-ASCII code point costs one below U+0800 and
    two otherwise. Use it to rank files and to see whether a tree fits a
    window. It is not a model tokenizer.
    """
    if not text.strip():
        return 0
    count = 0
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        code = ord(ch)
        if ch.isspace():
            i += 1
            continue
        if code < 128 and (ch.isalnum() or ch == "_"):
            j = i + 1
            while j < length and ord(text[j]) < 128 and (text[j].isalnum() or text[j] == "_"):
                j += 1
            count += max(1, round((j - i) / 3.6))
            i = j
            continue
        if code < 128:
            count += 1
            i += 1
            continue
        count += 1 if code < 0x800 else 2
        i += 1
    return count


def robust_z(values: list[float], x: float) -> float:
    if not values:
        return 0.0
    med = statistics.median(values)
    mad = statistics.median([abs(value - med) for value in values])
    if mad == 0:
        return 0.0
    return _MAD_K * (x - med) / mad


def score_risk(
    files: list[FileView],
    clones: tuple[Clone, ...],
) -> tuple[tuple[str, float], ...]:
    code = [f for f in files if f.kind == "code" and f.sloc > 0]
    if not code:
        return ()
    cloned = {clone.left for clone in clones} | {clone.right for clone in clones}
    densities = [f.cyclomatic / f.sloc for f in code]
    nests = [float(f.max_nesting) for f in code]
    sizes = [math.log(f.sloc) for f in code]
    scored: list[tuple[str, float]] = []
    for f, density, nest, size in zip(code, densities, nests, sizes, strict=True):
        value = (
            W_CC * robust_z(densities, density)
            + W_NEST * robust_z(nests, nest)
            + W_SIZE * robust_z(sizes, size)
            + (W_CLONE if f.path in cloned else 0.0)
        )
        scored.append((f.path, value))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return tuple(scored)


def _is_test(path: str) -> bool:
    base = posixpath.basename(path).lower()
    parts = path.lower().split("/")
    if any(part in {"test", "tests", "__tests__", "spec"} for part in parts):
        return True
    if base.startswith("test_") or base.endswith("_test.py") or base.endswith("_test.go"):
        return True
    if ".test." in base or ".spec." in base:
        return True
    return False


def _value(path: str, kind: str, risk: float, rank: float, max_rank: float) -> tuple[float, str]:
    base = posixpath.basename(path).lower()
    value = 0.3
    why: list[str] = []
    if base == "readme.md":
        value += 6.0
        why.append("readme")
    if base in _ENTRY:
        value += 4.0
        why.append("entry")
    if max_rank > 0 and rank > 0:
        value += 3.0 * (rank / max_rank)
        if rank >= max_rank * 0.5:
            why.append("hub")
    if risk > 0:
        value += risk
        if risk >= 0.5:
            why.append("risk")
    if not why:
        why.append("context")
    if _is_test(path):
        value *= 0.25
        why.append("test")
    if kind == "doc" and "readme" not in why:
        value *= 0.8
    return value, "+".join(why)


def select_reading(
    files: list[FileView],
    risk: dict[str, float],
    rank: dict[str, float],
    window: int,
) -> tuple[Reading, ...]:
    if window <= 0:
        return ()
    max_rank = max(rank.values(), default=0.0)
    items: list[Reading] = []
    for f in files:
        if f.tokens_est <= 0:
            continue
        value, why = _value(f.path, f.kind, risk.get(f.path, 0.0), rank.get(f.path, 0.0), max_rank)
        items.append(Reading(f.path, f.tokens_est, value, why))
    items.sort(key=lambda item: (-(item.value / item.tokens), item.path))

    chosen: list[Reading] = []
    used = 0
    readmes = [item for item in items if posixpath.basename(item.path).lower() == "readme.md"]
    readmes.sort(key=lambda item: (item.path.count("/"), item.path))
    pinned: set[str] = set()
    if readmes and readmes[0].tokens <= window:
        chosen.append(readmes[0])
        used += readmes[0].tokens
        pinned.add(readmes[0].path)
    for item in items:
        if item.path in pinned:
            continue
        if used + item.tokens <= window:
            chosen.append(item)
            used += item.tokens
            pinned.add(item.path)
    return tuple(chosen)
