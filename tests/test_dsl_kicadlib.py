"""KiCad library integration tests (need the nix-provisioned libraries)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from oparroy.dsl import (
    KiCadLibraries,
    LibraryError,
    PinType,
    UnknownSymbolError,
)

if TYPE_CHECKING:
    from pathlib import Path


def _library_with_symbols(tmp_path: Path, body: str) -> KiCadLibraries:
    """Build a KiCadLibraries over one hand-written Stub.kicad_sym."""
    (tmp_path / "Stub.kicad_sym").write_text(
        f'(kicad_symbol_lib (version 20231120) (generator "test")\n{body})\n',
        encoding="utf-8",
    )
    return KiCadLibraries(tmp_path, tmp_path)


def test_lookup_resistor(kicad_libs: KiCadLibraries) -> None:
    symbol = kicad_libs.lookup("Device:R")
    pins = {pin.number: pin.type for pin in symbol.pins}
    assert pins == {"1": PinType.PASSIVE, "2": PinType.PASSIVE}
    assert "R_*" in symbol.footprint_filters


def test_lookup_dual_diode(kicad_libs: KiCadLibraries) -> None:
    symbol = kicad_libs.lookup("Diode:BAT54S")
    assert {pin.number for pin in symbol.pins} == {"1", "2", "3"}


def test_lookup_extends_inherits_pins(kicad_libs: KiCadLibraries) -> None:
    # Filter_EMI_C extends C_Feedthrough in Device.kicad_sym.
    symbol = kicad_libs.lookup("Device:Filter_EMI_C")
    min_inherited_pins = 2
    assert len(symbol.pins) >= min_inherited_pins


def test_lookup_unknown_symbol_raises(kicad_libs: KiCadLibraries) -> None:
    with pytest.raises(UnknownSymbolError):
        kicad_libs.lookup("Device:NO_SUCH_SYMBOL")


def test_footprint_existence(kicad_libs: KiCadLibraries) -> None:
    assert kicad_libs.exists("Resistor_SMD:R_0603_1608Metric")
    assert not kicad_libs.exists("Resistor_SMD:NOPE")


def test_project_footprint_dir_resolves(tmp_path: Path) -> None:
    kicad_root = tmp_path / "kicad"
    project_root = tmp_path / "project"
    local = project_root / "Oparroy.pretty" / "Local.kicad_mod"
    local.parent.mkdir(parents=True)
    local.write_text("(kicad_mod)", encoding="utf-8")
    libs = KiCadLibraries(kicad_root, kicad_root, (project_root,))
    assert libs.exists("Oparroy:Local")
    assert not libs.exists("Oparroy:Nope")
    # Without the extra root, the same ref does not resolve.
    assert not KiCadLibraries(kicad_root, kicad_root).exists("Oparroy:Local")


def test_from_env_requires_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPARROY_KICAD_SYMBOL_DIR", raising=False)
    monkeypatch.delenv("OPARROY_KICAD_FOOTPRINT_DIR", raising=False)
    with pytest.raises(LibraryError, match="nix dev shell"):
        KiCadLibraries.from_env()


def test_from_env_picks_up_project_footprint_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project_root = tmp_path / "project"
    local = project_root / "Oparroy.pretty" / "Local.kicad_mod"
    local.parent.mkdir(parents=True)
    local.write_text("(kicad_mod)", encoding="utf-8")
    monkeypatch.setenv("OPARROY_KICAD_SYMBOL_DIR", str(tmp_path))
    monkeypatch.setenv("OPARROY_KICAD_FOOTPRINT_DIR", str(tmp_path))
    monkeypatch.setenv("OPARROY_PROJECT_FOOTPRINT_DIR", str(project_root))
    assert KiCadLibraries.from_env().exists("Oparroy:Local")


def test_from_env_rejects_missing_project_footprint_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPARROY_KICAD_SYMBOL_DIR", str(tmp_path))
    monkeypatch.setenv("OPARROY_KICAD_FOOTPRINT_DIR", str(tmp_path))
    monkeypatch.setenv("OPARROY_PROJECT_FOOTPRINT_DIR", str(tmp_path / "nope"))
    with pytest.raises(LibraryError, match="OPARROY_PROJECT_FOOTPRINT_DIR"):
        KiCadLibraries.from_env()


def test_from_env_rejects_missing_symbol_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPARROY_KICAD_SYMBOL_DIR", str(tmp_path / "nope"))
    monkeypatch.setenv("OPARROY_KICAD_FOOTPRINT_DIR", str(tmp_path))
    with pytest.raises(LibraryError, match="OPARROY_KICAD_SYMBOL_DIR"):
        KiCadLibraries.from_env()


def test_from_env_rejects_missing_footprint_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OPARROY_KICAD_SYMBOL_DIR", str(tmp_path))
    monkeypatch.setenv("OPARROY_KICAD_FOOTPRINT_DIR", str(tmp_path / "nope"))
    with pytest.raises(LibraryError, match="OPARROY_KICAD_FOOTPRINT_DIR"):
        KiCadLibraries.from_env()


def test_lookup_cyclic_extends_raises(tmp_path: Path) -> None:
    libs = _library_with_symbols(
        tmp_path,
        '(symbol "A" (extends "B") (symbol "A_0_1"))\n'
        '(symbol "B" (extends "A") (symbol "B_0_1"))',
    )
    with pytest.raises(LibraryError, match="cyclic 'extends' chain"):
        libs.lookup("Stub:A")


def test_lookup_self_extends_raises(tmp_path: Path) -> None:
    libs = _library_with_symbols(
        tmp_path, '(symbol "A" (extends "A") (symbol "A_0_1"))'
    )
    with pytest.raises(LibraryError, match="cyclic 'extends' chain"):
        libs.lookup("Stub:A")


def test_lookup_missing_extends_parent_names_it(tmp_path: Path) -> None:
    libs = _library_with_symbols(
        tmp_path, '(symbol "A" (extends "MISSING") (symbol "A_0_1"))'
    )
    with pytest.raises(UnknownSymbolError, match="extends 'MISSING'"):
        libs.lookup("Stub:A")


def test_unknown_pin_type_raises(tmp_path: Path) -> None:
    # A KiCad pin type we don't know must fail loud, not silently
    # degrade to UNSPECIFIED and corrupt the power-driver rules.
    libs = _library_with_symbols(
        tmp_path,
        '(symbol "A" (symbol "A_0_1" (pin quantum line (at 0 0 0)'
        ' (name "X") (number "1"))))',
    )
    with pytest.raises(LibraryError, match="unknown KiCad pin type"):
        libs.lookup("Stub:A")


def test_conflicting_pin_definitions_reported(tmp_path: Path) -> None:
    # Same pin number redefined with a different name/type across
    # subsymbols (upstream library bugs do this): last wins, conflict
    # recorded. Identical duplicates (pin stacking) stay silent.
    libs = _library_with_symbols(
        tmp_path,
        '(symbol "A" (symbol "A_0_1" (pin power_in line (at 0 0 0)'
        ' (name "GND") (number "8")))'
        ' (symbol "A_1_1" (pin output line (at 0 0 0)'
        ' (name "Q3") (number "8"))))',
    )
    symbol = libs.lookup("Stub:A")
    assert symbol.pin_conflicts == ("8",)
    pin8 = symbol.pin("8")
    assert pin8 is not None
    assert pin8.name == "Q3"


def test_real_conflicting_symbol_resolves(kicad_libs: KiCadLibraries) -> None:
    # 74xx:74LS09 redefines pins 3/6/8/11 across body styles (open_collector
    # vs output) — a real upstream-library conflict, resolved not fatal.
    symbol = kicad_libs.lookup("74xx:74LS09")
    assert symbol.pin_conflicts == ("3", "6", "8", "11")
