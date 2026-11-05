"""Type-2 clone detection by winnowing.

Identifiers and literals are normalized away, keywords and operators stay.
Fingerprints follow Schleimer, Wilkerson, and Aiken, SIGMOD 2003: in every
window of ``w`` k-gram hashes, keep the minimum, breaking ties toward the
rightmost position. A shared fingerprint is then expanded to the full run of
equal k-grams so the reported span is the clone, not the fingerprint.

Hashes that occur more than ``MAX_POSTINGS`` times are dropped. They are
the fingerprint equivalent of stop-words.
"""

from __future__ import annotations

from collections import defaultdict, deque

from code_master.model import Clone
from code_master.scan import Token

MASK = (1 << 64) - 1
BASE = 911382323
MAX_POSTINGS = 40
DEFAULT_K = 6
DEFAULT_W = 8
DEFAULT_MIN_TOKENS = 24
# A run must contain real control flow. Keyword tables and repeated
# punctuation normalize into long "clones" that are not copied logic.
_FLOW = frozenset(
    {
        "def",
        "if",
        "elif",
        "elsif",
        "elseif",
        "for",
        "while",
        "return",
        "class",
        "fn",
        "func",
        "function",
        "switch",
        "case",
        "foreach",
        "guard",
        "loop",
        "match",
    }
)


def normalize(tokens: list[Token]) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for tok in tokens:
        if tok.kind in {"nl", "comment"}:
            continue
        if tok.kind == "ident":
            text = "ID"
        elif tok.kind in {"num", "str"}:
            text = "LIT"
        else:
            text = tok.text
        out.append((text, tok.line))
    return out


def token_hash(text: str) -> int:
    """FNV-1a, 64 bit. Stable across processes and platforms."""
    value = 14695981039346656037
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * 1099511628211) & MASK
    return value


def kgram_hashes(texts: list[str], k: int) -> list[int]:
    """Rolling polynomial hash modulo 2^64.

    ``(h - out·BASE^(k-1)) · BASE + inn`` keeps the same value as hashing
    the window from scratch. ``BASE`` is odd, so it is invertible mod 2^64.
    """
    if k <= 0 or len(texts) < k:
        return []
    hashed = [token_hash(text) for text in texts]
    power = pow(BASE, k - 1, MASK + 1)
    value = 0
    for i in range(k):
        value = (value * BASE + hashed[i]) & MASK
    out = [value]
    for i in range(k, len(hashed)):
        value = (value - (hashed[i - k] * power)) & MASK
        value = (value * BASE + hashed[i]) & MASK
        out.append(value)
    return out


def winnow(hashes: list[int], w: int) -> list[tuple[int, int]]:
    """Return ``(gram_index, hash)`` fingerprints. Rightmost minimum wins ties."""
    if not hashes:
        return []
    if w <= 1:
        return list(enumerate(hashes))
    width = min(w, len(hashes))
    dq: deque[int] = deque()
    out: list[tuple[int, int]] = []
    last = -1
    for i, digest in enumerate(hashes):
        while dq and dq[0] <= i - width:
            dq.popleft()
        while dq and hashes[dq[-1]] >= digest:
            dq.pop()
        dq.append(i)
        if i >= width - 1:
            idx = dq[0]
            if idx != last:
                out.append((idx, hashes[idx]))
                last = idx
    return out


def _expand(
    a_hashes: list[int],
    b_hashes: list[int],
    i: int,
    j: int,
    k: int,
    same: bool,
) -> tuple[int, int, int] | None:
    while i > 0 and j > 0 and a_hashes[i - 1] == b_hashes[j - 1]:
        if same and (i - 1) < (j - 1) + k and (j - 1) < (i - 1) + k:
            break
        i -= 1
        j -= 1
    end_i, end_j = i, j
    limit_a = len(a_hashes)
    limit_b = len(b_hashes)
    while end_i + 1 < limit_a and end_j + 1 < limit_b and a_hashes[end_i + 1] == b_hashes[end_j + 1]:
        if same:
            nxt_i = end_i + 1
            nxt_j = end_j + 1
            # Spans are in token space: a gram at g covers tokens g .. g+k-1,
            # and the run covers start .. end_gram+k.
            length = (nxt_i - i) + k
            a0, a1 = i, i + length
            b0, b1 = j, j + length
            if a0 < b1 and b0 < a1:
                break
        end_i += 1
        end_j += 1
    length = (end_i - i) + k
    if same:
        a0, a1 = i, i + length
        b0, b1 = j, j + length
        if a0 < b1 and b0 < a1:
            return None
    return i, j, length


