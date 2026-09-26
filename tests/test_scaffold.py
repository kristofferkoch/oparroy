"""Scaffold smoke test: proves the uv/pytest harness imports the package."""

import oparroy


def test_package_imports() -> None:
    assert oparroy.__doc__ is not None
