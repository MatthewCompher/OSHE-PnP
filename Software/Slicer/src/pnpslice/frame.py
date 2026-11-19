"""KiCad coordinates -> job frame, for one side ("plate").

Job frame (JOB_FORMAT.md): millimetres, origin at the outline's lower-left
corner, +X right, +Y up, *as seen looking at the side being placed*. Angles
are counter-clockwise positive as seen from that side.

Top side, looking down at the board:
    x_job = x - min_x        y_job = max_y - y        (KiCad's Y points down)
    angle_job = angle_kicad

Bottom side, board flipped over left-to-right, looking at its underside:
    x_job = max_x - x        y_job = max_y - y
    angle_job = 180 - angle_kicad

Why 180 - angle on the bottom: when KiCad flips a footprint to B.Cu it stores
the footprint's local coordinates mirrored in Y (pin 1 of a SOIC moves from
local (-2.475, -1.905) to (-2.475, +1.905)). Seen from below, the part is
the library footprint (as you'd see it looking at the part) rotated by
180 - angle. tests/test_frame.py checks this for every pad on the test board.
"""

from __future__ import annotations

from dataclasses import dataclass

from .board import Board
from .geometry import Point

SIDES = ("top", "bottom")


def normalize_angle(a: float) -> float:
    """Wrap to (-180, 180] and tidy floating-point noise."""
    a = round(a, 6) % 360.0
    if a > 180.0:
        a -= 360.0
    return 0.0 if a == -0.0 else a


@dataclass(frozen=True)
class Frame:
    side: str
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @classmethod
    def for_board(cls, board: Board, side: str) -> "Frame":
        if side not in SIDES:
            raise ValueError(f"side must be 'top' or 'bottom', not {side!r}")
        x0, y0, x1, y1 = board.outline.bbox
        return cls(side, x0, y0, x1, y1)

    @property
    def mirrored(self) -> bool:
        return self.side == "bottom"

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def origin_kicad(self) -> Point:
        """Where the job origin (0, 0) is, in KiCad coordinates."""
        return (self.max_x if self.mirrored else self.min_x), self.max_y

    def point(self, x: float, y: float) -> Point:
        """KiCad board point -> job frame."""
        jx = (self.max_x - x) if self.mirrored else (x - self.min_x)
        return _tidy(jx), _tidy(self.max_y - y)

    def angle(self, kicad_angle: float) -> float:
        """KiCad orientation (CCW seen from the top) -> job angle (CCW seen from this side)."""
        return normalize_angle(180.0 - kicad_angle if self.mirrored else kicad_angle)

    def to_kicad(self, jx: float, jy: float) -> Point:
        """Job frame -> KiCad board point (inverse of ``point``)."""
        x = (self.max_x - jx) if self.mirrored else (jx + self.min_x)
        return x, self.max_y - jy


def _tidy(v: float) -> float:
    v = round(v, 6)
    return 0.0 if v == 0 else v