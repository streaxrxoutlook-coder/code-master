"""Structural scanner.

A scanner, not a parser. Comments, strings, and identifiers do not leak into
each other, which is the property metrics actually depend on. It does not
build an AST and does not resolve symbols.

Python soft keywords (``match`` / ``case``) are left as identifiers so a
variable named ``case`` is not charged as a branch. That under-counts
structural pattern matching. Brace-language ``match`` counts as one decision,
not one per arm. Both limits are intentional and tested.
"""

from __future__ import annotations

import math
import posixpath
import statistics
from dataclasses import dataclass
from typing import Literal

from code_master.model import FunctionMetric

Kind = Literal["kw", "ident", "num", "str", "op", "nl", "comment", "other"]

_PY_PREFIXES = frozenset({"r", "u", "b", "f", "fr", "rf", "rb", "br"})
_OPEN = "([{"
_CLOSE = ")]}"


@dataclass(frozen=True)
class Token:
    kind: Kind
    text: str
    line: int
    col: int


@dataclass(frozen=True)
class Lang:
    name: str
    family: str  # py, c, go, rust, ruby, sql, doc
    line_comments: tuple[str, ...]
    block_comments: tuple[tuple[str, str], ...]
    keywords: frozenset[str]
    decisions: frozenset[str]
    bool_ops: frozenset[str]
    ternary: bool
    templates: bool


@dataclass(frozen=True)
class Measured:
    lines: int
    sloc: int
    comment_lines: int
    blank_lines: int
    cyclomatic: int
    max_nesting: int
    maintainability: float | None
    halstead_volume: float
    halstead_difficulty: float
    functions: tuple[FunctionMetric, ...]


def _kw(*words: str) -> frozenset[str]:
    out: set[str] = set()
    for group in words:
        out.update(group.split())
    return frozenset(out)


_PY_KW = _kw(
    "False None True and as assert async await break class continue def del",
    "elif else except finally for from global if import in is lambda nonlocal",
    "not or pass raise return try while with yield",
)
_JS_KW = _kw(
    "break case catch class const continue debugger default delete do else",
    "export extends finally for function if import in instanceof new return",
    "super switch this throw try typeof var void while with yield let static",
    "await enum implements interface package private protected public as async",
    "from of type namespace declare readonly abstract module override",
)
_GO_KW = _kw(
    "break case chan const continue default defer else fallthrough for func go",
    "goto if import interface map package range return select struct switch type var",
)
_RUST_KW = _kw(
    "as async await break const continue crate dyn else enum extern false fn for",
    "if impl in let loop match mod move mut pub ref return self Self static struct",
    "super trait true type unsafe use where while",
)
_JAVA_KW = _kw(
    "abstract assert boolean break byte case catch char class const continue default",
    "do double else enum extends final finally float for goto if implements import",
    "instanceof int interface long native new package private protected public return",
    "short static strictfp super switch synchronized this throw throws transient try",
    "void volatile while var record yield sealed permits",
)
_C_KW = _kw(
    "auto break case char const continue default do double else enum extern float",
    "for goto if inline int long register restrict return short signed sizeof static",
    "struct switch typedef union unsigned void volatile while _Bool _Complex _Imaginary",
    "class namespace template typename public private protected virtual override",
    "final try catch throw new delete constexpr noexcept nullptr this operator",
)
_CS_KW = _kw(
    "abstract as base bool break byte case catch char checked class const continue",
    "decimal default delegate do double else enum event explicit extern false finally",
    "fixed float for foreach goto if implicit in int interface internal is lock long",
    "namespace new null object operator out override params private protected public",
    "readonly ref return sbyte sealed short sizeof stackalloc static string struct",
    "switch this throw true try typeof uint ulong unchecked unsafe ushort using",
    "virtual void volatile while var async await record",
)
_SWIFT_KW = _kw(
    "associatedtype break case catch class continue default defer do else enum",
    "extension fallthrough false fileprivate for func guard if import in init",
    "inout internal is let nil open operator private protocol public repeat return",
    "self static struct subscript super switch throw throws true try typealias",
    "var where while",
)
_PHP_KW = _kw(
    "abstract and array as break callable case catch class clone const continue",
    "declare default die do echo else elseif empty enddeclare endfor endforeach",
    "endif endswitch endwhile eval exit extends final finally fn for foreach",
    "function global goto if implements include include_once instanceof insteadof",
    "interface isset list match namespace new or print private protected public",
    "require require_once return static switch throw trait try unset use var",
    "while xor yield from",
)
_RUBY_KW = _kw(
    "alias and begin break case class def defined? do else elsif end ensure false",
    "for if in module next nil not or redo rescue retry return self super then true",
    "undef unless until when while yield",
)
_SQL_KW = _kw(
    "select from where and or not in is null as join left right inner outer on",
    "group by order having limit offset insert into values update set delete",
    "create table view index drop alter union all distinct case when then else end",
    "with recursive exists between like",
)

