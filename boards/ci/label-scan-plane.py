"""Label the scan plane's shift registers on canvas — pcbnew console helper.

Run inside pcbnew's scripting console (Tools → Scripting Console):

    exec(open("/home/kek/src/oparroy/boards/ci/label-scan-plane.py").read())

Reads the sibling ``placement-map.json`` (``python -m design.ci_board
--placement-map boards/ci/placement-map.json``), finds every
``PLANE/<stage>/U1`` footprint, and draws the stage name on Dwgs.User
just above it — while placing, you can see which shift register you are
dragging. The daisy-chain order with each stage's role prints to the
console. Footprint positions are never changed.

Labels live in the ``scan-labels`` pcbnew group: re-running moves them
to follow their footprints (run it again after moving a register),
other drawings and groups are untouched, and Ctrl+Z reverts the whole
run. Labels are updated in place, never deleted — deleting a board
item whose wrapper still owns it double-frees under SWIG. Delete the
group by hand to drop the labels.

The CHAIN table mirrors the daisy chain in design/scan_plane.py
(docs/scan-plane.md §1) — update both together if the stage order or
the bit map changes. Regenerate placement-map.json whenever the netlist
is re-emitted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_LABEL_GROUP = "scan-labels"
_LABEL_ABOVE_MM = 4.0  # label sits this far above the footprint
_TEXT_MM = 1.2
_PREVIEW = 8  # refdes shown per report line before "+N more"
_PLANE_PATH_DEPTH = 3  # PLANE/<stage>/U1

#: Daisy-chain order with each stage's role (design/scan_plane.py,
#: docs/scan-plane.md §1/§3). T6 is the measurement tile
#: (ci_tiles.MEASUREMENT_TILE): its 595 slice drives `pwr` only.
CHAIN: tuple[tuple[str, str], ...] = (
    ("AUX0", "595, supervisor injector + swio_a0/a1"),
    ("AUX1", "595, swio_a2 + wd_defeat + tiles 1/3 input overrides"),
    ("AUX2", "595, tiles 5/7 input overrides, bits 6/7 spare"),
    ("T0", "595, tile 0 control byte"),
    ("T1", "595, tile 1 control byte"),
    ("T2", "595, tile 2 control byte"),
    ("T3", "595, tile 3 control byte"),
    ("T4", "595, tile 4 control byte"),
    ("T5", "595, tile 5 control byte"),
    ("T6", "595, tile 6 (measurement) — pwr only, 7 spares"),
    ("T7", "595, tile 7 control byte"),
    ("OBS0", "165, tiles 0-3 sel/3v3n sense"),
    ("OBS1", "165, tiles 4-7 sel/3v3n sense"),
)


def _find_map(board_file: str) -> Path:
    """Locate placement-map.json: next to the open board, else the repo cwd."""
    candidates = [
        Path(board_file).parent / "placement-map.json",
        Path.cwd() / "boards/ci/placement-map.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    msg = (
        "placement-map.json not found next to the board or under "
        f"{Path.cwd() / 'boards/ci'} — regenerate it: "
        "python -m design.ci_board --placement-map "
        "boards/ci/placement-map.json > tests/golden/oparroy-ci.net"
    )
    raise FileNotFoundError(msg)


def _stage_footprints(
    mapping: dict[str, str], board_refs: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Collect stage name → footprint for every PLANE/<stage>/U1 in the map."""
    stages: dict[str, Any] = {}
    stale: list[str] = []
    for ref, identity in mapping.items():
        parts = identity.split("/")
        if len(parts) != _PLANE_PATH_DEPTH or parts[0] != "PLANE" or parts[2] != "U1":
            continue
        footprint = board_refs.get(ref)
        if footprint is None:
            stale.append(ref)
        else:
            stages[parts[1]] = footprint
    return stages, stale


def _report(
    stages: dict[str, Any],
    stale: list[str],
    labeled: int,
    leftover: dict[str, Any],
) -> None:
    """Print the chain table and whatever the run could not label."""
    sys.stdout.write("scan-plane daisy chain, ser order (RP2040 → … → RP2040):\n")
    known = set(stages)
    for stage, role in CHAIN:
        footprint = stages.get(stage)
        ref = footprint.GetReference() if footprint is not None else "—"
        sys.stdout.write(f"  {stage:5s} {ref:4s} {role}\n")
        known.discard(stage)
    if known:
        sys.stdout.write(
            f"map stages not in CHAIN ({', '.join(sorted(known))}) — CHAIN here "
            "drifted from design/scan_plane.py\n"
        )
    if stale:
        preview = ", ".join(sorted(stale)[:_PREVIEW])
        more = f" (+{len(stale) - _PREVIEW} more)" if len(stale) > _PREVIEW else ""
        sys.stdout.write(
            f"map refdes not on the board: {preview}{more} — the map is stale "
            "or the board is behind the netlist\n"
        )
    if leftover:
        sys.stdout.write(
            f"{len(leftover)} labels whose stage left the map "
            f"({', '.join(sorted(leftover))}) — kept, not deleted; remove the "
            f"{_LABEL_GROUP} group by hand to drop them\n"
        )
    sys.stdout.write(f"{labeled} labels on Dwgs.User (group {_LABEL_GROUP})\n")


def main() -> None:
    """Draw a stage-name label above each scan-plane shift register."""
    import pcbnew  # noqa: PLC0415 — resolves only on KiCad's PYTHONPATH

    board = pcbnew.GetBoard()
    mapping = json.loads(_find_map(board.GetFileName()).read_text(encoding="utf-8"))
    board_refs = {f.GetReference(): f for f in board.GetFootprints()}
    stages, stale = _stage_footprints(mapping, board_refs)

    # Reuse the previous run's labels instead of deleting them:
    # board.Remove frees the C++ object while its SWIG wrapper still
    # owns it, and the double free on garbage collection corrupts the
    # heap (later wrappers come back as bare SwigPyObjects). Labels are
    # updated in place; ones whose stage left the map are reported,
    # never deleted.
    group = next((g for g in board.Groups() if g.GetName() == _LABEL_GROUP), None)
    if group is None:
        group = pcbnew.PCB_GROUP(board)
        group.SetName(_LABEL_GROUP)
        board.Add(group)
    leftover = {item.GetText(): item for item in group.GetItems()}

    labeled = 0
    for stage, footprint in stages.items():
        label = leftover.pop(stage, None)
        if label is None:
            label = pcbnew.PCB_TEXT(board)
            label.SetText(stage)
            label.SetLayer(pcbnew.Dwgs_User)
            size = pcbnew.FromMM(_TEXT_MM)
            label.SetTextSize(pcbnew.VECTOR2I(size, size))
            label.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
            board.Add(label)
            group.AddItem(label)
        position = footprint.GetPosition()
        label.SetPosition(
            pcbnew.VECTOR2I(position.x, position.y - pcbnew.FromMM(_LABEL_ABOVE_MM))
        )
        labeled += 1

    pcbnew.Refresh()
    _report(stages, stale, labeled, leftover)


main()
