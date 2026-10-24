"""Place the CI board as a deterministic, editable first layout sketch.

Run with KiCad's Python (inside the nix dev shell)::

    python boards/ci/grid-layout.py

The default input is the sibling ``oparroy-ci.kicad_pcb`` and the board is
updated in place. Pass another board path, or ``--output FILE``, to stage the
result elsewhere. ``placement-map.json`` must be current; capture paths, not
reference designators, drive placement.

This is a placement aid, not an autorouter. T0-T3 run left-to-right across the
top and T7-T4 run left-to-right across the bottom, so the logical ring follows
a horseshoe. Each MCU sits in the middle of its cell, its PHY follows signal
order, and its scan register and pull-downs form an inner-edge array. The
center carries the supervisor, power, debug trees, and aux/observe registers.
The bottom row mirrors local X coordinates but stays on the front side.

The script replaces the board's single rectangular Edge.Cuts outline and owns
the ``grid-layout`` documentation group. Existing scan-plane labels follow
their footprints. Nets, reference designators, footprint layers, project
settings, tracks, and zones are otherwise untouched. Save manual work before
running in place; re-running is deterministic.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pcbnew

_BOARD_WIDTH = 240.0
_BOARD_HEIGHT = 180.0
_TILE_WIDTH = 55.0
_TILE_HEIGHT = 55.0
_BOARD_MARGIN = 10.0
_CENTER_Y = 65.0
_GROUP_NAME = "grid-layout"
_TEXT_MM = 1.5


@dataclass(frozen=True, slots=True)
class _Point:
    x: float
    y: float
    angle: float = 0.0


class _Layout:
    def __init__(self, board: pcbnew.BOARD, mapping: dict[str, str]) -> None:
        self.board = board
        self.parts = {
            path: board.FindFootprintByReference(ref) for ref, path in mapping.items()
        }
        self.placed: set[str] = set()

    def place(self, path: str, point: _Point) -> None:
        if path in self.placed:
            msg = f"placement rule used {path} twice"
            raise RuntimeError(msg)
        footprint = self.parts.get(path)
        if footprint is None:
            msg = f"placement rule names missing footprint {path}"
            raise RuntimeError(msg)
        footprint.SetPosition(
            pcbnew.VECTOR2I(pcbnew.FromMM(point.x), pcbnew.FromMM(point.y))
        )
        footprint.SetOrientationDegrees(point.angle)
        self.placed.add(path)

    def optional(self, path: str, point: _Point) -> None:
        if path in self.parts:
            self.place(path, point)

    def grid(
        self,
        paths: list[str],
        *,
        xs: list[float],
        ys: list[float],
        transform: Callable[[_Point], _Point] | None = None,
        angle: float = 0.0,
    ) -> None:
        if len(paths) > len(xs) * len(ys):
            msg = f"grid has {len(xs) * len(ys)} slots for {len(paths)} parts"
            raise RuntimeError(msg)
        for index, path in enumerate(paths):
            point = _Point(xs[index % len(xs)], ys[index // len(xs)], angle)
            self.place(path, transform(point) if transform else point)

    def finish(self) -> None:
        missing = sorted(set(self.parts) - self.placed)
        if missing:
            msg = f"no placement rule for {len(missing)} parts: {', '.join(missing)}"
            raise RuntimeError(msg)


def _tile_layout(layout: _Layout, tile: int, column: int, *, bottom: bool) -> None:
    root = f"T{tile}"
    ox = _BOARD_MARGIN + column * _TILE_WIDTH
    oy = _BOARD_MARGIN if not bottom else _CENTER_Y + 50.0
    base_angle = 180.0 if bottom else 0.0

    def point(x: float, y: float, angle: float = 0.0) -> _Point:
        return _Point(
            ox + (_TILE_WIDTH - x if bottom else x),
            oy + y,
            (base_angle + angle) % 360.0,
        )

    def place(path: str, x: float, y: float, angle: float = 0.0) -> None:
        layout.place(path, point(x, y, angle))

    def optional(path: str, x: float, y: float, angle: float = 0.0) -> None:
        layout.optional(path, point(x, y, angle))

    place(f"{root}/U1", 27.5, 32.0)
    place(f"{root}/C1", 23.5, 26.5)
    place(f"{root}/C2", 31.5, 26.5)
    for index in range(4):
        place(f"{root}/TP{index + 1}", 28.0 + 6.0 * index, 20.0)

    # Ring A reads upstream to downstream; ring B reads in the return direction.
    place(f"{root}/PHY1/Rar", 4.0, 28.0)
    place(f"{root}/PHY1/SW1", 11.0, 28.0)
    place(f"{root}/PHY1/Rat", 18.0, 28.0)
    place(f"{root}/PHY1/Rbr", 4.0, 33.0)
    place(f"{root}/PHY1/Rbt", 18.0, 33.0)
    optional(f"{root}/PHY1/Dar", 11.0, 23.0)
    optional(f"{root}/PHY1/Dbt", 18.0, 23.0)
    phy_rest = sorted(
        path
        for path in layout.parts
        if path.startswith(f"{root}/PHY1/") and path not in layout.placed
    )
    layout.grid(
        phy_rest,
        xs=[4.0, 11.0, 18.0],
        ys=[38.0, 43.0],
        transform=lambda p: point(p.x, p.y, p.angle),
    )

    fi_parts = sorted(path for path in layout.parts if path.startswith(f"{root}/FI1/"))
    layout.grid(
        fi_parts,
        xs=[36.0, 42.0, 48.0, 54.0],
        ys=[23.0, 27.0, 31.0, 35.0, 39.0, 43.0],
        transform=lambda p: point(p.x, p.y, p.angle),
    )
    watchdog = sorted(path for path in layout.parts if path.startswith(f"{root}/WD1/"))
    layout.grid(
        watchdog,
        xs=[23.0, 27.5, 31.5],
        ys=[38.0, 43.0],
        transform=lambda p: point(p.x, p.y, p.angle),
    )

    leds = sorted(path for path in layout.parts if path.startswith(f"{root}/SL1/"))
    layout.grid(
        leds,
        xs=[3.0, 9.0, 15.0, 21.0, 27.0, 33.0, 39.0],
        ys=[3.0],
        transform=lambda p: point(p.x, p.y, p.angle),
    )
    for name, x in (("POT1", 10.0), ("SWA", 30.0), ("SWB", 45.0)):
        optional(f"{root}/{name}", x, 13.0, -base_angle if name == "POT1" else 0.0)
    optional(f"{root}/BZ1", 42.0, 11.0)
    optional(f"{root}/J1", 4.0, 13.0, 90.0)

    tile_scan = f"PLANE/{root}"
    place(f"{tile_scan}/U1", 7.0, 51.0)
    place(f"{tile_scan}/C1", 14.0, 51.0)
    pulls = sorted(path for path in layout.parts if path.startswith(f"PLANE/R_{root}_"))
    layout.grid(
        pulls,
        xs=[21.0 + 4.5 * index for index in range(7)],
        ys=[51.0],
        transform=lambda p: point(p.x, p.y, 90.0),
    )

    special = {f"{root}/U1", f"{root}/C1", f"{root}/C2", f"{root}/J1"}
    special.update(f"{root}/TP{index + 1}" for index in range(4))
    special.update(f"{root}/{name}" for name in ("POT1", "SWA", "SWB", "BZ1"))
    payload_rest = sorted(
        path
        for path in layout.parts
        if path.startswith(f"{root}/")
        and "/" not in path[len(root) + 1 :]
        and path not in layout.placed
        and path not in special
    )
    layout.grid(
        payload_rest,
        xs=[4.0, 10.0, 16.0, 22.0, 28.0],
        ys=[23.5],
        transform=lambda p: point(p.x, p.y, p.angle),
    )


def _center_layout(layout: _Layout) -> None:
    def point(x: float, y: float, angle: float = 0.0) -> _Point:
        return _Point(x, y, angle)

    layout.place("J0", point(12.0, 75.0, 90.0))
    layout.place("PWR/J1", point(5.0, 108.0, 90.0))
    layout.place("PWR/U1", point(22.0, 102.0))
    layout.place("PWR/Cin", point(18.0, 94.0))
    layout.place("PWR/Cout", point(27.0, 94.0))
    layout.place("PWR/Rcc1", point(18.0, 111.0))
    layout.place("PWR/Rcc2", point(27.0, 111.0))

    sup_fi = sorted(path for path in layout.parts if path.startswith("SUP/FI1/"))
    layout.grid(sup_fi, xs=[34.0, 40.0, 46.0], ys=[72.0, 80.0, 88.0, 96.0])
    layout.place("SUP/U1", point(66.0, 90.0))
    layout.place("SUP/U2", point(79.0, 90.0))
    layout.place("SUP/X1", point(79.0, 101.0))
    sup_caps = sorted(
        path
        for path in layout.parts
        if path.startswith("SUP/C") and "/" not in path[len("SUP/") :]
    )
    layout.grid(
        sup_caps,
        xs=[56.0, 61.0, 66.0, 71.0, 76.0, 81.0, 86.0],
        ys=[72.0, 110.0],
    )
    sup_rest = sorted(
        path
        for path in layout.parts
        if path.startswith("SUP/")
        and "/" not in path[len("SUP/") :]
        and path not in layout.placed
    )
    layout.grid(sup_rest, xs=[58.0, 66.0, 74.0, 82.0], ys=[82.0, 98.0, 113.0])

    _tree_layout(layout, "SWIO", 96.0, 106.0, 116.0)
    layout.place("SWIO/RUR", point(90.0, 104.0))
    for index in range(8):
        layout.place(
            f"SWIO/RU{index}",
            point(
                120.0 + 5.0 * (index // 4),
                (70.0, 80.0, 100.0, 110.0)[index % 4],
                90.0,
            ),
        )
    _tree_layout(layout, "DBG", 135.0, 145.0, 155.0)

    for index, stage in enumerate(("AUX0", "AUX1", "AUX2", "OBS0", "OBS1")):
        x = 168.0 + 12.0 * index
        layout.place(f"PLANE/{stage}/U1", point(x, 73.0))
        layout.place(f"PLANE/{stage}/C1", point(x, 82.0))
        prefixes = {
            "AUX0": ("PLANE/R_SUP_", "PLANE/R_SWIO_A0", "PLANE/R_SWIO_A1"),
            "AUX1": (
                "PLANE/R_SWIO_A2",
                "PLANE/R_WD_DEFEAT",
                "PLANE/R_POT_SEL1",
                "PLANE/R_POT_SEL3",
            ),
            "AUX2": ("PLANE/R_POT_SEL5", "PLANE/R_POT_SEL7"),
        }.get(stage, ())
        pulls = sorted(
            path
            for path in layout.parts
            if any(path.startswith(prefix) for prefix in prefixes)
        )
        layout.grid(
            pulls,
            xs=[x],
            ys=[88.0 + 3.5 * row for row in range(9)],
            angle=90.0,
        )
    layout.place("PLANE/R_OE", point(160.0, 114.0, 90.0))


def _tree_layout(layout: _Layout, root: str, x1: float, x2: float, x3: float) -> None:
    layout.place(f"{root}/SW1", _Point(x1, 90.0))
    for index, y in enumerate((78.0, 102.0)):
        layout.place(f"{root}/SW{index + 2}", _Point(x2, y))
    for index, y in enumerate((70.0, 80.0, 100.0, 110.0)):
        layout.place(f"{root}/SW{index + 4}", _Point(x3, y))


def _drawing_group(board: pcbnew.BOARD) -> pcbnew.PCB_GROUP:
    group = next((g for g in board.Groups() if g.GetName() == _GROUP_NAME), None)
    if group is None:
        group = pcbnew.PCB_GROUP(board)
        group.SetName(_GROUP_NAME)
        board.Add(group)
    return group


def _draw_guides(board: pcbnew.BOARD) -> None:
    group = _drawing_group(board)
    old_shapes = sorted(
        (item for item in group.GetItems() if isinstance(item, pcbnew.PCB_SHAPE)),
        key=lambda item: (item.GetStart().y, item.GetStart().x),
    )
    old_texts = sorted(
        (item for item in group.GetItems() if isinstance(item, pcbnew.PCB_TEXT)),
        key=lambda item: item.GetText(),
    )
    boxes = [
        (
            _BOARD_MARGIN + column * _TILE_WIDTH,
            _BOARD_MARGIN if row == 0 else _CENTER_Y + 50.0,
            f"T{tile}",
        )
        for row, tiles in enumerate(((0, 1, 2, 3), (4, 5, 6, 7)))
        for column, tile in enumerate(tiles)
    ]
    while len(old_shapes) < len(boxes):
        shape = pcbnew.PCB_SHAPE(board)
        shape.SetShape(pcbnew.SHAPE_T_RECT)
        shape.SetLayer(pcbnew.Dwgs_User)
        shape.SetWidth(pcbnew.FromMM(0.1))
        board.Add(shape)
        group.AddItem(shape)
        old_shapes.append(shape)
    while len(old_texts) < len(boxes):
        text = pcbnew.PCB_TEXT(board)
        text.SetLayer(pcbnew.Dwgs_User)
        text.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        size = pcbnew.FromMM(_TEXT_MM)
        text.SetTextSize(pcbnew.VECTOR2I(size, size))
        board.Add(text)
        group.AddItem(text)
        old_texts.append(text)
    if len(old_shapes) != len(boxes) or len(old_texts) != len(boxes):
        msg = f"{_GROUP_NAME} group has unexpected drawings; remove it and rerun"
        raise RuntimeError(msg)
    for shape, text, (x, y, name) in zip(old_shapes, old_texts, boxes, strict=True):
        shape.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        shape.SetEnd(
            pcbnew.VECTOR2I(
                pcbnew.FromMM(x + _TILE_WIDTH), pcbnew.FromMM(y + _TILE_HEIGHT)
            )
        )
        text.SetText(name)
        text.SetPosition(
            pcbnew.VECTOR2I(pcbnew.FromMM(x + _TILE_WIDTH / 2), pcbnew.FromMM(y + 1.5))
        )


def _set_outline(board: pcbnew.BOARD) -> None:
    edges = [
        drawing
        for drawing in board.GetDrawings()
        if drawing.GetLayer() == pcbnew.Edge_Cuts
    ]
    if len(edges) != 1 or edges[0].GetShape() != pcbnew.SHAPE_T_RECT:
        msg = "grid sketch expects one rectangular Edge.Cuts outline"
        raise RuntimeError(msg)
    edges[0].SetStart(pcbnew.VECTOR2I(0, 0))
    edges[0].SetEnd(
        pcbnew.VECTOR2I(pcbnew.FromMM(_BOARD_WIDTH), pcbnew.FromMM(_BOARD_HEIGHT))
    )


def _follow_scan_labels(board: pcbnew.BOARD, mapping: dict[str, str]) -> None:
    stage_refs = {
        path.split("/")[1]: ref
        for ref, path in mapping.items()
        if path.startswith("PLANE/") and path.endswith("/U1")
    }
    group = next((g for g in board.Groups() if g.GetName() == "scan-labels"), None)
    if group is None:
        return
    for label in group.GetItems():
        ref = stage_refs.get(label.GetText())
        if ref is None:
            continue
        position = board.FindFootprintByReference(ref).GetPosition()
        label.SetPosition(pcbnew.VECTOR2I(position.x, position.y - pcbnew.FromMM(4.0)))


def _validate(board: pcbnew.BOARD) -> None:
    boxes = []
    for footprint in board.GetFootprints():
        box = footprint.GetBoundingBox(False, False)  # noqa: FBT003 — pcbnew API
        if (
            box.GetLeft() < 0
            or box.GetTop() < 0
            or box.GetRight() > pcbnew.FromMM(_BOARD_WIDTH)
            or box.GetBottom() > pcbnew.FromMM(_BOARD_HEIGHT)
        ):
            msg = f"{footprint.GetReference()} lies outside the board outline"
            raise RuntimeError(msg)
        boxes.append((footprint.GetReference(), box))
    overlaps = []
    for index, (ref_a, a) in enumerate(boxes):
        for ref_b, b in boxes[index + 1 :]:
            if (
                a.GetLeft() < b.GetRight()
                and a.GetRight() > b.GetLeft()
                and a.GetTop() < b.GetBottom()
                and a.GetBottom() > b.GetTop()
            ):
                overlaps.append(f"{ref_a}/{ref_b}")
    if overlaps:
        msg = f"{len(overlaps)} footprint overlaps: {', '.join(overlaps[:30])}"
        raise RuntimeError(msg)


def main() -> None:
    """Place a board from its placement map and save the sketch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", nargs="?", type=Path, help="input .kicad_pcb")
    parser.add_argument("--output", type=Path, help="output path (default: in place)")
    parser.add_argument("--map", dest="map_path", type=Path, help="placement-map.json")
    args = parser.parse_args()
    board_path = args.board or Path(__file__).with_name("oparroy-ci.kicad_pcb")
    map_path = args.map_path or board_path.with_name("placement-map.json")
    output_path = args.output or board_path

    board = pcbnew.LoadBoard(str(board_path))
    mapping = json.loads(map_path.read_text(encoding="utf-8"))
    board_refs = {footprint.GetReference() for footprint in board.GetFootprints()}
    if board_refs != set(mapping):
        msg = (
            "placement map and board differ: "
            f"map-only={sorted(set(mapping) - board_refs)}, "
            f"board-only={sorted(board_refs - set(mapping))}"
        )
        raise RuntimeError(msg)

    layout = _Layout(board, mapping)
    for column, tile in enumerate(range(4)):
        _tile_layout(layout, tile, column, bottom=False)
    for column, tile in enumerate((7, 6, 5, 4)):
        _tile_layout(layout, tile, column, bottom=True)
    _center_layout(layout)
    layout.finish()
    _set_outline(board)
    _draw_guides(board)
    _follow_scan_labels(board, mapping)
    _validate(board)
    pcbnew.SaveBoard(str(output_path), board)
    sys.stdout.write(
        f"placed {len(layout.placed)} footprints on a "
        f"{_BOARD_WIDTH:g} x {_BOARD_HEIGHT:g} mm grid: {output_path}\n"
    )


if __name__ == "__main__":
    main()