_CONTROL = frozenset(
    """
    if elif else elseif elsif for while switch catch except do foreach loop when
    unless until case guard synchronized lock fixed using assert select
    """.split()
)
_BRACE = frozenset({"c", "go", "rust"})

_OPS = tuple(
    sorted(
        {
            ">>>=",
            ">>=",
            "<<=",
            "===",
            "!==",
            ">>>",
            "...",
            "..=",
            "..",
            "**=",
            "//=",
            "&&=",
            "||=",
            "??=",
            "=>",
            "??",
            "?.",
            "&&",
            "||",
            "==",
            "!=",
            "<=",
            ">=",
            "++",
            "--",
            "+=",
            "-=",
            "*=",
            "/=",
            "%=",
            "&=",
            "|=",
            "^=",
            "<<",
            ">>",
            "**",
            "//",
            "::",
            "->",
            "<-",
            ":=",
            "|>",
            "=~",
            "!~",
        },
        key=len,
        reverse=True,
    )
)


def _lang(
    name: str,
    family: str,
    line: tuple[str, ...],
    block: tuple[tuple[str, str], ...],
    keywords: frozenset[str],
    decisions: frozenset[str],
    bool_ops: frozenset[str],
    ternary: bool,
    templates: bool = False,
) -> Lang:
    return Lang(name, family, line, block, keywords, decisions, bool_ops, ternary, templates)


_LANGS: dict[str, Lang] = {
    "python": _lang(
        "python", "py", ("#",), (), _PY_KW,
        frozenset({"if", "elif", "for", "while", "except", "and", "or"}),
        frozenset(), False,
    ),
    "javascript": _lang(
        "javascript", "c", ("//",), (("/*", "*/"),), _JS_KW,
        frozenset({"if", "for", "while", "case", "catch"}),
        frozenset({"&&", "||"}), True, True,
    ),
    "typescript": _lang(
        "typescript", "c", ("//",), (("/*", "*/"),), _JS_KW,
        frozenset({"if", "for", "while", "case", "catch"}),
        frozenset({"&&", "||"}), True, True,
    ),
    "go": _lang(
        "go", "go", ("//",), (("/*", "*/"),), _GO_KW,
        frozenset({"if", "for", "case"}),
        frozenset({"&&", "||"}), False,
    ),
    "rust": _lang(
        "rust", "rust", ("//",), (("/*", "*/"),), _RUST_KW,
        frozenset({"if", "for", "while", "loop", "match"}),
        frozenset({"&&", "||"}), False,
    ),
    "java": _lang(
        "java", "c", ("//",), (("/*", "*/"),), _JAVA_KW,
        frozenset({"if", "for", "while", "case", "catch"}),
        frozenset({"&&", "||"}), True,
    ),
    "kotlin": _lang(
        "kotlin", "c", ("//",), (("/*", "*/"),), _JAVA_KW | frozenset({"fun", "when", "object", "typealias", "val", "var", "suspend"}),
        frozenset({"if", "for", "while", "when", "catch"}),
        frozenset({"&&", "||"}), True,
    ),
    "c": _lang(
        "c", "c", ("//",), (("/*", "*/"),), _C_KW,
        frozenset({"if", "for", "while", "case", "catch"}),
        frozenset({"&&", "||"}), True,
    ),
    "cpp": _lang(
        "cpp", "c", ("//",), (("/*", "*/"),), _C_KW,
        frozenset({"if", "for", "while", "case", "catch"}),
        frozenset({"&&", "||"}), True,
    ),
    "csharp": _lang(
        "csharp", "c", ("//",), (("/*", "*/"),), _CS_KW,
        frozenset({"if", "for", "while", "case", "catch", "foreach"}),
        frozenset({"&&", "||"}), True,
    ),
    "swift": _lang(
        "swift", "c", ("//",), (("/*", "*/"),), _SWIFT_KW,
        frozenset({"if", "for", "while", "case", "catch", "guard"}),
        frozenset({"&&", "||"}), True,
    ),
    "php": _lang(
        "php", "c", ("//", "#"), (("/*", "*/"),), _PHP_KW,
        frozenset({"if", "for", "while", "case", "catch", "elseif", "foreach", "and", "or"}),
        frozenset({"&&", "||"}), True,
    ),
    "ruby": _lang(
        "ruby", "ruby", ("#",), (), _RUBY_KW,
        frozenset({"if", "unless", "while", "until", "for", "rescue", "elsif", "when", "and", "or"}),
        frozenset({"&&", "||"}), True,
    ),
    "sql": _lang(
        "sql", "sql", ("--",), (("/*", "*/"),), _SQL_KW,
        frozenset({"case", "when", "and", "or"}),
        frozenset(), False,
    ),
    "markdown": _lang("markdown", "doc", (), (), frozenset(), frozenset(), frozenset(), False),
    "text": _lang("text", "doc", (), (), frozenset(), frozenset(), frozenset(), False),
}

