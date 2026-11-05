"""Command line. ``scan``, ``graph``, ``clones``, ``budget``, and ``brief``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from code_master.analyze import analyze
from code_master.budget import DEFAULT_WINDOW
from code_master.clones import DEFAULT_K, DEFAULT_MIN_TOKENS, DEFAULT_W
from code_master.render import RENDER, render_json
from code_master.version import __version__

_COMMANDS = (
    ("scan", "complexity, maintainability, hotspots"),
    ("graph", "imports, cycles, PageRank, instability"),
    ("clones", "type-2 clone runs (winnowing)"),
    ("budget", "token estimate and a reading order that fits a window"),
    ("brief", "one markdown document for a reviewer or a model"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="code-master",
        description=(
            "Local, deterministic code intelligence. "
            "Metrics, import structure, type-2 clones, and a context budget. "
            "Nothing leaves the machine."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  code-master scan .\n"
            "  code-master graph .\n"
            "  code-master clones .\n"
            "  code-master budget . --window 8000\n"
            "  code-master brief . -o BRIEF.md\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"code-master {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, help_text in _COMMANDS:
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("path")
        cmd.add_argument("--json", action="store_true", help="write the full report as JSON")
        cmd.add_argument("-o", "--out", help="write to a file instead of stdout")
        cmd.add_argument("--top", type=int, default=8, help="rows to show (default 8)")
        cmd.add_argument(
            "--window",
            type=int,
            default=DEFAULT_WINDOW,
            help=f"token window for the reading list (default {DEFAULT_WINDOW})",
        )
        cmd.add_argument(
            "--min-tokens",
            type=int,
            default=DEFAULT_MIN_TOKENS,
            help=f"shortest clone run to report (default {DEFAULT_MIN_TOKENS})",
        )
        cmd.add_argument("--k", type=int, default=DEFAULT_K, help=f"winnowing k-gram width (default {DEFAULT_K})")
        cmd.add_argument("--w", type=int, default=DEFAULT_W, help=f"winnowing window (default {DEFAULT_W})")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = analyze(args.path, window=args.window, min_clone=args.min_tokens, k=args.k, w=args.w)
    except FileNotFoundError as exc:
        print(f"code-master: no such path: {exc}", file=sys.stderr)
        return 2
    color = sys.stdout.isatty() and not args.json and args.out is None and os.environ.get("NO_COLOR") is None
    text = render_json(report) if args.json else RENDER[args.cmd](report, top=args.top, color=color)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0
