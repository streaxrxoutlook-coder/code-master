"""Three faces of one report: a terminal, a brief, and JSON."""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict

from code_master.model import BRIEF_SCHEMA, Report


def render_json(report: Report) -> str:
    return json.dumps(asdict(report), indent=2, ensure_ascii=False) + "\n"


def render_scan(report: Report, *, top: int, color: bool) -> str:
    lines = [_header(report), ""]
    code = [f for f in report.files if f.kind == "code"]
    risk = dict(report.risk)
    mark_at = _p90([score for _path, score in report.risk])
    lines.append("hotspots")
    if not code:
        lines.append("  (no code files)")
    else:
        ranked = sorted(code, key=lambda f: (-risk.get(f.path, 0.0), f.path))
        for f in ranked[:top]:
            score = risk.get(f.path, 0.0)
            mark = "!" if score > 0 and score >= mark_at else " "
            mi = f"{f.maintainability:5.1f}" if f.maintainability is not None else "    -"
            row = f"  {mark} {score:6.2f}  cc {f.cyclomatic:<4} nest {f.max_nesting:<3} mi {mi}  {f.path}"
            if mark == "!":
                row = _paint(color, "33", row)
            lines.append(row)
    functions = [
        (fn.cyclomatic, fn.nesting, f.path, fn.line, fn.name, fn.kind)
        for f in code
        for fn in f.functions
    ]
    functions.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    if functions:
        lines.append("")
        lines.append("functions")
        for cc, nest, path, line, name, kind in functions[:top]:
            lines.append(f"  cc {cc:<4} nest {nest:<3} {path}:{line}  {kind} {name}")
    lines.append("")
    lines.append(
        f"cycles {len(report.cycles)}   "
        f"clone runs {len(report.clones)}   "
        f"tokens ~{report.tokens_est:,}"
    )
    if report.skipped:
        lines.append(f"skipped {len(report.skipped)}")
    lines.append("")
    return "\n".join(lines)


def render_graph(report: Report, *, top: int, color: bool) -> str:
    del color
    lines = [_header(report), ""]
    internal = [e for e in report.edges if e.kind == "internal"]
    external = [e for e in report.edges if e.kind == "external"]
    lines.append(f"internal edges {len(internal)}   external edges {len(external)}")
    lines.append("")
    lines.append("cycles")
    if not report.cycles:
        lines.append("  none")
    else:
        for comp in report.cycles[:top]:
            lines.append("  " + " → ".join(comp) + " → " + comp[0])
    lines.append("")
    lines.append("hubs")
    if not report.pagerank:
        lines.append("  none")
    else:
        for path, score in report.pagerank[:top]:
            lines.append(f"  {score:.4f}  {path}")
    lines.append("")
    lines.append("instability  I = Ce / (Ca + Ce), internal edges only")
    coupled = sorted(report.coupling, key=lambda row: (-row.instability, -row.ce, row.path))
    shown = [row for row in coupled if row.ca or row.ce]
    if not shown:
        lines.append("  none")
    else:
        for row in shown[:top]:
            lines.append(
                f"  I {row.instability:.2f}  Ca {row.ca:<3} Ce {row.ce:<3} {row.path}"
            )
    lines.append("")
    return "\n".join(lines)


def render_clones(report: Report, *, top: int, color: bool) -> str:
    del color
    lines = [_header(report), ""]
    if not report.clones:
        lines.append("no clone runs at this threshold")
        lines.append("")
        return "\n".join(lines)
    lines.append(f"{len(report.clones)} runs")
    lines.append("")
    for clone in report.clones[:top]:
        lines.append(
            f"  {clone.tokens:4} tokens  {clone.left}:{clone.left_line}  ~  {clone.right}:{clone.right_line}"
        )
        lines.append(f"           {clone.sample}")
    lines.append("")
    return "\n".join(lines)


def render_budget(report: Report, *, top: int, color: bool) -> str:
    del color
    lines = [_header(report), ""]
    lines.append(f"window {report.window:,}   corpus ~{report.tokens_est:,}")
    for window in (8_000, 32_000, 128_000, 200_000):
        fits = "fits" if report.tokens_est <= window else "exceeds"
        lines.append(f"  {window // 1000:>4}k  {fits}")
    lines.append("")
    lines.append("read first")
    if not report.reading:
        lines.append("  (empty)")
    else:
        for item in report.reading[:top]:
            lines.append(f"  {item.tokens:6}  {item.why:<16} {item.path}")
        rest = len(report.reading) - top
        if rest > 0:
            lines.append(f"  … {rest} more inside the window")
    lines.append("")
    return "\n".join(lines)