_EXT: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".php": "php",
    ".rb": "ruby",
    ".sql": "sql",
    ".md": "markdown",
    ".rst": "text",
    ".txt": "text",
    ".toml": "text",
    ".yaml": "text",
    ".yml": "text",
    ".json": "text",
    ".ini": "text",
    ".cfg": "text",
}


def language_for(path: str) -> Lang | None:
    ext = posixpath.splitext(path)[1].lower()
    name = _EXT.get(ext)
    if name is None:
        return None
    return _LANGS[name]


def is_doc(lang: Lang) -> bool:
    return lang.family == "doc"


def is_decision(tok: Token, lang: Lang) -> bool:
    if tok.kind == "kw" and tok.text in lang.decisions:
        return True
    if tok.kind == "op" and tok.text in lang.bool_ops:
        return True
    if tok.kind == "op" and tok.text == "??":
        return True
    if lang.ternary and tok.kind == "op" and tok.text == "?":
        return True
    return False


class Lexer:
    def __init__(self, src: str, lang: Lang) -> None:
        self.s = src
        self.n = len(src)
        self.i = 0
        self.line = 1
        self.col = 1
        self.lang = lang
        self.out: list[Token] = []
        self.delim = 0

    def tokenize(self) -> list[Token]:
        while self.i < self.n:
            self.step()
        return self.out

    def step(self) -> None:
        before = self.i
        if self.i >= self.n:
            return
        ch = self.s[self.i]
        if ch == "\r":
            if self.i + 1 < self.n and self.s[self.i + 1] == "\n":
                self.bump(1)
            else:
                self._emit("nl", "\n")
                self.bump(1)
            return
        if ch == "\n":
            self._emit("nl", "\n")
            self.bump(1)
            return
        if ch in " \t\f\v":
            j = self.i + 1
            while j < self.n and self.s[j] in " \t\f\v":
                j += 1
            self.bump(j - self.i)
            return
        if self._try_string() or self._try_comment() or self._try_number() or self._try_ident():
            return
        if self._try_op():
            return
        self._emit("other", ch)
        self.bump(1)
        if self.i == before:
            self.bump(1)

    def _emit(self, kind: Kind, text: str, line: int | None = None, col: int | None = None) -> None:
        self.out.append(Token(kind, text, self.line if line is None else line, self.col if col is None else col))

    def bump(self, k: int) -> None:
        end = self.i + k
        while self.i < end and self.i < self.n:
            if self.s[self.i] == "\n":
                self.line += 1
                self.col = 1
            else:
                self.col += 1
            self.i += 1

    def _bracket(self, text: str, line: int, col: int) -> None:
        self._emit("op", text, line, col)
        if text in _OPEN:
            self.delim += 1
        elif text in _CLOSE:
            self.delim = max(0, self.delim - 1)

    def _try_string(self) -> bool:
        family = self.lang.family
        if family == "py":
            return self._try_py_string()
        if family == "rust":
            return self._try_rust_string()
        if family == "go" and self.s[self.i] == "`":
            self._read_raw_until("`")
            return True
        if family == "sql" and self.s[self.i] == "'":
            self._read_quoted("'", template=False, sql=True, allow_nl=False)
            return True
        if family in {"c", "go", "rust", "ruby"} and self.s[self.i] in "\"'":
            self._read_quoted(self.s[self.i], template=self.lang.templates and self.s[self.i] == "`", allow_nl=False)
            return True
        return False

    def _try_py_string(self) -> bool:
        j = self.i
        while j < self.n and j - self.i < 3 and self.s[j].isalpha():
            j += 1
        prefix = self.s[self.i:j]
        if prefix and prefix.lower() not in _PY_PREFIXES:
            return False
        if j >= self.n or self.s[j] not in "\"'":
            return False
        self._read_py_string(prefix)
        return True

    def _read_py_string(self, prefix: str) -> None:
        sl, sc = self.line, self.col
        buf: list[str] = []
        if prefix:
            buf.append(prefix)
            self.bump(len(prefix))
        quote = self.s[self.i : self.i + 3]
        if quote not in {'"""', "'''"}:
            quote = self.s[self.i]
        buf.append(quote)
        self.bump(len(quote))
        is_f = "f" in prefix.lower()
        triple = len(quote) == 3
        seg_line, seg_col = sl, sc

        def flush() -> None:
            nonlocal seg_line, seg_col
            if buf:
                self._emit("str", "".join(buf), seg_line, seg_col)
                buf.clear()
            seg_line, seg_col = self.line, self.col

        while self.i < self.n:
            if self.s.startswith("\\", self.i) and self.i + 1 < self.n:
                buf.append(self.s[self.i : self.i + 2])
                self.bump(2)
                continue
            if self.s.startswith(quote, self.i):
                buf.append(quote)
                self.bump(len(quote))
                flush()
                return
            if is_f and self.s.startswith("{{", self.i):
                buf.append("{{")
                self.bump(2)
                continue
            if is_f and self.s.startswith("}}", self.i):
                buf.append("}}")
                self.bump(2)
                continue
            if is_f and self.s[self.i] == "{":
                flush()
                bl, bc = self.line, self.col
                self.bump(1)
                self._bracket("{", bl, bc)
                # Match this interpolation, not a hardcoded depth. The f-string
                # may already sit inside parentheses (`print(f"{x}")`).
                opened = self.delim
                while self.i < self.n and not (self.s[self.i] == "}" and self.delim == opened):
                    self.step()
                if self.i < self.n and self.s[self.i] == "}":
                    bl, bc = self.line, self.col
                    self.bump(1)
                    self._bracket("}", bl, bc)
                seg_line, seg_col = self.line, self.col
                continue
            if self.s[self.i] == "\n" and not triple:
                flush()
                return
            buf.append(self.s[self.i])
            self.bump(1)
        flush()

    def _try_rust_string(self) -> bool:
        s, i, n = self.s, self.i, self.n
        k = i
        if k < n and s[k] in "bB":
            k += 1
        if k < n and s[k] in "rR":
            h = k + 1
            while h < n and s[h] == "#":
                h += 1
            if h < n and s[h] == '"':
                hashes = h - (k + 1)
                end_pat = '"' + ("#" * hashes)
                j = s.find(end_pat, h + 1)
                sl, sc = self.line, self.col
                if j < 0:
                    text = s[i:]
                    self.bump(n - i)
                else:
                    text = s[i : j + len(end_pat)]
                    self.bump(len(text))
                self._emit("str", text, sl, sc)
                return True
        if s[i] in "\"'":
            self._read_quoted(s[i], template=False, allow_nl=False)
            return True
        if s[i] in "bB" and i + 1 < n and s[i + 1] in "\"'":
            # Keep the prefix on the literal so it is not an identifier.
            prefix = s[i]
            sl, sc = self.line, self.col
            self.bump(1)
            self._read_quoted(self.s[self.i], template=False, allow_nl=False, already=(sl, sc, prefix))
            return True
        return False

    def _read_raw_until(self, quote: str) -> None:
        sl, sc = self.line, self.col
        j = self.s.find(quote, self.i + 1)
        if j < 0:
            text = self.s[self.i :]
            self.bump(self.n - self.i)
        else:
            text = self.s[self.i : j + len(quote)]
            self.bump(len(text))
        self._emit("str", text, sl, sc)

    def _read_quoted(
        self,
        quote: str,
        *,
        template: bool,
        sql: bool = False,
        allow_nl: bool,
        already: tuple[int, int, str] | None = None,
    ) -> None:
        if already is None:
            sl, sc = self.line, self.col
            buf = [quote]
            self.bump(1)
        else:
            sl, sc, prefix = already
            buf = [prefix, quote]
            self.bump(1)
        seg_line, seg_col = sl, sc

        def flush() -> None:
            nonlocal seg_line, seg_col
            if buf:
                self._emit("str", "".join(buf), seg_line, seg_col)
                buf.clear()
            seg_line, seg_col = self.line, self.col

        while self.i < self.n:
            if self.s[self.i] == "\\" and self.i + 1 < self.n:
                buf.append(self.s[self.i : self.i + 2])
                self.bump(2)
                continue
            if sql and self.s.startswith("''", self.i):
                buf.append("''")
                self.bump(2)
                continue
            if self.s.startswith(quote, self.i):
                buf.append(quote)
                self.bump(len(quote))
                flush()
                return
            if template and self.s.startswith("${", self.i):
                flush()
                dl, dc = self.line, self.col
                self.bump(1)
                self._emit("op", "$", dl, dc)
                bl, bc = self.line, self.col
                self.bump(1)
                self._bracket("{", bl, bc)
                opened = self.delim
                while self.i < self.n and not (self.s[self.i] == "}" and self.delim == opened):
                    self.step()
                if self.i < self.n and self.s[self.i] == "}":
                    bl, bc = self.line, self.col
                    self.bump(1)
                    self._bracket("}", bl, bc)
                seg_line, seg_col = self.line, self.col
                continue
            if self.s[self.i] == "\n" and not allow_nl:
                flush()
                return
            buf.append(self.s[self.i])
            self.bump(1)
        flush()

    def _try_comment(self) -> bool:
        for start, end in self.lang.block_comments:
            if self.s.startswith(start, self.i):
                sl, sc = self.line, self.col
                j = self.s.find(end, self.i + len(start))
                if j < 0:
                    text = self.s[self.i :]
                    self.bump(self.n - self.i)
                else:
                    text = self.s[self.i : j + len(end)]
                    self.bump(len(text))
                self._emit("comment", text, sl, sc)
                return True
        for start in self.lang.line_comments:
            if self.s.startswith(start, self.i):
                sl, sc = self.line, self.col
                j = self.s.find("\n", self.i)
                if j < 0:
                    j = self.n
                text = self.s[self.i : j]
                self.bump(len(text))
                self._emit("comment", text, sl, sc)
                return True
        return False

    def _try_number(self) -> bool:
        s, i, n = self.s, self.i, self.n
        if not (s[i].isdigit() or (s[i] == "." and i + 1 < n and s[i + 1].isdigit())):
            return False
        sl, sc = self.line, self.col
        j = i
        if s.startswith(("0x", "0X", "0b", "0B", "0o", "0O"), j):
            j += 2
            while j < n and (s[j].isalnum() or s[j] == "_"):
                j += 1
        else:
            while j < n and (s[j].isdigit() or s[j] == "_"):
                j += 1
            if j < n and s[j] == "." and (j + 1 == n or s[j + 1] != "."):
                # A single dot followed by a digit continues a float.
                # `..` is the range operator, not a decimal point.
                if j + 1 < n and s[j + 1].isdigit():
                    j += 1
                    while j < n and (s[j].isdigit() or s[j] == "_"):
                        j += 1
            if j < n and s[j] in "eE":
                k = j + 1
                if k < n and s[k] in "+-":
                    k += 1
                if k < n and s[k].isdigit():
                    j = k + 1
                    while j < n and (s[j].isdigit() or s[j] == "_"):
                        j += 1
        text = s[i:j]
        self.bump(j - i)
        self._emit("num", text, sl, sc)
        return True

    def _try_ident(self) -> bool:
        ch = self.s[self.i]
        if not (ch.isalpha() or ch == "_" or ord(ch) > 127):
            return False
        sl, sc = self.line, self.col
        j = self.i + 1
        while j < self.n:
            c = self.s[j]
            if c.isalnum() or c == "_" or ord(c) > 127:
                j += 1
                continue
            break
        if self.lang.family == "ruby" and j < self.n and self.s[j] in "?!":
            j += 1
        text = self.s[self.i : j]
        self.bump(j - self.i)
        kind: Kind = "kw" if text in self.lang.keywords else "ident"
        self._emit(kind, text, sl, sc)
        return True

    def _try_op(self) -> bool:
        for op in _OPS:
            if self.s.startswith(op, self.i):
                sl, sc = self.line, self.col
                self.bump(len(op))
                if op in _OPEN or op in _CLOSE:
                    self._bracket(op, sl, sc)
                else:
                    self._emit("op", op, sl, sc)
                return True
        ch = self.s[self.i]
        if ch in "()[]{}.,;:+-*/%&|^~!?=<>@#$\\":
            sl, sc = self.line, self.col
            self.bump(1)
            if ch in _OPEN or ch in _CLOSE:
                self._bracket(ch, sl, sc)
            else:
                self._emit("op", ch, sl, sc)
            return True
        return False


