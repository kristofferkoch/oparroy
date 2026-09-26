"""S-expression parser tests: KiCad escapes and error paths."""

import pytest

from oparroy.dsl.sexpr import SexpError, parse


def test_kicad_escapes_decode() -> None:
    assert parse(r'(a "x\ny")') == ["a", "x\ny"]
    assert parse(r'(a "x\ty")') == ["a", "x\ty"]
    assert parse(r'(a "x\"y")') == ["a", 'x"y']
    assert parse(r'(a "x\\y")') == ["a", "x\\y"]


def test_unknown_escape_passes_through() -> None:
    assert parse(r'(a "x\qy")') == ["a", "xqy"]


def test_trailing_content_raises() -> None:
    with pytest.raises(SexpError, match="trailing content"):
        parse("(a) (b)")


def test_unclosed_paren_raises() -> None:
    with pytest.raises(SexpError, match="unclosed"):
        parse("(a (b)")


def test_unterminated_string_raises() -> None:
    with pytest.raises(SexpError, match="unterminated string"):
        parse('(a "b)')


def test_missing_open_paren_raises() -> None:
    with pytest.raises(SexpError, match="expected '\\('"):
        parse("a")