def find_clones(
    files: list[tuple[str, list[tuple[str, int]]]],
    *,
    k: int = DEFAULT_K,
    w: int = DEFAULT_W,
    min_tokens: int = DEFAULT_MIN_TOKENS,
) -> tuple[Clone, ...]:
    prepared: list[tuple[str, list[tuple[str, int]], list[int], list[tuple[int, int]]]] = []
    for path, norms in files:
        texts = [text for text, _line in norms]
        hashes = kgram_hashes(texts, k)
        prepared.append((path, norms, hashes, winnow(hashes, w)))

    postings: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for file_index, (_path, _norms, _hashes, prints) in enumerate(prepared):
        for gram, digest in prints:
            postings[digest].append((file_index, gram))

    seen: set[tuple[int, int, int, int]] = set()
    found: list[tuple[Clone, str, int, str, int]] = []
    for digest, hits in postings.items():
        if len(hits) > MAX_POSTINGS:
            continue
        for a in range(len(hits)):
            ai, ag = hits[a]
            for b in range(a, len(hits)):
                bi, bg = hits[b]
                if ai == bi and bg < ag:
                    continue
                if ai == bi and ag == bg:
                    continue
                if ai == bi and abs(ag - bg) < k:
                    continue
                if (ai, ag) <= (bi, bg):
                    li, lg, ri, rg = ai, ag, bi, bg
                else:
                    li, lg, ri, rg = bi, bg, ai, ag
                expanded = _expand(
                    prepared[li][2],
                    prepared[ri][2],
                    lg,
                    rg,
                    k,
                    same=li == ri,
                )
                if expanded is None:
                    continue
                start_l, start_r, length = expanded
                if length < min_tokens:
                    continue
                dedup = (li, ri, start_l, start_r)
                if dedup in seen:
                    continue
                seen.add(dedup)
                norms_l = prepared[li][1]
                norms_r = prepared[ri][1]
                if not _looks_like_logic(norms_l, start_l, length):
                    continue
                path_l = prepared[li][0]
                path_r = prepared[ri][0]
                sample_n = min(length, 14)
                sample = " ".join(text for text, _line in norms_l[start_l : start_l + sample_n])
                if length > sample_n:
                    sample += " …"
                found.append(
                    (
                        Clone(
                            left=path_l,
                            right=path_r,
                            left_line=norms_l[start_l][1],
                            right_line=norms_r[start_r][1],
                            tokens=length,
                            sample=sample,
                        ),
                        path_l,
                        start_l,
                        path_r,
                        start_r,
                    )
                )
    found.sort(key=lambda item: (-item[0].tokens, item[0].left, item[0].right, item[0].left_line))
    kept: list[Clone] = []
    spans: list[tuple[str, int, int]] = []
    for clone, path_l, start_l, path_r, start_r in found:
        if _overlaps_kept(spans, path_l, start_l, clone.tokens) or _overlaps_kept(
            spans, path_r, start_r, clone.tokens
        ):
            continue
        spans.append((path_l, start_l, start_l + clone.tokens))
        if path_l != path_r:
            spans.append((path_r, start_r, start_r + clone.tokens))
        kept.append(clone)
    return tuple(kept)


def _looks_like_logic(norms: list[tuple[str, int]], start: int, length: int) -> bool:
    hits = 0
    for text, _line in norms[start : start + length]:
        if text in _FLOW:
            hits += 1
            if hits >= 2:
                return True
    return False


def _overlaps_kept(spans: list[tuple[str, int, int]], path: str, start: int, length: int) -> bool:
    end = start + length
    for kept_path, kept_start, kept_end in spans:
        if kept_path != path:
            continue
        inter = max(0, min(end, kept_end) - max(start, kept_start))
        if inter >= 0.6 * min(length, kept_end - kept_start):
            return True
    return False