def tokenize(text: str, lang: Lang) -> list[Token]:
    return Lexer(text, lang).tokenize()


def _halstead(tokens: list[Token]) -> tuple[float, float]:
    operators: list[str] = []
    operands: list[str] = []
    for tok in tokens:
        if tok.kind in {"nl", "comment"}:
            continue
        if tok.kind in {"ident", "num", "str"}:
            operands.append(tok.text)
        elif tok.kind in {"kw", "op", "other"}:
            operators.append(tok.text)
    n1 = len(set(operators))
    n2 = len(set(operands))
    n = n1 + n2
    length = len(operators) + len(operands)
    if n <= 1 or length == 0 or n2 == 0:
        return 0.0, 0.0
    volume = length * math.log2(n)
    difficulty = (n1 / 2) * (len(operands) / n2)
    return volume, difficulty


def maintainability(volume: float, cyclomatic: int, sloc: int) -> float | None:
    """Visual Studio scaled form of Coleman, Ash, Lowther, Oman 1994.

    MI_raw = 171 - 5.2·ln(V) - 0.23·G - 16.2·ln(SLOC), then × 100/171,
    clamped to 0..100. ``ln`` is the natural log, matching the paper.
    SLOC here is physical source lines, comments and blanks removed.
    """
    if sloc <= 0 or volume <= 0:
        return None
    raw = 171 - 5.2 * math.log(volume) - 0.23 * cyclomatic - 16.2 * math.log(sloc)
    scaled = raw * 100 / 171
    if scaled < 0:
        return 0.0
    if scaled > 100:
        return 100.0
    return scaled


