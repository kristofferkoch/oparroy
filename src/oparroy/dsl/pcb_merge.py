"""Merge an emitted constraint skeleton into a live board via pcbnew.

The skeleton emitter (:mod:`oparroy.dsl.pcb_emit`) is a seed, not a
merge: re-running it against ``boards/node/`` would clobber hand layout
and GUI-authored project state (DRC exclusions, defaults, viewports).
This module scripts pcbnew's Board Setup → Import Settings from Another
Board merge through KiCad's own SWIG API (DESIGN.md §7: lean on KiCad's
own code), so constraint updates stay hands-off. Mechanism verified
against KiCad 10.0.6 on 2026-10-04 (against behavior and source —
``dialog_board_setup.cpp``'s import, ``board.cpp``,
``board_design_settings.cpp``):

- ``live.GetDesignSettings().CloneFrom(staged.GetDesignSettings())``
  transfers the board-level settings — stackup and layers (saved to
  the ``.kicad_pcb``) and the board minimums and severities (saved to
  the ``.kicad_pro``).
- Net classes are the exception. ``CloneFrom`` *re-points* the design
  settings' ``m_NetSettings`` shared_ptr at the staged project's
  NET_SETTINGS, while ``SaveBoard`` persists net settings from the live
  project's own object — so the classes, the Default class, and the
  net→class assignments are deep-copied into that object (captured
  before the CloneFrom; in-place mutation of it is what persists) via
  ``SetNetclasses`` / ``SetDefaultNetclass`` /
  ``SetNetclassLabelAssignment``. SWIG's ``GetNetclassLabelAssignments``
  is opaque, so the assignments are read back from the staged
  ``.kicad_pro`` JSON instead — the emitter's own output, in both its
  scalar form and KiCad's native list form.
- ``CloneFrom`` also overwrites the live board's DRC exclusions with
  the staged board's empty set. GUI-authored exclusions are
  marker-backed: at ``LoadBoard`` they resolve from the ``.kicad_pro``
  strings against the board's items (unresolvable ones are dropped by
  KiCad itself), so ``live.RecordDRCExclusions()`` after the CloneFrom
  rebuilds them from the live markers. The GUI-owned settings the DSL
  does not own — zone defaults and the pre-defined track/via sizes —
  are snapshotted before the CloneFrom and restored after it, so a
  constraint update touches nothing the layout author tuned. Net-class
  patterns, net colors, diff-pair presets, violation severities,
  teardrops, and tuning patterns are not reachable through SWIG and
  follow the staged skeleton, matching a full GUI Import Settings; the
  emitter writes none of them.
- ``SaveBoard`` rewrites both files: layout intact (37 footprints /
  355 tracks on the node board), GUI-owned project keys
  (``board.design_settings.defaults``, viewports) preserved.

Run it with the flake's ``kicad-python`` wrapper — nixpkgs' pcbnew is
built for Python 3.14, which the uv-pinned 3.13 interpreter cannot
import (verified 2026-10-04). Hence the lazy ``import pcbnew`` inside
:func:`merge_settings`: the module stays stdlib-only at import time so
pytest's ``--doctest-modules`` can import it under 3.13.

Usage (in the nix dev shell):

    kicad-python -m oparroy.dsl.pcb_merge <staged_dir> <live_dir>

``python -m design.node_board --apply DIR`` wraps exactly this call.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


class PcbMergeError(Exception):
    """The staged or live directory cannot be merged as asked."""


@dataclass(frozen=True)
class MergeReport:
    """What the merge pushed into the live board, for printing."""

    staged_pcb: Path
    live_pcb: Path
    net_classes: tuple[str, ...]
    stackup: bool
    minimums: bool


def merge_settings(staged_dir: Path, live_dir: Path) -> MergeReport:
    """Push the staged skeleton's design settings into the live board.

    ``staged_dir`` holds a fresh emitter output (exactly one
    ``.kicad_pcb`` plus its sibling ``.kicad_pro``); ``live_dir`` holds
    the board under layout with the same filename. The staged board
    must be a bare skeleton — any footprint or track means the
    arguments are swapped, and the merge refuses rather than
    overwriting live layout with an empty board.
    """
    import pcbnew  # ty: ignore[unresolved-import]  # noqa: PLC0415 — lazy: see the module docstring

    staged_pcb = _single_pcb(staged_dir, "staged")
    live_pcb = live_dir / staged_pcb.name
    if not live_pcb.is_file():
        msg = f"no live board at {live_pcb}"
        raise PcbMergeError(msg)
    staged = pcbnew.LoadBoard(str(staged_pcb))
    live = pcbnew.LoadBoard(str(live_pcb))
    footprints = len(list(staged.GetFootprints()))
    tracks = len(list(staged.GetTracks()))
    if footprints or tracks:
        msg = (
            f"staged board {staged_pcb} carries {footprints} footprints and"
            f" {tracks} tracks — it looks like a live board, not an emitted"
            " skeleton (swapped arguments?)"
        )
        raise PcbMergeError(msg)
    live_settings = live.GetDesignSettings()
    live_net_settings = live_settings.m_NetSettings
    staged_net_settings = staged.GetDesignSettings().m_NetSettings
    # Snapshot the GUI-owned settings the DSL does not own; restored
    # after the CloneFrom, which would overwrite them with stock values.
    zone_defaults = pcbnew.ZONE_SETTINGS()
    zone_defaults.CopyFrom(live_settings.GetDefaultZoneSettings())
    track_widths = pcbnew.intVector(live_settings.m_TrackWidthList)
    via_dimensions = pcbnew.VIA_DIMENSION_Vector(live_settings.m_ViasDimensionsList)
    live_settings.CloneFrom(staged.GetDesignSettings())
    live.RecordDRCExclusions()
    live_settings.GetDefaultZoneSettings().CopyFrom(zone_defaults)
    live_settings.m_TrackWidthList = track_widths
    live_settings.m_ViasDimensionsList = via_dimensions
    live_net_settings.SetNetclasses(staged_net_settings.GetNetclasses())
    live_net_settings.SetDefaultNetclass(staged_net_settings.GetDefaultNetclass())
    live_net_settings.ClearNetclassLabelAssignments()
    staged_project = staged_pcb.with_suffix(".kicad_pro")
    for net, class_names in _staged_assignments(staged_project).items():
        names = pcbnew.STRINGSET()
        for class_name in class_names:
            names.insert(class_name)
        live_net_settings.SetNetclassLabelAssignment(net, names)
    pcbnew.SaveBoard(str(live_pcb), live)
    return MergeReport(
        staged_pcb=staged_pcb,
        live_pcb=live_pcb,
        net_classes=tuple(sorted(map(str, staged.GetNetClasses()))),
        stackup="(stackup" in staged_pcb.read_text(encoding="utf-8"),
        minimums=_has_minimums(staged_project),
    )


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: merge STAGED_DIR's settings into LIVE_DIR's board."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "staged_dir", type=Path, help="directory holding the emitted skeleton"
    )
    parser.add_argument(
        "live_dir", type=Path, help="directory holding the board under layout"
    )
    args = parser.parse_args(argv)
    try:
        report = merge_settings(args.staged_dir, args.live_dir)
    except PcbMergeError as error:
        sys.stderr.write(f"pcb_merge: {error}\n")
        raise SystemExit(2) from None
    sys.stdout.write(
        f"merged {report.staged_pcb} → {report.live_pcb}:"
        f" net classes {', '.join(report.net_classes) or '(none)'},"
        f" stackup {'applied' if report.stackup else 'absent'},"
        f" board minimums {'applied' if report.minimums else 'absent'}\n"
    )


def _single_pcb(directory: Path, role: str) -> Path:
    pcbs = sorted(directory.glob("*.kicad_pcb"))
    if len(pcbs) != 1:
        msg = (
            f"expected exactly one .kicad_pcb in the {role} directory"
            f" {directory}, found {len(pcbs)}"
        )
        raise PcbMergeError(msg)
    return pcbs[0]


def _staged_assignments(project: Path) -> dict[str, list[str]]:
    """Read the staged project's net→classes map.

    The emitter writes scalar class values (net-settings meta version 3);
    a KiCad-re-saved project writes lists (version 5). Both read.
    """
    data = json.loads(project.read_text(encoding="utf-8"))
    assignments = data.get("net_settings", {}).get("netclass_assignments", {})
    return {
        str(net): [classes] if isinstance(classes, str) else [str(c) for c in classes]
        for net, classes in assignments.items()
    }


def _has_minimums(project: Path) -> bool:
    data = json.loads(project.read_text(encoding="utf-8"))
    return bool(data.get("board", {}).get("design_settings", {}).get("rules", {}))


if __name__ == "__main__":
    main()
