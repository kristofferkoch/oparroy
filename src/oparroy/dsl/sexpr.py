"""Minimal s-expression reader for KiCad's library file formats.

Parses the dialect used by ``.kicad_sym`` files: parenthesized lists,
double-quoted strings with backslash escapes, and bare atoms. Atoms and
strings both surface as ``str`` — KiCad's grammar is positional, so the
distinction is not needed at the call sites here.

>>> parse('(symbol "R" (pin passive line (number "1")))')
['symbol', 'R', ['pin', 'passive', 'line', ['number', '1']]]
"""

type Sexp = str | list[Sexp]

_WHITESPACE = " \t\r\n"
_DELIMITERS = '() \t\r\n"'

# KiCad's string escapes (eeschema's own convention); any other \X
# passes through as literal X.
_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


class SexpError(Exception):
    """Malformed s-expression input."""


def parse(text: str) -> list[Sexp]:
    """Parse one top-level s-expression; raises SexpError on bad input."""
    node, pos = _parse_node(text, _skip_ws(text, 0))
    if _skip_ws(text, pos) != len(text):
        msg = "trailing content after top-level s-expression"
        raise SexpError(msg)
    return node


def _skip_ws(text: str, pos: int) -> int:
    while pos < len(text) and text[pos] in _WHITESPACE:
        pos += 1
    return pos


def _parse_node(text: str, pos: int) -> tuple[list[Sexp], int]:
    if pos >= len(text) or text[pos] != "(":
        msg = f"expected '(' at offset {pos}"
        raise SexpError(msg)
    pos += 1
    items: list[Sexp] = []
    while True:
        pos = _skip_ws(text, pos)
        if pos >= len(text):
            msg = "unclosed '('"
            raise SexpError(msg)
        char = text[pos]
        if char == ")":
            return items, pos + 1
        if char == "(":
            child, pos = _parse_node(text, pos)
            items.append(child)
        elif char == '"':
            token, pos = _parse_string(text, pos)
            items.append(token)
        else:
            token, pos = _parse_atom(text, pos)
            items.append(token)


def _parse_string(text: str, pos: int) -> tuple[str, int]:
    pos += 1
    chars: list[str] = []
    while pos < len(text):
        char = text[pos]
        if char == '"':
            return "".join(chars), pos + 1
        if char == "\\":
            pos += 1
            if pos >= len(text):
                break
            chars.append(_ESCAPES.get(text[pos], text[pos]))
        else:
            chars.append(char)
        pos += 1
    msg = "unterminated string"
    raise SexpError(msg)


def _parse_atom(text: str, pos: int) -> tuple[str, int]:
    start = pos
    while pos < len(text) and text[pos] not in _DELIMITERS:
        pos += 1
    if pos == start:
        msg = f"empty atom at offset {start}"
        raise SexpError(msg)
    return text[start:pos], pos
