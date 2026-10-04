"""ngspice simulation-netlist emitter: the DUT netlist (DESIGN.md §7).

Emits the circuit as a ``.subckt`` wrapper around the flat IR — the
DUT half of the simulation split. The boundary is deliberate: stimulus
and ``.meas`` assertions stay in external bench decks
(``circuits/**/tb_*.cir``, run by ``scripts/sim-run``); the DSL emits
the circuit, benches drive it. A capture whose ports match a
hand-written DUT's ``.subckt`` interface drops into the same benches
unmodified, so either capture can drive the run while T7e ports the
``circuits/`` DUTs over.

Spice bindings are declared ad hoc until T7c's parts DB owns them: a
small symbol-keyed table (``_BINDINGS``) maps KiCad symbols to element
forms, and the caller passes the ``.model`` definitions (``models=``)
a model-backed part references — the part's value names its model, as
in any hand-written deck. Power-library symbols are schematic-only and
excluded, matching the KiCad emitter.

Emission is byte-identical across runs (DESIGN.md §8): parts and
models iterate in natural sorted order and nothing dated or
path-derived leaks in. A hierarchical circuit is flattened first;
flattened names carry ``/`` (``WD1/Rs``), which ngspice accepts
verbatim in element and node names.
"""

from collections.abc import Callable, Mapping

from oparroy.dsl.ir import Circuit, DefinitionError, Part, Pin, natural_key


def emit_spice(
    circuit: Circuit,
    *,
    name: str | None = None,
    models: Mapping[str, str] | None = None,
) -> str:
    """Emit the circuit as an ngspice DUT netlist.

    ``name`` is the ``.subckt`` name (default: the circuit name) — set
    it to match the interface the bench decks instantiate. Ports land
    on the ``.subckt`` line in declaration order. ``models`` maps
    model name → definition body (``"d(is=200n …)"``); only models a
    placed part actually references are emitted, and a reference
    without a definition raises.
    """
    if circuit.instances:
        circuit = circuit.flatten()
    subckt = name if name is not None else circuit.name
    definitions = dict(models) if models is not None else {}
    referenced: set[str] = set()
    elements = [
        line
        for ref in sorted(circuit.parts, key=natural_key)
        for line in _emit_part(circuit.parts[ref], referenced)
    ]
    undefined = sorted(referenced - definitions.keys(), key=natural_key)
    if undefined:
        msg = (
            f"parts reference spice models {undefined} with no definition — "
            "pass them via models= (ad hoc until T7c's parts DB owns them)"
        )
        raise DefinitionError(msg)
    lines = [
        (
            f"* {subckt} — ngspice DUT netlist emitted by the oparroy DSL; "
            "regenerate, do not edit."
        ),
        f".subckt {subckt}{_port_list(circuit)}",
    ]
    lines.extend(
        f".model {model} {definitions[model]}"
        for model in sorted(referenced, key=natural_key)
    )
    lines.extend(elements)
    lines.append(f".ends {subckt}")
    return "\n".join(lines) + "\n"


def _port_list(circuit: Circuit) -> str:
    ports = " ".join(circuit.ports)
    return f" {ports}" if ports else ""


def _emit_part(part: Part, referenced: set[str]) -> list[str]:
    if part.symbol.is_power:
        return []
    binding = _BINDINGS.get(part.symbol.ref)
    if binding is None:
        msg = (
            f"no spice binding for symbol {part.symbol.ref!r} (part {part.ref}) — "
            "bindings are declared ad hoc until T7c's parts DB owns them"
        )
        raise DefinitionError(msg)
    return binding(part, referenced)


def _two_pin(kind: str) -> Callable[[Part, set[str]], list[str]]:
    """Build a binding for an unpolarized two-pin primitive (R, C)."""

    def emit(part: Part, _referenced: set[str]) -> list[str]:
        return [
            (
                f"{_element_name(kind, part.ref)} {_net_of(part['1'])} "
                f"{_net_of(part['2'])} {_require_value(part)}"
            )
        ]

    return emit


def _element_name(kind: str, ref: str) -> str:
    """Return the element name: the ref, brought to start with its kind letter.

    ngspice keys the element type on the name's first letter. Captured
    refs already carry it by convention (``Rs``, ``Cp``); a flattened
    hierarchical ref (``WD1/Rs``) does not, so the kind letter is
    prepended there.
    """
    return ref if ref.upper().startswith(kind) else f"{kind}{ref}"


def _bat54s(part: Part, referenced: set[str]) -> list[str]:
    """Expand the BAT54S series pair into its two diode elements.

    Pin 1 (A) is the pair's overall anode, pin 2 (K) the overall
    cathode, pin 3 (COM) the shared middle — so the A element spans
    anode→com and the K element com→cathode. The part value names the
    model, as in a hand-written deck.
    """
    model = _require_value(part)
    referenced.add(model)
    anode = _net_of(part["1"])
    cathode = _net_of(part["2"])
    com = _net_of(part["3"])
    base = _element_name("D", part.ref)
    return [
        f"{base}A {anode} {com} {model}",
        f"{base}K {com} {cathode} {model}",
    ]


def _led(part: Part, referenced: set[str]) -> list[str]:
    """Emit an LED as a plain diode element (pin 1 = cathode, pin 2 = anode)."""
    model = _require_value(part)
    referenced.add(model)
    anode = _net_of(part["2"])
    cathode = _net_of(part["1"])
    return [f"{_element_name('D', part.ref)} {anode} {cathode} {model}"]


_BINDINGS: dict[str, Callable[[Part, set[str]], list[str]]] = {
    "Device:R": _two_pin("R"),
    "Device:C": _two_pin("C"),
    "Device:LED": _led,
    "Diode:BAT54S": _bat54s,
}


def _require_value(part: Part) -> str:
    if part.value is None:
        msg = (
            f"{part.ref} ({part.symbol.ref}) has no value — the spice emitter needs one"
        )
        raise DefinitionError(msg)
    return part.value


def _net_of(pin: Pin) -> str:
    if pin.net is None:
        msg = f"{pin.part.ref}.{pin.number} is not connected"
        raise DefinitionError(msg)
    return pin.net.name
