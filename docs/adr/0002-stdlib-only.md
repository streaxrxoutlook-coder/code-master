# ADR 0002 — The standard library is the dependency list

## Status

Accepted.

## Context

A code-intelligence tool that pulls a parser generator, a tokenizer vocabulary, and a CLI framework asks its user to trust a supply chain before it has done anything useful. It also makes the result harder to re-run later.

## Decision

Runtime dependencies: none. Python 3.11 or newer. Development uses pytest and mypy, and those are not imported by the tool.

Hashing, graphs, and the terminal rendering are implemented here. The token estimate is a documented character model, not a vendored BPE vocabulary. It is for ranking and for window checks. It is not a billing figure.

## Consequences

There is no `tiktoken` parity and no Tree-sitter grammar coverage. Both can be added later behind the same report schema if a measurement shows the estimate or the scanner is the thing that is wrong. They are not added in advance.
