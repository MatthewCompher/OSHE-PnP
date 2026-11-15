"""A plate = one side of the board, already in the job frame.

This is what the UI draws and what gets sliced into a job file. SMD parts are
included; do-not-populate SMD parts are included too, marked ``dnp`` (the job
file keeps them with ``"skip": true``). Parts you exclude in pnpslice are
handled the same way (see slicer.py). Everything else is listed as skipped
with a reason so the UI can show why.

Pick point: JOB_FORMAT.md says x, y should equal the centre of the
footprint's pads, so that's what ``JobPart.x/y`` is. ``origin`` keeps the
footprint origin for comparison.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .board import Board, Footprint
from .frame import Frame
from .geometry import Point

# Footprint origin vs middle of the pads: above this, the UI flags the part.
ORIGIN_OFFSET_WARN_MM = 0.1


@dataclass
class JobPad:
    number: str
    shape: str
    x: float          # job frame
    y: float
    angle: float      # job frame, CCW seen from this side
    w: float
    h: float
    roundrect_rratio: float | None = None


@dataclass
class JobPart:
    ref: str
    value: str
    package: str
    x: float          # pick point = centre of the pads' bounding box, job frame
    y: float
    rot: float        # CCW seen from this side, (-180, 180]
    pads: list[JobPad]
    origin: Point     # footprint origin, job frame (usually the same point)
    footprint: Footprint = field(repr=False)
    dnp: bool = False  # do not populate: written with "skip": true

    @property
    def key(self) -> str:
        return self.footprint.key

    @property
    def pad_center(self) -> Point:
        return self.x, self.y

    @property
    def origin_offset(self) -> float:
        return ((self.origin[0] - self.x) ** 2 + (self.origin[1] - self.y) ** 2) ** 0.5


@dataclass
class Plate:
    number: int                       # 1 = top, 2 = bottom
    side: str
    frame: Frame
    outline: list[Point]              # job frame
    holes: list[list[Point]]
    parts: list[JobPart]
    skipped: list[tuple[Footprint, str]]

    def contains(self, x: float, y: float) -> bool:
        """True if job-frame point (x, y) is on the board (inside the outline, not in a cut-out)."""
        from .geometry import point_in_polygon
        return point_in_polygon(x, y, self.outline) and not any(point_in_polygon(x, y, h) for h in self.holes)

    @property
    def placed_parts(self) -> list[JobPart]:
        return [p for p in self.parts if not p.dnp]

    @property
    def title(self) -> str:
        return f"Plate {self.number} · {self.side.capitalize()}"

    @property
    def width(self) -> float:
        return self.frame.width

    @property
    def height(self) -> float:
        return self.frame.height

    def package_counts(self) -> dict[str, int]:
        return dict(sorted(Counter(p.package for p in self.placed_parts).items()))

    def skipped_counts(self) -> dict[str, int]:
        return dict(Counter(reason for _, reason in self.skipped))


def skip_reason(fp: Footprint) -> str | None:
    """Why a footprint isn't placed, or None if it is."""
    if fp.board_only:
        return "board-only"
    if fp.exclude_from_pos:
        return "excluded from position files"
    if fp.mount == "through_hole":
        return "through-hole"
    if fp.mount != "smd":
        return "not marked SMD"
    if not fp.copper_pads:
        return "no copper pads"
    return None


def build_plate(board: Board, side: str) -> Plate:
    frame = Frame.for_board(board, side)
    parts: list[JobPart] = []
    skipped: list[tuple[Footprint, str]] = []

    for fp in board.on_side(side):
        reason = skip_reason(fp)
        if reason:
            skipped.append((fp, reason))
            continue
        pads = []
        for p in fp.copper_pads:
            px, py = frame.point(p.x, p.y)
            pads.append(JobPad(p.number, p.shape, px, py, frame.angle(p.angle), p.w, p.h, p.roundrect_rratio))
        x, y = frame.point(*fp.pad_center())
        parts.append(JobPart(
            ref=fp.ref, value=fp.value, package=fp.package,
            x=x, y=y, rot=frame.angle(fp.rot), pads=pads,
            origin=frame.point(fp.x, fp.y), footprint=fp, dnp=fp.dnp,
        ))

    o = board.outline
    return Plate(
        number=1 if side == "top" else 2, side=side, frame=frame,
        outline=[frame.point(x, y) for x, y in o.outer],
        holes=[[frame.point(x, y) for x, y in h] for h in o.holes],
        parts=parts, skipped=skipped,
    )


def build_plates(board: Board) -> list[Plate]:
    return [build_plate(board, "top"), build_plate(board, "bottom")]
