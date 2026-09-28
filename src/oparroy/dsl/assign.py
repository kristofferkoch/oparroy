"""Footprint assignment: the first stage between capture and pcbnew.

Class defaults resolve during capture (a bin subclass carries its
footprint, DESIGN.md §7), so most parts arrive here assigned. This
stage applies the override table — per-instance data, keyed by the
flat capture path (``WD1/Rs``) — and dumps the current assignment for
editing. The checker's missing-footprint error runs on the
post-assignment IR: a part reaching ``check`` without a footprint has
neither default nor override.

Override tables are data, not code: JSON on disk, byte-identical on
write (sorted keys), so the assignment diff in review is the change.
"""

import json
from collections.abc import Mapping

from oparroy.dsl.ir import Circuit, DefinitionError, natural_key
from oparroy.dsl.kicadlib import LibraryError, split_ref


def footprint_map(circuit: Circuit) -> dict[str, str | None]:
    """Dump the current assignment: flat capture path → footprint.

    ``None`` marks a part with neither class default nor override.
    A hierarchical circuit is flattened first, so paths are the same
    ones ``check`` and the emitters report.
    """
    if circuit.instances:
        circuit = circuit.flatten()
    return {
        ref: circuit.parts[ref].footprint
        for ref in sorted(circuit.parts, key=natural_key)
    }


def assign_footprints(circuit: Circuit, overrides: Mapping[str, str]) -> Circuit:
    """Apply an override table; returns the flat, assigned circuit.

    Keys are flat capture paths; an unknown key means the capture moved
    under the table and raises — silently ignoring it would ship the
    class default where review approved an override. Values must be
    ``Lib:Name`` references, same as any declared footprint.
    """
    if circuit.instances:
        circuit = circuit.flatten()
    unknown = sorted(set(overrides) - set(circuit.parts), key=natural_key)
    if unknown:
        msg = f"footprint overrides name unknown parts {unknown}"
        raise DefinitionError(msg)
    for ref, footprint in overrides.items():
        try:
            split_ref(footprint)
        except LibraryError:
            msg = (
                f"footprint override for {ref!r} is {footprint!r}, "
                "not a 'Lib:Name' reference"
            )
            raise DefinitionError(msg) from None
        circuit.parts[ref].footprint = footprint
    return circuit


def overrides_to_json(overrides: Mapping[str, str]) -> str:
    """Serialize an override table: sorted keys, byte-identical output."""
    return json.dumps(dict(sorted(overrides.items())), indent=2) + "\n"


def overrides_from_json(text: str) -> dict[str, str]:
    """Parse an override table, rejecting anything but a flat string map."""
    raw = json.loads(text)
    if not isinstance(raw, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in raw.items()
    ):
        msg = "footprint overrides must be a JSON object of path: footprint"
        raise DefinitionError(msg)
    return dict(raw)
