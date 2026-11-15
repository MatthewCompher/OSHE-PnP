"""Board model loaded from a KiCad 6+ ``.kicad_pcb`` file.

Everything here is in **KiCad's own coordinates**: millimetres, +Y down the
screen, origin at the page origin, angles counter-clockwise as seen on screen
from the top. That is deliberate: the model matches what KiCad and its Gerber
export say, so it can be checked against them. ``frame.py`` (milestone 2)
converts to the job frame.

KiCad facts this relies on (checked against Gerbers in the tests):
* Footprint ``(at x y rot)`` is the footprint origin and orientation.
* Pad ``(at x y angle)``: x, y are local to the footprint and *unrotated*;
  ``angle`` is the pad's absolute orientation (it already includes the
  footprint's rotation).
* For a footprint on B.Cu the local coordinates are stored already flipped,
  so local -> board is the same rotate + translate for both sides.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable

from . import geometry as g
from .outline import Outline, OutlineError, build_outline, collect_edge_paths
from .sexpr import Node, SExprError, parse

# KiCad 6.0 was the first release with the format this reader expects
# (properties, start/mid/end arcs, absolute pad angles).
MIN_FILE_VERSION = 20211014
# Newest format this was tested with (KiCad 10.0). Newer files load with a warning.
TESTED_FILE_VERSION = 20260206

SIDES = ("top", "bottom")
_SIDE_OF_LAYER = {"F.Cu": "top", "B.Cu": "bottom"}

# Flags that can appear in a footprint's (attr ...) list, or (KiCad 9+) as
# their own "(flag yes)" child.
_ATTR_FLAGS = ("board_only", "exclude_from_pos_files", "exclude_from_bom",
               "allow_missing_courtyard", "dnp", "allow_soldermask_bridges")


class BoardError(ValueError):
    """The file can't be used; the message says what to fix."""


