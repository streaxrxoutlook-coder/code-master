"""One pipeline. Discover files, measure them, then graph, clones, risk, budget."""

from __future__ import annotations

import os
from pathlib import Path

from code_master.budget import DEFAULT_WINDOW, estimate_tokens, score_risk, select_reading
from code_master.clones import DEFAULT_K, DEFAULT_MIN_TOKENS, DEFAULT_W, find_clones, normalize
from code_master.graph import build_graph, extract_imports
from code_master.model import SCHEMA, FileView, Report
from code_master.scan import is_doc, language_for, measure, tokenize
from code_master.version import __version__

MAX_BYTES = 400_000
MAX_FILES = 5_000
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        "target",
        ".next",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "coverage",
        "htmlcov",
        "vendor",
        "site-packages",
    }
)
SKIP_FILES = frozenset(
    {
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "poetry.lock",
        "cargo.lock",
    }
)


def analyze(
    path: Path | str,
    *,
    window: int = DEFAULT_WINDOW,
    min_clone: int = DEFAULT_MIN_TOKENS,
    k: int = DEFAULT_K,
    w: int = DEFAULT_W,
) -> Report:
    root = Path(path).resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    single = root.is_file()
    base = root.parent if single else root
    discovered, skipped = _discover(root, single)
    files: list[FileView] = []
    norms: list[tuple[str, list[tuple[str, int]]]] = []
    graph_input: list[tuple[str, str, tuple[str, ...]]] = []

    for file_path, rel in discovered:
        try:
            raw = file_path.read_bytes()
        except OSError as exc:
            skipped.append((rel, str(exc)))
            continue
        if b"\0" in raw[:1024]:
            skipped.append((rel, "binary"))
            continue
        if len(raw) > MAX_BYTES:
            skipped.append((rel, "too large"))
            continue
        text = raw.decode("utf-8-sig", errors="replace")
        lang = language_for(rel)
        if lang is None or is_doc(lang):
            files.append(_doc(rel, lang.name if lang else "text", raw, text))
            continue
        tokens = tokenize(text, lang)
        measured = measure(text, lang, tokens)
        imports = extract_imports(tokens, lang)
        files.append(
            FileView(
                path=rel,
                language=lang.name,
                kind="code",
                bytes=len(raw),
                lines=measured.lines,
                sloc=measured.sloc,
                comment_lines=measured.comment_lines,
                blank_lines=measured.blank_lines,
                cyclomatic=measured.cyclomatic,
                max_nesting=measured.max_nesting,
                maintainability=measured.maintainability,
                halstead_volume=measured.halstead_volume,
                halstead_difficulty=measured.halstead_difficulty,
                tokens_est=estimate_tokens(text),
                functions=measured.functions,
                imports=imports,
            )
        )
        norms.append((rel, normalize(tokens)))
        graph_input.append((rel, lang.name, imports))

    files.sort(key=lambda item: item.path)
    graph = build_graph(graph_input)
    clones = find_clones(norms, k=k, w=w, min_tokens=min_clone)
    rank = dict(graph.pagerank)
    risk = score_risk(files, clones)
    reading = select_reading(files, dict(risk), rank, window)
    return Report(
        schema=SCHEMA,
        version=__version__,
        root=root.as_posix(),
        window=window,
        tokens_est=sum(item.tokens_est for item in files),
        files=tuple(files),
        edges=graph.edges,
        cycles=graph.cycles,
        pagerank=graph.pagerank,
        coupling=graph.coupling,
        clones=clones,
        risk=risk,
        reading=reading,
        skipped=tuple(sorted(skipped)),
    )


def _doc(rel: str, language: str, raw: bytes, text: str) -> FileView:
    lines = text.splitlines()
    blanks = sum(1 for line in lines if not line.strip())
    return FileView(
        path=rel,
        language=language,
        kind="doc",
        bytes=len(raw),
        lines=len(lines),
        sloc=len(lines) - blanks,
        comment_lines=0,
        blank_lines=blanks,
        cyclomatic=0,
        max_nesting=0,
        maintainability=None,
        halstead_volume=0.0,
        halstead_difficulty=0.0,
        tokens_est=estimate_tokens(text),
        functions=(),
        imports=(),
    )


def _discover(root: Path, single: bool) -> tuple[list[tuple[Path, str]], list[tuple[str, str]]]:
    if single:
        rel = root.name
        return [(root, rel)], []
    found: list[tuple[Path, str]] = []
    skipped: list[tuple[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info") and not d.startswith(".")
        )
        for name in sorted(filenames):
            if name.startswith(".") or name.lower() in SKIP_FILES:
                continue
            file_path = Path(dirpath) / name
            rel = file_path.relative_to(root).as_posix()
            if language_for(rel) is None:
                continue
            if len(found) >= MAX_FILES:
                skipped.append((rel, "file cap"))
                continue
            found.append((file_path, rel))
    return found, skipped
