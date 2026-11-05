"""Public records. One analysis, three renderings: terminal, brief, JSON."""

from __future__ import annotations

from dataclasses import dataclass

SCHEMA = "code-master.report.v1"
BRIEF_SCHEMA = "code-master.brief.v1"


@dataclass(frozen=True)
class FunctionMetric:
    name: str
    kind: str  # def, class, fn
    line: int
    end_line: int
    cyclomatic: int
    nesting: int
    sloc: int


@dataclass(frozen=True)
class FileView:
    path: str
    language: str
    kind: str  # code | doc
    bytes: int
    lines: int
    sloc: int
    comment_lines: int
    blank_lines: int
    cyclomatic: int
    max_nesting: int
    maintainability: float | None
    halstead_volume: float
    halstead_difficulty: float
    tokens_est: int
    functions: tuple[FunctionMetric, ...]
    imports: tuple[str, ...]


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: str  # internal | external


@dataclass(frozen=True)
class Coupling:
    path: str
    ca: int  # afferent, internal dependents
    ce: int  # efferent, internal dependencies
    instability: float  # Ce / (Ca + Ce); 0 when isolated


@dataclass(frozen=True)
class Clone:
    left: str
    right: str
    left_line: int
    right_line: int
    tokens: int
    sample: str


@dataclass(frozen=True)
class Reading:
    path: str
    tokens: int
    value: float
    why: str


@dataclass(frozen=True)
class Report:
    schema: str
    version: str
    root: str
    window: int
    tokens_est: int
    files: tuple[FileView, ...]
    edges: tuple[Edge, ...]
    cycles: tuple[tuple[str, ...], ...]
    pagerank: tuple[tuple[str, float], ...]
    coupling: tuple[Coupling, ...]
    clones: tuple[Clone, ...]
    risk: tuple[tuple[str, float], ...]
    reading: tuple[Reading, ...]
    skipped: tuple[tuple[str, str], ...]