def _expand_layers(names: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    for n in names:
        if n.startswith("*."):
            out += [f"F.{n[2:]}", f"B.{n[2:]}"]
        elif n.startswith("F&B."):
            out += [f"F.{n[4:]}", f"B.{n[4:]}"]
        else:
            out.append(n)
    return tuple(dict.fromkeys(out))


@dataclass
class Pad:
    number: str          # "1", "2", "" for paste-only / mechanical pads
    kind: str            # smd | thru_hole | np_thru_hole | connect
    shape: str           # rect | roundrect | circle | oval | trapezoid | chamfered_rect | custom
    local_x: float
    local_y: float
    x: float             # board coordinates (KiCad frame)
    y: float
    angle: float         # absolute orientation, degrees CCW on screen
    w: float
    h: float
    layers: tuple[str, ...]
    roundrect_rratio: float | None = None

    @property
    def copper_sides(self) -> tuple[str, ...]:
        return tuple(_SIDE_OF_LAYER[l] for l in ("F.Cu", "B.Cu") if l in self.layers)

    @property
    def is_copper(self) -> bool:
        return bool(self.copper_sides)


@dataclass
class Footprint:
    ref: str
    value: str
    lib_id: str          # "Resistor_SMD:R_0603_1608Metric"
    side: str            # "top" | "bottom"
    x: float             # footprint origin, KiCad frame
    y: float
    rot: float           # degrees CCW on screen (as KiCad shows it)
    mount: str           # "smd" | "through_hole" | "unspecified"
    flags: frozenset[str]
    properties: dict[str, str]
    pads: list[Pad]
    uuid: str = ""
    line: int = 0        # line in the .kicad_pcb (for messages)

    @property
    def key(self) -> str:
        """Stable id for settings (exclusions, alignment picks): KiCad's uuid, which
        survives reannotating and moving the part. Falls back to ref@position."""
        return self.uuid or f"{self.ref}@{self.x:g},{self.y:g}"

    @property
    def package(self) -> str:
        """Footprint name without the library: 'R_0603_1608Metric'."""
        return self.lib_id.split(":", 1)[-1]

    @property
    def dnp(self) -> bool:
        return "dnp" in self.flags

    @property
    def exclude_from_pos(self) -> bool:
        return "exclude_from_pos_files" in self.flags

    @property
    def board_only(self) -> bool:
        return "board_only" in self.flags

    @property
    def copper_pads(self) -> list[Pad]:
        return [p for p in self.pads if p.is_copper]

    def to_board(self, lx: float, ly: float) -> g.Point:
        dx, dy = g.kicad_rotate(lx, ly, self.rot)
        return self.x + dx, self.y + dy

    def pad_center(self) -> g.Point | None:
        """Middle of the copper pads' bounding box (None if no copper pads)."""
        pads = self.copper_pads
        if not pads:
            return None
        x0, y0, x1, y1 = g.bbox((p.x, p.y) for p in pads)
        return (x0 + x1) / 2, (y0 + y1) / 2


@dataclass
class Board:
    path: str
    name: str
    file_version: int
    generator_version: str
    thickness: float
    outline: Outline
    footprints: list[Footprint]
    warnings: list[str] = field(default_factory=list)
    aux_origin: g.Point = (0.0, 0.0)    # Setup > drill/place file origin (KiCad frame)

    def on_side(self, side: str) -> list[Footprint]:
        if side not in SIDES:
            raise ValueError(f"side must be one of {SIDES}, not {side!r}")
        return [f for f in self.footprints if f.side == side]

    def duplicate_refs(self) -> dict[str, int]:
        """References used by more than one footprint (ignoring board-only items)."""
        c = Counter(f.ref for f in self.footprints if not f.board_only)
        return {r: n for r, n in sorted(c.items()) if n > 1}

    def unannotated_refs(self) -> list[str]:
        """References KiCad hasn't numbered yet, like 'R?' or 'U'."""
        return sorted({f.ref for f in self.footprints if not f.board_only
                       and (f.ref.endswith("?") or not any(ch.isdigit() for ch in f.ref))})


# ---------------------------------------------------------------------------
# loading


def _float_at(node: Node | None) -> tuple[float, float, float]:
    if node is None:
        return 0.0, 0.0, 0.0
    a = [float(v) for v in node.atoms if _is_number(v)]
    return (a + [0.0, 0.0, 0.0])[0], (a + [0.0, 0.0, 0.0])[1], (a[2] if len(a) > 2 else 0.0)


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except ValueError:
        return False


def _footprint_text(fp: Node, key: str) -> str | None:
    """Reference/Value: KiCad 8+ uses (property "Reference" ..); 6/7 also had fp_text."""
    for p in fp.nodes("property"):
        if p.atoms and p.atoms[0] == key:
            return p.atoms[1] if len(p.atoms) > 1 else ""
    for t in fp.nodes("fp_text"):
        if t.atoms and t.atoms[0] == key.lower():
            return t.atoms[1] if len(t.atoms) > 1 else ""
    return None


def _make_transform(fp: Node):
    fx, fy, frot = _float_at(fp.node("at"))

    def to_board(lx: float, ly: float) -> g.Point:
        dx, dy = g.kicad_rotate(lx, ly, frot)
        return fx + dx, fy + dy

    return to_board


def _parse_footprint(fp: Node) -> Footprint:
    lib_id = fp.atoms[0] if fp.atoms else ""
    layer = fp.value("layer", "F.Cu")
    if layer not in _SIDE_OF_LAYER:
        raise BoardError(f"footprint {lib_id} at line {fp.line} is on layer {layer!r}, expected F.Cu or B.Cu")
    x, y, rot = _float_at(fp.node("at"))

    attr = fp.node("attr")
    attr_atoms = attr.atoms if attr is not None else []
    mount = next((a for a in attr_atoms if a in ("smd", "through_hole")), "unspecified")
    flags = {a for a in attr_atoms if a in _ATTR_FLAGS}
    for flag in _ATTR_FLAGS:  # newer files may write (dnp yes) etc.
        v = fp.value(flag)
        if v is not None and v.lower() in ("yes", "true"):
            flags.add(flag)

    props = {p.atoms[0]: (p.atoms[1] if len(p.atoms) > 1 else "")
             for p in fp.nodes("property") if p.atoms}

    to_board = _make_transform(fp)
    pads: list[Pad] = []
    for pn in fp.nodes("pad"):
        a = pn.atoms
        number, kind, shape = (a + ["", "", ""])[:3]
        lx, ly, pangle = _float_at(pn.node("at"))
        size = pn.floats("size") or [0.0, 0.0]
        bx, by = to_board(lx, ly)
        layers_node = pn.node("layers")
        rr = pn.value("roundrect_rratio")
        pads.append(Pad(
            number=number, kind=kind, shape=shape,
            local_x=lx, local_y=ly, x=bx, y=by, angle=pangle,
            w=size[0], h=size[1] if len(size) > 1 else size[0],
            layers=_expand_layers(layers_node.atoms if layers_node else []),
            roundrect_rratio=float(rr) if rr is not None else None,
        ))

    return Footprint(
        ref=_footprint_text(fp, "Reference") or "",
        value=_footprint_text(fp, "Value") or "",
        lib_id=lib_id, side=_SIDE_OF_LAYER[layer], x=x, y=y, rot=rot,
        mount=mount, flags=frozenset(flags), properties=props, pads=pads,
        uuid=fp.value("uuid") or fp.value("tstamp") or "", line=fp.line,
    )


def load_board(path: str | os.PathLike, chain_tol: float | None = None) -> Board:
    """Read a .kicad_pcb file. Raises BoardError with a fix-it message on problems."""
    path = os.fspath(path)
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise BoardError(f"can't open {path}: {e.strerror}") from e
    return load_board_text(text, path=path, chain_tol=chain_tol)


def load_board_text(text: str, path: str = "<memory>", chain_tol: float | None = None) -> Board:
    try:
        root = parse(text)
    except SExprError as e:
        raise BoardError(f"{os.path.basename(path)} is not a valid KiCad file: {e}") from e
    if root.name != "kicad_pcb":
        raise BoardError(f"{os.path.basename(path)} is not a KiCad board (starts with '{root.name}')")

    warnings: list[str] = []
    version = int(root.value("version", "0") or 0)
    if version < MIN_FILE_VERSION:
        raise BoardError(
            f"board file format {version} is from KiCad 5 or older. "
            "Open it in KiCad 6 or newer and save it, then try again."
        )
    if version > TESTED_FILE_VERSION:
        warnings.append(f"board file format {version} is newer than tested ({TESTED_FILE_VERSION}); "
                        "check the preview carefully")

    if root.node("module") is not None:
        raise BoardError("board uses the old 'module' syntax; re-save it in KiCad 6 or newer")

    general = root.node("general")
    thickness = float(general.value("thickness", "1.6")) if general is not None else 1.6

    footprints = [_parse_footprint(fp) for fp in root.nodes("footprint")]

    kwargs = {} if chain_tol is None else {"chain_tol": chain_tol}
    try:
        open_paths, loops = collect_edge_paths(root, _make_transform)
        outline = build_outline(open_paths, loops, **kwargs)
    except OutlineError as e:
        raise BoardError(str(e)) from e
    if outline.extra:
        warnings.append(f"{len(outline.extra)} Edge.Cuts shape(s) lie outside the main board edge "
                        "(a panel or a second board?); only the largest outline is used")

    title_block = root.node("title_block")
    title = title_block.value("title") if title_block is not None else None
    name = title or os.path.splitext(os.path.basename(path))[0]

    aux = (0.0, 0.0)
    setup = root.node("setup")
    if setup is not None:
        ao = setup.floats("aux_axis_origin")
        if ao and len(ao) >= 2:
            aux = (ao[0], ao[1])

    return Board(path=path, name=name, file_version=version,
                 generator_version=root.value("generator_version", "") or "",
                 thickness=thickness, outline=outline, footprints=footprints,
                 warnings=warnings, aux_origin=aux)