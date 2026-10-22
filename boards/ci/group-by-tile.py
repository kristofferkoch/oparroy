"""Group the CI board's footprints by capture tile — pcbnew console helper.

Run inside pcbnew's scripting console (Tools → Scripting Console):

    exec(open("/home/kek/src/oparroy/boards/ci/group-by-tile.py").read())

Reads the sibling ``placement-map.json`` (``python -m design.ci_board
--placement-map boards/ci/placement-map.json``) and creates one pcbnew
group per first capture-path component — T0..T7, SUP, PLANE, and
"board" for everything without a ``/`` — so a tile's parts select and
move as one. Re-running replaces the groups it made; groups of any
other name are untouched, as are all footprint positions. Ctrl+Z
reverts the whole run.

Footprints the map doesn't know (hand-added mounting holes, a stale
map) are reported, not grouped. Regenerate the map whenever the
netlist is re-emitted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PREVIEW = 8  # refdes shown per report line before "+N more"


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


def _report(
    added: dict[str, int],
    unknown: list[str],
    mapping: dict[str, str],
    board_refs: set[str],
    skipped: int,
) -> None:
    """Write the run's summary to the console."""
    for name in sorted(added):
        sys.stdout.write(f"{name}: {added[name]} footprints\n")
    if unknown:
        preview = ", ".join(sorted(unknown)[:_PREVIEW])
        more = f" (+{len(unknown) - _PREVIEW} more)" if len(unknown) > _PREVIEW else ""
        sys.stdout.write(
            f"not in the map, left ungrouped: {preview}{more} — "
            "regenerate placement-map.json if these are capture parts\n"
        )
    stale_refs = sorted(set(mapping) - board_refs)
    if stale_refs:
        sys.stdout.write(
            f"{len(stale_refs)} map refdes not on the board "
            f"({', '.join(stale_refs[:_PREVIEW])}) — the map is stale or "
            "the board is behind the netlist\n"
        )
    if skipped:
        sys.stdout.write(f"{skipped} footprints kept in their existing groups\n")


def main() -> None:
    """Create one pcbnew group per capture-path root on the open board."""
    import pcbnew  # noqa: PLC0415 — resolves only on KiCad's PYTHONPATH

    board = pcbnew.GetBoard()
    mapping = json.loads(_find_map(board.GetFileName()).read_text(encoding="utf-8"))
    footprints = list(board.GetFootprints())

    members: dict[str, list] = {}
    unknown: list[str] = []
    for footprint in footprints:
        identity = mapping.get(footprint.GetReference())
        if identity is None:
            unknown.append(footprint.GetReference())
            continue
        root = identity.split("/", maxsplit=1)[0] if "/" in identity else "board"
        members.setdefault(root, []).append(footprint)

    # Reuse this script's groups from a previous run, clearing their
    # members through RemoveItem (board.Remove would leave each member's
    # parent-group pointer dangling). Groups of any other name are
    # hand-made: their members are skipped, never stolen.
    existing = {g.GetName(): g for g in board.Groups()}

    added: dict[str, int] = {}
    skipped = 0
    for name in sorted(members):
        group = existing.get(name)
        if group is None:
            group = pcbnew.PCB_GROUP(board)
            group.SetName(name)
            board.Add(group)
        else:
            for item in list(group.GetItems()):
                group.RemoveItem(item)
        count = 0
        for footprint in members[name]:
            if footprint.GetParentGroup() is None:
                group.AddItem(footprint)
                count += 1
            else:
                skipped += 1
        added[name] = count

    pcbnew.Refresh()
    board_refs = {f.GetReference() for f in footprints}
    _report(added, unknown, mapping, board_refs, skipped)


main()