def render_brief(report: Report, *, top: int, color: bool) -> str:
    del color
    code = [f for f in report.files if f.kind == "code"]
    sloc = sum(f.sloc for f in code)
    langs = ", ".join(sorted({f.language for f in code})) or "none"
    mis = [f.maintainability for f in code if f.maintainability is not None]
    parts = [
        f"schema: {BRIEF_SCHEMA}",
        f"version: {report.version}",
        f"root: {report.root}",
        f"code_files: {len(code)}",
        f"sloc: {sloc}",
        f"languages: {langs}",
        f"tokens_est: {report.tokens_est}",
        f"window: {report.window}",
        f"cycles: {len(report.cycles)}",
        f"clone_runs: {len(report.clones)}",
        f"skipped: {len(report.skipped)}",
    ]
    if mis:
        parts.append(f"mi_median: {statistics.median(mis):.2f}")
        parts.append(f"mi_mean: {statistics.fmean(mis):.2f}")
    parts.append("")
    parts.append(
        f"{len(code)} code files, {sloc} SLOC, "
        f"{len(report.cycles)} import cycles, {len(report.clones)} clone runs, "
        f"about {report.tokens_est} tokens "
        f"({'fits' if report.tokens_est <= report.window else 'exceeds'} a {report.window} window)."
    )
    parts.append("")
    parts.append("## hotspots")
    parts.append("")
    if not report.risk:
        parts.append("(none)")
    else:
        risk = dict(report.risk)
        by_path = {f.path: f for f in code}
        for path, score in report.risk[:top]:
            f = by_path.get(path)
            if f is None:
                continue
            mi = f"{f.maintainability:.1f}" if f.maintainability is not None else "-"
            parts.append(
                f"- {score:.2f}  cc {f.cyclomatic}  nest {f.max_nesting}  mi {mi}  {path}"
            )
    parts.append("")
    parts.append("## cycles")
    parts.append("")
    if not report.cycles:
        parts.append("none")
    else:
        for comp in report.cycles:
            parts.append("- " + " → ".join(comp))
    parts.append("")
    parts.append("## clones")
    parts.append("")
    if not report.clones:
        parts.append("none")
    else:
        for clone in report.clones[:top]:
            parts.append(
                f"- {clone.tokens} tokens  {clone.left}:{clone.left_line} ~ {clone.right}:{clone.right_line}"
            )
            parts.append(f"  `{clone.sample}`")
    parts.append("")
    parts.append("## read first")
    parts.append("")
    if not report.reading:
        parts.append("(empty)")
    else:
        for item in report.reading[:top]:
            parts.append(f"- {item.tokens} tokens  {item.why}  {item.path}")
    parts.append("")
    parts.append("## limits")
    parts.append("")
    parts.append(
        "Scanner, not a parser. Cyclomatic counts decision tokens outside strings and comments. "
        "Python `match`/`case` are soft keywords and are not counted. "
        "A Rust or Kotlin `match`/`when` counts as one decision, not one per arm. "
        "Clones are type-2: identifiers and literals are normalized away. "
        "Token counts are an estimate, not a model tokenizer. "
        "Import resolution is syntactic."
    )
    parts.append("")
    return "\n".join(parts) + "\n"


def _header(report: Report) -> str:
    code = [f for f in report.files if f.kind == "code"]
    sloc = sum(f.sloc for f in code)
    langs = ", ".join(sorted({f.language for f in code})) or "none"
    mis = [f.maintainability for f in code if f.maintainability is not None]
    mi = ""
    if mis:
        mi = f"   mi median {statistics.median(mis):.1f}  mean {statistics.fmean(mis):.1f}"
    return f"code-master {report.version}   {len(code)} files   {sloc:,} sloc   {langs}{mi}"


def _p90(scores: list[float]) -> float:
    if not scores:
        return math.inf
    ordered = sorted(scores)
    # Nearest-rank on the high side. One file → that file's score.
    idx = min(len(ordered) - 1, max(0, math.ceil(0.9 * len(ordered)) - 1))
    return ordered[idx]


def _paint(enabled: bool, code: str, text: str) -> str:
    if not enabled:
        return text
    return f"\033[{code}m{text}\033[0m"


RENDER = {
    "scan": render_scan,
    "graph": render_graph,
    "clones": render_clones,
    "budget": render_budget,
    "brief": render_brief,
}
