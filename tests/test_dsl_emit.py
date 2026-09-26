"""Netlist emitter tests: golden output, determinism, order independence."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from oparroy.dsl import Circuit, emit_netlist

if TYPE_CHECKING:
    from conftest import StubSymbols

# Independent recomputation of the emitter's tstamp namespace — if the
# emitter's scheme drifts, this golden test goes red.
_TSTAMP_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://oparroy.koch.no/dsl/tstamp")

EXPECTED_TEMPLATE = """\
(export (version "E")
  (design
    (source "emit")
    (tool "oparroy-dsl"))
  (components
    (comp (ref "R1")
      (value "1k")
      (footprint "StubFP:R_0603")
      (sheetpath (names "/") (tstamps "/"))
      (tstamps "{r1}"))
    (comp (ref "R2")
      (value "1k")
      (footprint "StubFP:R_0603")
      (sheetpath (names "/") (tstamps "/"))
      (tstamps "{r2}"))
  )
  (nets
    (net (code "1") (name "a")
      (node (ref "R1") (pin "1") (pintype "passive"))
      (node (ref "R2") (pin "2") (pintype "passive")))
    (net (code "2") (name "mid")
      (node (ref "R1") (pin "2") (pintype "passive"))
      (node (ref "R2") (pin "1") (pintype "passive")))
  )
)
"""

EXPECTED = EXPECTED_TEMPLATE.format(
    r1=uuid.uuid5(_TSTAMP_NS, "emit/R1"),
    r2=uuid.uuid5(_TSTAMP_NS, "emit/R2"),
)


def build(symbols: StubSymbols, *, swap: bool = False) -> Circuit:
    c = Circuit("emit", symbols)
    r1 = c.part("R1", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
    r2 = c.part("R2", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
    a = c.net("a")
    mid = c.net("mid")
    pins = (r2[2], r1[1]) if swap else (r1[1], r2[2])
    c.connect(a, *pins)
    c.connect(mid, r1[2], r2[1])
    return c


def test_emit_matches_golden(symbols: StubSymbols) -> None:
    assert emit_netlist(build(symbols)) == EXPECTED


def test_emission_is_byte_identical_across_runs(symbols: StubSymbols) -> None:
    assert emit_netlist(build(symbols)) == emit_netlist(build(symbols))


def test_emission_independent_of_connect_order(symbols: StubSymbols) -> None:
    assert emit_netlist(build(symbols)) == emit_netlist(build(symbols, swap=True))


def test_empty_net_emits_without_nodes(symbols: StubSymbols) -> None:
    circuit = build(symbols)
    circuit.net("spare")
    rendered = emit_netlist(circuit)
    assert '(net (code "3") (name "spare"))' in rendered


def test_quoting_escapes_strings(symbols: StubSymbols) -> None:
    c = Circuit("esc", symbols)
    r1 = c.part("R1", symbol="Stub:R", value='4k7 "1%"', footprint="StubFP:R_0603")
    n = c.net("a")
    c.connect(n, r1[1], r1[2])
    rendered = emit_netlist(c)
    assert '(value "4k7 \\"1%\\"")' in rendered


def test_quoting_escapes_backslashes(symbols: StubSymbols) -> None:
    c = Circuit("esc", symbols)
    r1 = c.part("R1", symbol="Stub:R", value=r"10k\5%", footprint="StubFP:R_0603")
    n = c.net("a")
    c.connect(n, r1[1], r1[2])
    rendered = emit_netlist(c)
    assert r'(value "10k\\5%")' in rendered


def test_emission_independent_of_declaration_order(symbols: StubSymbols) -> None:
    def reversed_build() -> Circuit:
        c = Circuit("emit", symbols)
        r2 = c.part("R2", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
        r1 = c.part("R1", symbol="Stub:R", value="1k", footprint="StubFP:R_0603")
        mid = c.net("mid")
        a = c.net("a")
        c.connect(mid, r2[1], r1[2])
        c.connect(a, r2[2], r1[1])
        return c

    assert emit_netlist(build(symbols)) == emit_netlist(reversed_build())


def test_power_symbols_excluded_from_netlist(symbols: StubSymbols) -> None:
    # Power-library symbols mark the rail for checks but never reach
    # the board: no comp, no node (eeschema excludes them likewise).
    c = build(symbols)
    marker = c.part("P1", symbol="power:+3V3", value="+3V3")
    c.connect("a", marker[1])
    rendered = emit_netlist(c)
    assert '(comp (ref "P1")' not in rendered
    assert '(node (ref "P1")' not in rendered
    assert '(node (ref "R1") (pin "1") (pintype "passive"))' in rendered
