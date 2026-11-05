"""Import graph: extract, resolve, Tarjan SCCs, PageRank, instability.

An edge A → B means A depends on B. Rank therefore collects on modules
that other modules import. External specifiers that do not resolve to a
file in the tree stay external and do not enter the cycle or rank math.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass

from code_master.model import Coupling, Edge
from code_master.scan import Lang, Token


def extract_imports(tokens: list[Token], lang: Lang) -> tuple[str, ...]:
    if lang.family == "py":
        return tuple(_py_imports(tokens))
    if lang.name in {"javascript", "typescript"}:
        return tuple(_js_imports(tokens))
    if lang.name == "go":
        return tuple(_go_imports(tokens))
    if lang.name == "rust":
        return tuple(_rust_imports(tokens))
    if lang.name in {"java", "kotlin"}:
        return tuple(_java_imports(tokens))
    return ()


def _skip_noise(tokens: list[Token], i: int) -> int:
    while i < len(tokens) and tokens[i].kind in {"nl", "comment"}:
        i += 1
    return i


def _py_imports(tokens: list[Token]) -> list[str]:
    """Python import specs.

    Newlines end a statement unless parentheses are open. Comments never do.
    ``from . import scan`` records the submodule ``.scan``; ``from .graph import Edge``
    records the module ``.graph``.
    """
    out: list[str] = []
    i = 0
    n = len(tokens)

    def skip_comment(j: int) -> int:
        while j < n and tokens[j].kind == "comment":
            j += 1
        return j

    while i < n:
        i = skip_comment(i)
        if i >= n:
            break
        tok = tokens[i]
        if tok.kind == "nl":
            i += 1
            continue
        if tok.kind == "kw" and tok.text == "from":
            i = _py_from(tokens, i + 1, out)
            continue
        if tok.kind == "kw" and tok.text == "import":
            i = _py_import(tokens, i + 1, out)
            continue
        i += 1
    return out


def _py_from(tokens: list[Token], i: int, out: list[str]) -> int:
    n = len(tokens)

    def skip_comment(j: int) -> int:
        while j < n and tokens[j].kind == "comment":
            j += 1
        return j

    i = skip_comment(i)
    level = 0
    while i < n and tokens[i].text == ".":
        level += 1
        i = skip_comment(i + 1)
    parts: list[str] = []
    while i < n and tokens[i].kind in {"ident", "kw"} and not (tokens[i].kind == "kw" and tokens[i].text == "import"):
        parts.append(tokens[i].text)
        i = skip_comment(i + 1)
        if i < n and tokens[i].text == ".":
            i = skip_comment(i + 1)
            continue
        break
    i = skip_comment(i)
    if i >= n or not (tokens[i].kind == "kw" and tokens[i].text == "import"):
        return i
    i = skip_comment(i + 1)
    module = ".".join(parts)
    if module:
        out.append("." * level + module)
        return _skip_statement(tokens, i)
    depth = 0
    while i < n:
        tok = tokens[i]
        if tok.kind == "comment":
            i += 1
            continue
        if tok.kind == "nl" and depth == 0:
            return i + 1
        if tok.text == "(":
            depth += 1
            i += 1
            continue
        if tok.text == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if tok.kind == "nl":
            i += 1
            continue
        if tok.kind == "kw" and tok.text == "as":
            i = skip_comment(i + 1)
            if i < n and tokens[i].kind in {"ident", "kw"}:
                i += 1
            continue
        if tok.kind in {"ident", "kw"}:
            out.append("." * level + tok.text)
            i += 1
            continue
        if tok.text == ",":
            i += 1
            continue
        i += 1
    return i


def _py_import(tokens: list[Token], i: int, out: list[str]) -> int:
    n = len(tokens)
    depth = 0
    while i < n:
        tok = tokens[i]
        if tok.kind == "comment":
            i += 1
            continue
        if tok.kind == "nl" and depth == 0:
            return i + 1
        if tok.text == "(":
            depth += 1
            i += 1
            continue
        if tok.text == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if tok.kind == "nl" or tok.text == ",":
            i += 1
            continue
        if tok.kind == "kw" and tok.text == "as":
            i += 1
            while i < n and tokens[i].kind == "comment":
                i += 1
            if i < n and tokens[i].kind in {"ident", "kw"}:
                i += 1
            continue
        if tok.kind in {"ident", "kw"}:
            parts = [tok.text]
            i += 1
            while i < n:
                while i < n and tokens[i].kind == "comment":
                    i += 1
                if i < n and tokens[i].text == ".":
                    i += 1
                    while i < n and tokens[i].kind == "comment":
                        i += 1
                    if i < n and tokens[i].kind in {"ident", "kw"}:
                        parts.append(tokens[i].text)
                        i += 1
                        continue
                break
            out.append(".".join(parts))
            continue
        i += 1
    return i


def _skip_statement(tokens: list[Token], i: int) -> int:
    depth = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok.kind == "op" and tok.text in "([{":
            depth += 1
        elif tok.kind == "op" and tok.text in ")]}":
            depth = max(0, depth - 1)
        elif tok.kind == "nl" and depth == 0:
            return i + 1
        i += 1
    return i


def _statement_string(tokens: list[Token], i: int) -> tuple[str | None, int]:
    """Last string literal before the statement ends. Used by JS module specifiers."""
    depth = 0
    found: str | None = None
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok.kind == "op" and tok.text in "([{":
            depth += 1
        elif tok.kind == "op" and tok.text in ")]}":
            depth = max(0, depth - 1)
        elif tok.kind == "str":
            found = _unquote(tok.text)
        elif (tok.kind == "nl" and depth == 0) or tok.text == ";":
            return found, i + 1
        i += 1
    return found, i


def _unquote(text: str) -> str:
    # Strip one layer of quotes. Prefixes (f, r, b) are not expected on JS/Go strings.
    if len(text) >= 2 and text[0] in "\"'`" and text[-1] == text[0]:
        return text[1:-1]
    return text


def _js_imports(tokens: list[Token]) -> list[str]:
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok.kind == "kw" and tok.text in {"import", "export"}:
            spec, i = _statement_string(tokens, i + 1)
            if spec:
                out.append(spec)
            continue
        if tok.kind == "ident" and tok.text in {"require", "import"}:
            nxt = _skip_noise(tokens, i + 1)
            if nxt < n and tokens[nxt].text == "(":
                # require("x") / import("x")
                k = _skip_noise(tokens, nxt + 1)
                if k < n and tokens[k].kind == "str":
                    out.append(_unquote(tokens[k].text))
                    i = k + 1
                    continue
        i += 1
    return out


def _go_imports(tokens: list[Token]) -> list[str]:
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        tok = tokens[i]
        if tok.kind == "kw" and tok.text == "import":
            i = _skip_noise(tokens, i + 1)
            if i < n and tokens[i].kind == "str":
                out.append(_unquote(tokens[i].text))
                i += 1
                continue
            if i < n and tokens[i].text == "(":
                i += 1
                while i < n and tokens[i].text != ")":
                    if tokens[i].kind == "str":
                        out.append(_unquote(tokens[i].text))
                    i += 1
        i += 1
    return out


def _rust_imports(tokens: list[Token]) -> list[str]:
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        if tokens[i].kind == "kw" and tokens[i].text == "use":
            i += 1
            parts: list[str] = []
            while i < n and tokens[i].text not in {";", "{"}:
                tok = tokens[i]
                if tok.kind in {"ident", "kw"}:
                    parts.append(tok.text)
                i += 1
            if parts:
                out.append("::".join(parts))
            continue
        i += 1
    return out


def _java_imports(tokens: list[Token]) -> list[str]:
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        if tokens[i].kind == "kw" and tokens[i].text == "import":
            i += 1
            i = _skip_noise(tokens, i)
            if i < n and tokens[i].kind == "kw" and tokens[i].text == "static":
                i += 1
            parts: list[str] = []
            while i < n and tokens[i].text not in {";", "nl"} and tokens[i].kind != "nl":
                tok = tokens[i]
                if tok.kind in {"ident", "kw"} or tok.text == "*":
                    parts.append(tok.text)
                i += 1
            if parts:
                out.append(".".join(parts))
            continue
        i += 1
    return out


@dataclass(frozen=True)
class GraphResult:
    edges: tuple[Edge, ...]
    cycles: tuple[tuple[str, ...], ...]
    pagerank: tuple[tuple[str, float], ...]
    coupling: tuple[Coupling, ...]


def build_graph(files: list[tuple[str, str, tuple[str, ...]]]) -> GraphResult:
    """``files`` is (path, language, imports)."""
    paths = [path for path, _lang, _imports in files]
    path_set = set(paths)
    py_paths = [path for path, lang, _imports in files if lang == "python"]
    index = _py_index(py_paths)
    edges: list[Edge] = []
    seen: set[tuple[str, str, str]] = set()

    def add(src: str, dst: str, kind: str) -> None:
        if src == dst:
            return
        key = (src, dst, kind)
        if key in seen:
            return
        seen.add(key)
        edges.append(Edge(src, dst, kind))

    for path, lang, imports in files:
        for spec in imports:
            target = _resolve(path, lang, spec, path_set, index)
            if target is not None:
                add(path, target, "internal")
            elif not spec.startswith(".") and not spec.startswith("crate::") and not spec.startswith("super::") and not spec.startswith("self::"):
                add(path, spec, "external")

    internal = [(e.src, e.dst) for e in edges if e.kind == "internal"]
    nodes = sorted(path_set)
    cycles = tuple(tuple(comp) for comp in tarjan(nodes, internal))
    rank = pagerank(nodes, internal)
    ranked = tuple(sorted(rank.items(), key=lambda item: (-item[1], item[0])))
    coupling = tuple(_coupling(nodes, internal))
    ordered = tuple(sorted(edges, key=lambda e: (e.kind, e.src, e.dst)))
    return GraphResult(ordered, cycles, ranked, coupling)


def _py_index(paths: list[str]) -> dict[str, str]:
    buckets: dict[str, list[str]] = {}
    for path in paths:
        if not path.endswith(".py"):
            continue
        rel = path[:-3]
        if rel.endswith("/__init__"):
            rel = rel[: -len("/__init__")]
        if not rel or rel.endswith("__init__"):
            continue
        parts = rel.split("/")
        for i in range(len(parts)):
            key = ".".join(parts[i:])
            buckets.setdefault(key, []).append(path)
    return {key: vals[0] for key, vals in buckets.items() if len(set(vals)) == 1}


def _package_name(path: str) -> str:
    rel = path[:-3] if path.endswith(".py") else path
    if rel.endswith("/__init__"):
        rel = rel[: -len("/__init__")]
    else:
        rel = posixpath.dirname(rel)
    return rel.replace("/", ".")


def _resolve_py(spec: str, current: str, index: dict[str, str]) -> str | None:
    if spec.startswith("."):
        level = len(spec) - len(spec.lstrip("."))
        rest = spec[level:]
        package = [part for part in _package_name(current).split(".") if part]
        drop = level - 1
        if drop > len(package):
            return None
        base = package[: len(package) - drop] if drop else package
        if rest:
            base.extend(rest.split("."))
        spec = ".".join(base)
    if spec in index:
        return index[spec]
    matches = [path for key, path in index.items() if key == spec or key.endswith("." + spec)]
    unique = sorted(set(matches))
    if len(unique) == 1:
        return unique[0]
    return None


def _resolve_relative_js(spec: str, current: str, path_set: set[str]) -> str | None:
    if not spec.startswith("."):
        return None
    base = posixpath.normpath(posixpath.join(posixpath.dirname(current), spec))
    exts = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
    candidates = [base]
    for ext in exts:
        candidates.append(base + ext)
        candidates.append(posixpath.join(base, "index" + ext))
    for cand in candidates:
        if cand in path_set:
            return cand
    return None


def _resolve_go(spec: str, path_set: set[str]) -> str | None:
    head = spec.split("/", 1)[0]
    if "." not in head and "/" not in spec:
        return None
    parts = spec.split("/")
    for n in range(len(parts), 0, -1):
        suffix = "/".join(parts[-n:])
        hits = [
            path
            for path in path_set
            if path.endswith(".go")
            and (
                posixpath.dirname(path) == suffix
                or posixpath.dirname(path).endswith("/" + suffix)
            )
        ]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return sorted(hits)[0]
    return None


def _resolve_rust(spec: str, current: str, path_set: set[str]) -> str | None:
    parts = [part for part in spec.split("::") if part and part != "self"]
    if not parts:
        return None
    if parts[0] == "crate":
        base = "src"
        rest = parts[1:]
    elif parts[0] == "super":
        base = posixpath.dirname(current)
        rest = parts[1:]
        while rest and rest[0] == "super":
            base = posixpath.dirname(base)
            rest = rest[1:]
    else:
        return None
    for n in range(len(rest), 0, -1):
        rel = posixpath.join(base, *rest[:n])
        for cand in (rel + ".rs", posixpath.join(rel, "mod.rs")):
            if cand in path_set:
                return cand
    return None


def _resolve_java(spec: str, path_set: set[str]) -> str | None:
    if spec.endswith(".*"):
        spec = spec[:-2]
    suffix = spec.replace(".", "/") + ".java"
    kt = spec.replace(".", "/") + ".kt"
    hits = [path for path in path_set if path.endswith(suffix) or path.endswith(kt) or path == suffix or path == kt]
    if len(hits) == 1:
        return hits[0]
    return None


def _resolve(
    path: str,
    lang: str,
    spec: str,
    path_set: set[str],
    py_index: dict[str, str],
) -> str | None:
    if lang == "python":
        return _resolve_py(spec, path, py_index)
    if lang in {"javascript", "typescript"}:
        return _resolve_relative_js(spec, path, path_set)
    if lang == "go":
        return _resolve_go(spec, path_set)
    if lang == "rust":
        return _resolve_rust(spec, path, path_set)
    if lang in {"java", "kotlin"}:
        return _resolve_java(spec, path_set)
    return None


def tarjan(nodes: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Strongly connected components that contain a cycle.

    A component of size one is kept only when the node has a self-loop.
    Components are emitted in deterministic order.
    """
    graph: dict[str, list[str]] = {node: [] for node in nodes}
    for src, dst in edges:
        if src in graph and dst in graph:
            graph[src].append(dst)
    index = 0
    stack: list[str] = []
    onstack: set[str] = set()
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strong(node: str) -> None:
        nonlocal index
        indices[node] = index
        low[node] = index
        index += 1
        stack.append(node)
        onstack.add(node)
        for nxt in graph[node]:
            if nxt not in indices:
                strong(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in onstack:
                low[node] = min(low[node], indices[nxt])
        if low[node] == indices[node]:
            comp: list[str] = []
            while True:
                got = stack.pop()
                onstack.remove(got)
                comp.append(got)
                if got == node:
                    break
            comp.sort()
            if len(comp) > 1 or node in graph[node]:
                sccs.append(comp)

    for node in nodes:
        if node not in indices:
            strong(node)
    sccs.sort(key=lambda comp: comp[0] if comp else "")
    return sccs


def pagerank(
    nodes: list[str],
    edges: list[tuple[str, str]],
    damping: float = 0.85,
    tol: float = 1e-12,
    iters: int = 100,
) -> dict[str, float]:
    """PageRank. Edge A → B distributes A's rank to B (B is depended on)."""
    uniq = sorted(set(nodes))
    if not uniq:
        return {}
    out: dict[str, list[str]] = {node: [] for node in uniq}
    node_set = set(uniq)
    for src, dst in edges:
        if src in node_set and dst in node_set and src != dst:
            out[src].append(dst)
    count = len(uniq)
    rank = {node: 1.0 / count for node in uniq}
    dangling = [node for node in uniq if not out[node]]
    for _ in range(iters):
        leak = sum(rank[node] for node in dangling)
        base = (1 - damping) / count + damping * leak / count
        new = {node: base for node in uniq}
        for src, dests in out.items():
            if not dests:
                continue
            share = damping * rank[src] / len(dests)
            for dst in dests:
                new[dst] += share
        err = sum(abs(new[node] - rank[node]) for node in uniq)
        rank = new
        if err < tol:
            break
    return rank


def _coupling(nodes: list[str], edges: list[tuple[str, str]]) -> list[Coupling]:
    ca = {node: 0 for node in nodes}
    ce = {node: 0 for node in nodes}
    seen: set[tuple[str, str]] = set()
    for src, dst in edges:
        if src == dst or (src, dst) in seen:
            continue
        if src not in ce or dst not in ca:
            continue
        seen.add((src, dst))
        ce[src] += 1
        ca[dst] += 1
    rows: list[Coupling] = []
    for node in nodes:
        total = ca[node] + ce[node]
        inst = (ce[node] / total) if total else 0.0
        rows.append(Coupling(node, ca[node], ce[node], inst))
    rows.sort(key=lambda row: row.path)
    return rows
