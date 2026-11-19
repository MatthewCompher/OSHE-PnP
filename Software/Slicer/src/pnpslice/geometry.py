"""Small 2D helpers. All coordinates in mm.

KiCad stores board coordinates with +Y pointing *down* the screen and angles
counter-clockwise *as seen on screen*. ``kicad_rotate`` reproduces KiCad's own
RotatePoint() so that local footprint coordinates land exactly where pcbnew
(and its Gerber export) puts them.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

Point = tuple[float, float]


def kicad_rotate(x: float, y: float, angle_deg: float) -> Point:
    """Rotate (x, y) by ``angle_deg`` CCW-on-screen in KiCad's Y-down frame."""
    if angle_deg == 0:
        return x, y
    a = math.radians(angle_deg)
    # Snap exact quarter turns so 90° rotations don't pick up 1e-17 noise.
    c, s = math.cos(a), math.sin(a)
    if abs(c) < 1e-12:
        c = 0.0
    if abs(s) < 1e-12:
        s = 0.0
    return x * c + y * s, -x * s + y * c


def circle_from_3_points(p1: Point, p2: Point, p3: Point) -> tuple[Point, float]:
    (ax, ay), (bx, by), (cx, cy) = p1, p2, p3
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-12:
        raise ValueError("arc points are collinear")
    a2, b2, c2 = ax * ax + ay * ay, bx * bx + by * by, cx * cx + cy * cy
    ux = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
    uy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
    return (ux, uy), math.hypot(ax - ux, ay - uy)


def _arc_steps(radius: float, sweep: float, tol: float, max_step_deg: float) -> int:
    max_step = math.radians(max_step_deg)
    if radius > tol:
        max_step = min(max_step, 2 * math.acos(1 - tol / radius))
    return max(1, math.ceil(abs(sweep) / max_step))


def arc_points(start: Point, mid: Point, end: Point, tol: float = 0.005, max_step_deg: float = 5.0) -> list[Point]:
    """Polyline through a 3-point arc, including both endpoints exactly."""
    try:
        (cx, cy), r = circle_from_3_points(start, mid, end)
    except ValueError:
        return [start, end]
    a0 = math.atan2(start[1] - cy, start[0] - cx)
    am = math.atan2(mid[1] - cy, mid[0] - cx)
    a1 = math.atan2(end[1] - cy, end[0] - cx)
    two_pi = 2 * math.pi
    sweep = (a1 - a0) % two_pi
    if (am - a0) % two_pi > sweep:  # mid not on the positive sweep -> go the other way
        sweep -= two_pi
    n = _arc_steps(r, sweep, tol, max_step_deg)
    pts = [start]
    for i in range(1, n):
        a = a0 + sweep * i / n
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts.append(end)
    return pts


def circle_points(center: Point, radius: float, tol: float = 0.005, max_step_deg: float = 5.0) -> list[Point]:
    """Closed polygon approximating a circle (first point not repeated)."""
    n = max(8, _arc_steps(radius, 2 * math.pi, tol, max_step_deg))
    cx, cy = center
    return [(cx + radius * math.cos(2 * math.pi * i / n), cy + radius * math.sin(2 * math.pi * i / n)) for i in range(n)]


def bezier_points(p0: Point, p1: Point, p2: Point, p3: Point, n: int = 32) -> list[Point]:
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((
            u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
            u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
        ))
    return out


def polygon_area(pts: Sequence[Point]) -> float:
    """Signed shoelace area (sign depends on winding and on the Y direction)."""
    s = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return s / 2


def point_in_polygon(x: float, y: float, pts: Sequence[Point]) -> bool:
    """Even-odd ray cast. Points exactly on an edge may go either way."""
    inside = False
    n = len(pts)
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y):
            xc = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < xc:
                inside = not inside
        j = i
    return inside


def bbox(points: Iterable[Point]) -> tuple[float, float, float, float]:
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])