def _line_buckets(text: str, tokens: list[Token]) -> tuple[int, int, int, int, set[int]]:
    """Comment-only lines are comments. A line with code and a trailing comment is code."""
    lines = text.splitlines()
    kinds: dict[int, set[str]] = {}
    for tok in tokens:
        if tok.kind == "nl":
            continue
        kinds.setdefault(tok.line, set()).add(tok.kind)
    blanks = 0
    comments = 0
    sloc = 0
    code_lines: set[int] = set()
    for i, line in enumerate(lines, start=1):
        if not line.strip():
            blanks += 1
            continue
        has_code = bool(kinds.get(i, set()) - {"comment"})
        if has_code:
            sloc += 1
            code_lines.add(i)
        else:
            comments += 1
    return len(lines), sloc, comments, blanks, code_lines


def _indent_width(line: str) -> int:
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n = (n // 8 + 1) * 8
        else:
            break
    return n


def _indent_unit(widths: list[int]) -> int:
    g = 0
    for width in widths:
        if width > 0:
            g = math.gcd(g, width)
    return g or 4


def _py_scope_start(toks: list[Token]) -> tuple[str, str] | None:
    i = 0
    if not toks or toks[0].text == "@":
        return None
    if toks[0].kind == "kw" and toks[0].text == "async":
        i = 1
    if i < len(toks) and toks[i].kind == "kw" and toks[i].text in {"def", "class"}:
        kind = "def" if toks[i].text == "def" else "class"
        name = "<anonymous>"
        if i + 1 < len(toks) and toks[i + 1].kind in {"ident", "kw"}:
            name = toks[i + 1].text
        return kind, name
    return None


class _PyFrame:
    def __init__(self, name: str, kind: str, line: int, indent: int) -> None:
        self.name = name
        self.kind = kind
        self.line = line
        self.indent = indent
        self.cc = 1
        self.max_indent = indent
        self.sloc = 0
        self.end_line = line


def _python_functions(
    text: str, tokens: list[Token], lang: Lang, code_lines: set[int]
) -> tuple[tuple[FunctionMetric, ...], int]:
    lines = text.splitlines()
    nlines = len(lines)
    indents = {i: _indent_width(line) for i, line in enumerate(lines, start=1)}
    unit = _indent_unit([indents[i] for i in code_lines])
    max_nest = 0
    for ln in code_lines:
        if unit:
            max_nest = max(max_nest, indents.get(ln, 0) // unit)

    by_line: dict[int, list[Token]] = {}
    depth = 0
    hard_after: dict[int, bool] = {}
    start_depth: dict[int, int] = {1: 0}
    for tok in tokens:
        if tok.kind == "nl":
            hard_after[tok.line] = depth == 0
            start_depth[tok.line + 1] = depth
            continue
        by_line.setdefault(tok.line, []).append(tok)
        if tok.kind == "op" and tok.text in _OPEN:
            depth += 1
        elif tok.kind == "op" and tok.text in _CLOSE:
            depth = max(0, depth - 1)
    if nlines:
        hard_after[nlines] = True

    frames: list[_PyFrame] = []
    found: list[FunctionMetric] = []
    prev_hard = True

    def close_until(indent: int) -> None:
        while frames and indent <= frames[-1].indent:
            fr = frames.pop()
            extra = 0
            if unit and fr.max_indent > fr.indent:
                extra = (fr.max_indent - fr.indent) // unit
            found.append(FunctionMetric(fr.name, fr.kind, fr.line, fr.end_line, fr.cc, extra, fr.sloc))

    for ln in range(1, nlines + 1):
        toks = by_line.get(ln, [])
        is_code = ln in code_lines
        ind = indents.get(ln, 0)
        if is_code and prev_hard:
            close_until(ind)
        if is_code and start_depth.get(ln, 0) == 0:
            opened = _py_scope_start(toks)
            if opened is not None:
                kind, name = opened
                frames.append(_PyFrame(name, kind, ln, ind))
        if is_code and frames:
            fr = frames[-1]
            fr.sloc += 1
            if ind > fr.max_indent:
                fr.max_indent = ind
            if ln > fr.end_line:
                fr.end_line = ln
            fr.cc += sum(1 for tok in toks if is_decision(tok, lang))
        prev_hard = hard_after.get(ln, True)
    close_until(-1)
    found.sort(key=lambda item: (item.line, item.name))
    return tuple(found), max_nest


def _looks_like_function(pre: list[Token]) -> tuple[bool, str, int]:
    cut = 0
    for i, tok in enumerate(pre):
        if tok.text in {";", "{", "}"}:
            cut = i + 1
    pre = pre[cut:]
    if not pre:
        return False, "", 0
    end = len(pre) - 1
    if pre[end].text == "=>":
        eq = -1
        for i in range(end - 1, -1, -1):
            if pre[i].kind == "op" and pre[i].text == "=":
                eq = i
                break
        if eq >= 0:
            for tok in reversed(pre[:eq]):
                if tok.kind == "ident":
                    return True, tok.text, tok.line
                if tok.text in {"const", "let", "var"}:
                    continue
                break
        if end >= 1 and pre[end - 1].kind == "ident":
            tok = pre[end - 1]
            return True, tok.text, tok.line
        return True, "<arrow>", pre[end].line

    i = end
    trailer_ops = {".", ",", "->", "::", "&", "*", "<", ">", "[", "]", "?", ":"}
    while i >= 0 and pre[i].text not in {")", "=>"}:
        tok = pre[i]
        if tok.kind in {"ident", "kw"} or (tok.kind == "op" and tok.text in trailer_ops):
            i -= 1
            continue
        return False, "", 0
    if i < 0 or pre[i].text != ")":
        return False, "", 0

    depth = 0
    open_at = -1
    for j in range(i, -1, -1):
        if pre[j].text == ")":
            depth += 1
        elif pre[j].text == "(":
            depth -= 1
            if depth == 0:
                open_at = j
                break
    if open_at < 0:
        return False, "", 0
    head = pre[:open_at]
    for tok in head:
        if tok.kind == "kw" and tok.text in _CONTROL:
            return False, "", 0
    name = ""
    name_line = pre[i].line
    j = open_at - 1
    if j >= 0 and head and head[-1].text == ">":
        gdepth = 0
        while j >= 0:
            if pre[j].text == ">":
                gdepth += 1
            elif pre[j].text == "<":
                gdepth -= 1
                if gdepth == 0:
                    j -= 1
                    break
            j -= 1
    while j >= 0 and pre[j].kind not in {"ident", "kw"}:
        j -= 1
    if j >= 0:
        name = pre[j].text
        name_line = pre[j].line
    if name in {"", "func", "function", "fn", "fun"}:
        name = "<anonymous>"
    return True, name, name_line


class _BraceFrame:
    def __init__(self, is_fn: bool, name: str, line: int, depth: int) -> None:
        self.is_fn = is_fn
        self.name = name
        self.line = line
        self.depth = depth
        self.cc = 1 if is_fn else 0
        self.max_depth = depth
        self.lines: set[int] = set()


def _brace_functions(
    tokens: list[Token], lang: Lang
) -> tuple[tuple[FunctionMetric, ...], int]:
    recent: list[Token] = []
    stack: list[_BraceFrame] = []
    found: list[FunctionMetric] = []
    cur_depth = 0
    max_depth = 0

    def nearest() -> _BraceFrame | None:
        for fr in reversed(stack):
            if fr.is_fn:
                return fr
        return None

    for tok in tokens:
        if tok.kind in {"nl", "comment"}:
            continue
        if tok.kind == "op" and tok.text == "{":
            is_fn, name, line = _looks_like_function(recent)
            cur_depth += 1
            max_depth = max(max_depth, cur_depth)
            fr = _BraceFrame(is_fn, name, line or tok.line, cur_depth)
            if is_fn:
                for prev in recent[-20:]:
                    fr.lines.add(prev.line)
                fr.lines.add(tok.line)
            stack.append(fr)
            recent.append(tok)
            continue
        if tok.kind == "op" and tok.text == "}":
            if stack:
                fr = stack.pop()
                if fr.is_fn:
                    nesting = fr.max_depth - fr.depth + 1
                    end_line = max(fr.lines) if fr.lines else fr.line
                    found.append(
                        FunctionMetric(fr.name, "fn", fr.line, end_line, fr.cc, nesting, len(fr.lines))
                    )
            cur_depth = max(0, cur_depth - 1)
            recent.append(tok)
            continue
        recent.append(tok)
        if len(recent) > 80:
            del recent[:-80]
        fn = nearest()
        if fn is not None:
            fn.lines.add(tok.line)
            if cur_depth > fn.max_depth:
                fn.max_depth = cur_depth
            if is_decision(tok, lang):
                fn.cc += 1
        for fr in stack:
            if cur_depth > fr.max_depth:
                fr.max_depth = cur_depth
    found.sort(key=lambda item: (item.line, item.name))
    return tuple(found), max_depth


def measure(text: str, lang: Lang, tokens: list[Token] | None = None) -> Measured:
    if tokens is None:
        tokens = tokenize(text, lang)
    total, sloc, comments, blanks, code_lines = _line_buckets(text, tokens)
    decisions = sum(1 for tok in tokens if is_decision(tok, lang))
    cyclomatic = 0 if sloc == 0 else 1 + decisions
    volume, difficulty = _halstead(tokens)
    if lang.family == "py":
        functions, nesting = _python_functions(text, tokens, lang, code_lines)
    elif lang.family in _BRACE:
        functions, nesting = _brace_functions(tokens, lang)
    else:
        functions, nesting = (), 0
    return Measured(
        lines=total,
        sloc=sloc,
        comment_lines=comments,
        blank_lines=blanks,
        cyclomatic=cyclomatic,
        max_nesting=nesting,
        maintainability=_file_mi(tokens, functions, volume, cyclomatic, sloc),
        halstead_volume=volume,
        halstead_difficulty=difficulty,
        functions=functions,
    )


def _file_mi(
    tokens: list[Token],
    functions: tuple[FunctionMetric, ...],
    volume: float,
    cyclomatic: int,
    sloc: int,
) -> float | None:
    """Median of per-function MI.

    The 1994 formula takes one cyclomatic number. Feeding it the sum of a
    whole module drives the index to zero on any large file, which is a
    property of the aggregation, not of the file. Per function, then the
    median, is the number a reader can compare.
    """
    scores: list[float] = []
    for fn in functions:
        span = [tok for tok in tokens if fn.line <= tok.line <= fn.end_line]
        vol, _difficulty = _halstead(span)
        score = maintainability(vol, fn.cyclomatic, fn.sloc)
        if score is not None:
            scores.append(score)
    if scores:
        return float(statistics.median(scores))
    return maintainability(volume, cyclomatic, sloc)
