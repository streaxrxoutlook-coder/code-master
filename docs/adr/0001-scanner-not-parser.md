# ADR 0001 — A scanner, not a parser

## Status

Accepted.

## Context

Complexity, clones, and imports need to know what is a comment, a string, or a keyword. They do not need types, overload resolution, or a faithful AST for six languages.

## Decision

Ship one hand-written scanner parameterized by comment syntax, string syntax, and keyword sets. Python is handled with the real lexical rules that affect metrics: prefixes, triple quotes, f-string interpolation, and parentheses suppressing indentation. Brace languages get a preamble check that rejects `if`, `for`, `while`, `catch`, and the rest of the control-statement list before it will call a `{` a function.

Known under-counts and over-counts are listed in `docs/ALGORITHMS.md` and repeated by `brief`. They are part of the contract.

## Consequences

The tool has no native dependency and runs from a checkout. It will mis-count some constructs a real parser would get right. That is preferable to a parser we cannot audit, or to a number we cannot define.
