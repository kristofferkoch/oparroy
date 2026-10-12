"""Extraction guard for scripts/check-sparse.

The script parses each gate's ``sparse-checkout: |`` block out of
.github/workflows/ci.yml with awk (the file stays the single source of
truth for the sparse sets). These tests pin the parse against the real
ci.yml: if the workflow's shape drifts from the formatting contract the
awk program relies on, they fail here instead of letting the script
silently rehearse an empty or mangled pattern set.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check-sparse"

# One sentinel per gate: a pattern that must always be in that gate's
# sparse set for the gate to work at all.
SENTINELS = {
    "pytest": ["flake.nix", "src/**", "tests/**"],
    "firmware": ["flake.nix", "firmware/**", "scripts/**"],
    "sim": ["flake.nix", "circuits/**", "scripts/**"],
    "rv32ec": ["flake.nix", "firmware/**", "meson/**"],
    "reproducibility": ["flake.nix", "firmware/**", "meson/**"],
}


@pytest.mark.parametrize("gate", sorted(SENTINELS))
def test_sparse_patterns_extract(gate: str) -> None:
    result = subprocess.run(  # noqa: S603 — runs the repo's own script
        [str(SCRIPT), "--list", gate],
        capture_output=True,
        text=True,
        check=True,
    )
    patterns = result.stdout.splitlines()
    assert patterns, f"{gate}: no patterns extracted from ci.yml"
    for line in patterns:
        assert line.strip() == line, f"{gate}: mangled pattern {line!r}"
        assert line, f"{gate}: empty pattern"
        assert not line.startswith("#"), f"{gate}: comment leaked into patterns"
    for sentinel in SENTINELS[gate]:
        assert sentinel in patterns, f"{gate}: {sentinel} missing from {patterns}"


def test_unknown_gate_fails() -> None:
    result = subprocess.run(  # noqa: S603 — runs the repo's own script
        [str(SCRIPT), "--list", "lint"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "unknown gate" in result.stderr
