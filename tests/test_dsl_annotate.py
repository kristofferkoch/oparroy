"""Annotation stage tests (DESIGN.md §7: refdes, back-annotation).

The stub symbol table needs its own prefix rules — the default rules
cover KiCad's libraries, not the stubs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from oparroy.dsl import (
    Annotation,
    AnnotationError,
    Circuit,
    annotate,
    annotation_from_pcb,
    apply_annotation,
    emit_netlist,
)
from oparroy.dsl.kicad_emit import part_tstamp

if TYPE_CHECKING:
    from conftest import StubSymbols

RULES = (
    ("Stub:R", "R"),
    ("Stub:C", "C"),
    ("Stub:DSER", "D"),
    ("Stub:CONN6", "J"),
    ("Stub:REG", "U"),
    ("Stub:LOAD", "U"),
)


def build(symbols: StubSymbols) -> Circuit:
    """Two resistors and a cap across two nets; one power marker."""
    c = Circuit("anno", symbols)
    r1 = c.part("Rs", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
    r2 = c.part("Rb", symbol="Stub:R", value="47k", footprint="StubFP:R_0603")
    c1 = c.part("Cs", symbol="Stub:C", value="10n", footprint="StubFP:C_0603")
    p1 = c.part("P1", symbol="power:+3V3", value="+3V3")
    a = c.net("a")
    b = c.net("b")
    c.connect(a, r1[1], c1[1], p1[1])
    c.connect(b, r1[2], r2[1], r2[2], c1[2])
    return c


def test_fresh_annotation_is_deterministic(symbols: StubSymbols) -> None:
    first = annotate(build(symbols), rules=RULES)
    second = annotate(build(symbols), rules=RULES)
    assert first.refs == second.refs == {"Rb": "R1", "Rs": "R2", "Cs": "C1"}
    assert first.to_json() == second.to_json()


def test_power_symbols_are_not_annotated(symbols: StubSymbols) -> None:
    refs = annotate(build(symbols), rules=RULES).refs
    assert "P1" not in refs


def test_prior_survives_a_source_edit(symbols: StubSymbols) -> None:
    prior = annotate(build(symbols), rules=RULES)

    def grown(symbols: StubSymbols) -> Circuit:
        c = build(symbols)
        r3 = c.part("Rx", symbol="Stub:R", value="220", footprint="StubFP:R_0603")
        c.connect("b", r3[1], r3[2])
        return c

    refreshed = annotate(grown(symbols), prior=prior, rules=RULES)
    # The edit adds one part; everything else keeps its refdes.
    assert refreshed.refs == {**prior.refs, "Rx": "R3"}


def test_prefix_mismatch_forces_reassignment(symbols: StubSymbols) -> None:
    # A stale table calling a resistor "C9" must not be kept.
    prior = Annotation({"Rs": "C9", "Rb": "R7", "Cs": "C3"}, circuit="anno")
    refreshed = annotate(build(symbols), prior=prior, rules=RULES)
    assert refreshed.refs["Rb"] == "R7"
    assert refreshed.refs["Cs"] == "C3"
    assert refreshed.refs["Rs"].startswith("R")


def test_unknown_symbol_class_raises(symbols: StubSymbols) -> None:
    c = Circuit("x", symbols)
    reg = c.part("REG1", symbol="Stub:REG", value="REG")
    a = c.net("a")
    c.connect(a, reg[1])
    with pytest.raises(AnnotationError, match="no refdes prefix rule"):
        annotate(c, rules=(("Stub:R", "R"),))


def test_apply_renames_and_keeps_identity(symbols: StubSymbols) -> None:
    circuit = build(symbols)
    renamed = apply_annotation(circuit, annotate(circuit, rules=RULES))
    assert set(renamed.parts) == {"R1", "R2", "C1", "P1"}
    assert renamed.parts["R2"].identity == "Rs"
    # The power marker passes through under its capture ref.
    assert renamed.parts["P1"].symbol.is_power


def test_apply_requires_full_coverage(symbols: StubSymbols) -> None:
    with pytest.raises(AnnotationError, match="covers no refdes"):
        apply_annotation(build(symbols), Annotation({"Rs": "R1"}))


def test_tstamps_survive_reannotation(symbols: StubSymbols) -> None:
    # pcbnew matches by tstamp: renaming must not re-key the comp's
    # tstamp, or every re-annotation would look like a new part.
    circuit = build(symbols)
    plain = emit_netlist(circuit)
    renamed = apply_annotation(circuit, annotate(circuit, rules=RULES))
    rendered = emit_netlist(renamed)
    stamp = str(part_tstamp("anno", "Rs"))
    assert f'(tstamps "{stamp}")' in plain
    assert f'(tstamps "{stamp}")' in rendered
    assert rendered != plain


def test_annotation_json_round_trip() -> None:
    table = Annotation({"WD1/Rs": "R12", "C1": "C2"}, circuit="oparroy-node")
    parsed = Annotation.from_json(table.to_json())
    assert parsed.refs == table.refs


def test_annotation_rejects_bad_refdes() -> None:
    with pytest.raises(AnnotationError, match="not a refdes"):
        Annotation({"Rs": "resistor"})
    with pytest.raises(AnnotationError, match="not a refdes"):
        Annotation({"Rs": "R"})


def test_annotation_rejects_duplicate_refdes() -> None:
    with pytest.raises(AnnotationError, match="both annotated"):
        Annotation({"Rs": "R1", "Rb": "R1"})


def test_annotation_from_json_rejects_garbage() -> None:
    with pytest.raises(AnnotationError, match="annotation file"):
        Annotation.from_json('{"refs": "R1"}')
    with pytest.raises(AnnotationError, match="annotation file"):
        Annotation.from_json('{"refs": {"Rs": 3}}')


def _pcb(*footprints: str) -> str:
    return "(kicad_pcb (version 20240108)\n" + "\n".join(footprints) + ")\n"


def _footprint(link: str, refdes: str, *, via: str = "path") -> str:
    if via == "path":
        joined = f'    (path "/deadbeef/{link}")'
    else:
        joined = f'    (uuid "{link}")'
    return (
        '  (footprint "StubFP:R_0603" (layer "F.Cu")\n'
        f"{joined}\n"
        f'    (property "Reference" "{refdes}" (at 0 0 0))\n'
        "  )"
    )


def test_back_annotation_reads_pcbnew_renumbering(symbols: StubSymbols) -> None:
    circuit = build(symbols)
    stamp_rs = str(part_tstamp("anno", "Rs"))
    stamp_cs = str(part_tstamp("anno", "Cs"))
    pcb = _pcb(
        _footprint(stamp_rs, "R7"),
        _footprint(stamp_cs, "C2", via="uuid"),
        _footprint("00000000-0000-0000-0000-000000000000", "H1"),
    )
    annotation = annotation_from_pcb(circuit, pcb)
    # Geographic renumbering folds back; the mounting hole pcbnew owns
    # (no capture tstamp) is skipped; unlisted parts fall out for
    # annotate(prior=...) to renumber.
    assert annotation.refs == {"Rs": "R7", "Cs": "C2"}


def test_back_annotation_merges_prior(symbols: StubSymbols) -> None:
    circuit = build(symbols)
    prior = Annotation({"Rb": "R9"}, circuit="anno")
    pcb = _pcb(_footprint(str(part_tstamp("anno", "Rs")), "R7"))
    annotation = annotation_from_pcb(circuit, pcb, prior=prior)
    assert annotation.refs == {"Rb": "R9", "Rs": "R7"}


def test_back_annotation_round_trip_through_annotate(symbols: StubSymbols) -> None:
    circuit = build(symbols)
    pcb = _pcb(_footprint(str(part_tstamp("anno", "Rs")), "R7"))
    refreshed = annotate(circuit, prior=annotation_from_pcb(circuit, pcb), rules=RULES)
    assert refreshed.refs["Rs"] == "R7"


def test_stale_circuit_name_rejected(symbols: StubSymbols) -> None:
    # The table names its design so a stale file against a renamed
    # capture is a visible error, not silent misassignment.
    prior = Annotation({"Rs": "R1"}, circuit="old-name")
    with pytest.raises(AnnotationError, match="old-name"):
        annotate(build(symbols), prior=prior, rules=RULES)
