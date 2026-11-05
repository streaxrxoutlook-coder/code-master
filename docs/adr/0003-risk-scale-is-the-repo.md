# ADR 0003 — Risk is scaled by this repository

## Status

Accepted.

## Context

A weighted "health score" with universal thresholds looks portable and isn't. One generated file sets the mean and the standard deviation, and a stable hub looks risky only because everything imports it.

## Decision

Risk is a weighted sum of median/MAD z-scores computed inside the repository being scanned, plus a 0/1 clone flag. MAD is used instead of the standard deviation because a single huge file should not set the scale. The consistency constant `1 / Φ⁻¹(0.75)` puts the score on a familiar z scale; it is not a claim that the repository is normal.

PageRank is reported separately. It is not added into risk. Centrality and hazard are different questions, and `graph` already answers the first one.

The maintainability index is the median of per-function values. The 1994 formula takes one cyclomatic number; summing a whole module into that slot collapses the index to zero.

`scan` prints the median and the mean of file MI together. In a skewed distribution those two diverge, and showing only one of them is how a report lies.

## Consequences

A risk of `1.2` in one repository is not "worse" than `0.4` in another. The reading order and the hotspot list are about the tree you pointed at.
