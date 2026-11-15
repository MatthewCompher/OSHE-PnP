"""Choosing the alignment pads for a plate (JOB_FORMAT.md "alignment").

Vision centres the camera on each alignment pad to find the board. A good pad:
  * is copper with a solder-mask opening on the side being placed (visible);
  * is *distinct*: JOB_FORMAT.md says no pad of similar shape and size within
    3 mm (the default here; it's a setting). Roughly: if the board can sit up
    to t mm off before alignment, look-alikes must be more than 2t away, or one
    could be nearer to where vision looks than the real pad is;
  * stays visible: fiducials and pads of parts that aren't placed in this job
    are never covered; pads of placed parts are covered from their step on,
    so later-placed parts are better (they matter for resume after a stop).
And the set of 2-4 pads should be spread as far apart as possible and not in a line.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from .board import Board, Footprint
from .frame import Frame
from .plate import Plate

DEFAULT_COUNT = 3
DEFAULT_CLEARANCE_MM = 3.0   # JOB_FORMAT.md: no similar pad within 3 mm
SIZE_TOLERANCE = 0.25        # pads within 25 % in both dimensions count as look-alikes
NAMES = "ABCD"
SHORTLIST_PER_CORNER = 6


@dataclass
class AlignCandidate:
    key: str                 # stable id: "<footprint uuid>/<pad number>"
    ref: str
    pad: str
    package: str
    x: float                 # job frame
    y: float
    angle: float             # job frame
    shape: str               # KiCad pad shape
    w: float
    h: float
    roundrect_rratio: float | None
    fiducial: bool
    covered_at: int | None   # placement step that covers this pad (None = never in this job)
    clearance: float         # mm to the nearest look-alike pad (inf if none)
    nearest_any: float       # mm to the nearest other pad of any kind

    def distinct(self, min_clearance: float) -> bool:
        return self.clearance >= min_clearance

    @property
    def shape_class(self) -> str:
        """Look-alike class: circle / oval / rect (roundrect counts as rect)."""
        return _shape_class(self.shape, self.w, self.h)

    @property
    def job_shape(self) -> str:
        """Shape name for the job file: rect, roundrect, oval or circle."""
        cls = self.shape_class
        if cls == "rect" and self.shape == "roundrect" and self.roundrect_rratio:
            return "roundrect"
        return cls

    def label(self) -> str:
        return f"{self.ref} pad {self.pad}" if self.pad else self.ref

    def describe(self, min_clearance: float) -> str:
        size = f"⌀{self.w:g}" if self.shape_class == "circle" else f"{self.w:g}×{self.h:g}"
        clr = "no look-alike" if not math.isfinite(self.clearance) else f"look-alike {self.clearance:.2f} mm"
        if self.fiducial:
            vis = "fiducial"
        elif self.covered_at is None:
            vis = "stays visible"
        else:
            vis = f"covered at #{self.covered_at}"
        warn = "" if self.distinct(min_clearance) else " ⚠ too close"
        return f"{self.label()} · {size} · {clr} · {vis}{warn}"


@dataclass
class AlignPick:
    name: str                # "A", "B", ...
    cand: AlignCandidate


def _shape_class(shape: str, w: float, h: float) -> str:
    if shape == "circle" or (shape == "oval" and abs(w - h) < 1e-6):
        return "circle"
    if shape == "oval":
        return "oval"
    return "rect"            # rect, roundrect, chamfered_rect, trapezoid, custom


def _alike(a: tuple, b: tuple) -> bool:
    """a, b = (class, long side, short side)."""
    if a[0] != b[0]:
        return False
    return (abs(a[1] - b[1]) <= SIZE_TOLERANCE * max(a[1], b[1]) and
            abs(a[2] - b[2]) <= SIZE_TOLERANCE * max(a[2], b[2]))


def is_fiducial(fp: Footprint) -> bool:
    return "fiducial" in fp.lib_id.lower() or fp.ref.upper().startswith("FID")


def _visible_pads(board: Board, side: str):
    """(footprint, pad index, pad) for copper pads exposed on ``side``."""
    cu, mask = ("F.Cu", "F.Mask") if side == "top" else ("B.Cu", "B.Mask")
    for fp in board.footprints:
        for i, p in enumerate(fp.pads):
            if p.kind == "np_thru_hole" or cu not in p.layers or mask not in p.layers:
                continue
            yield fp, i, p


def candidates(board: Board, plate: Plate,
               in_job: dict[str, tuple[int, str]] | None = None) -> list[AlignCandidate]:
    """All visible pads on this plate's side, with their clearances.

    ``in_job`` maps footprint uuid -> (placement step, job reference) for the
    parts placed in this job: their pads get covered from that step on.
    """
    in_job = in_job or {}
    frame: Frame = plate.frame
    raw = list(_visible_pads(board, plate.side))
    pts = []
    for fp, i, p in raw:
        x, y = frame.point(p.x, p.y)
        cls = _shape_class(p.shape, p.w, p.h)
        pts.append((x, y, (cls, max(p.w, p.h), min(p.w, p.h))))

    # neighbour search on a grid
    cell = 2.0
    grid: dict[tuple[int, int], list[int]] = {}
    for idx, (x, y, _) in enumerate(pts):
        grid.setdefault((int(x // cell), int(y // cell)), []).append(idx)

    def nearest(idx: int, max_r: float = 12.0) -> tuple[float, float]:
        x, y, sig = pts[idx]
        best_alike = best_any = math.inf
        reach = int(math.ceil(max_r / cell))
        gx, gy = int(x // cell), int(y // cell)
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                for j in grid.get((gx + dx, gy + dy), ()):
                    if j == idx:
                        continue
                    d = math.hypot(pts[j][0] - x, pts[j][1] - y)
                    best_any = min(best_any, d)
                    if d < best_alike and _alike(sig, pts[j][2]):
                        best_alike = d
        return best_alike, best_any

    out = []
    for idx, (fp, i, p) in enumerate(raw):
        x, y, _ = pts[idx]
        alike, any_ = nearest(idx)
        number = p.number or f"#{i + 1}"
        step, job_ref = in_job.get(fp.uuid, (None, fp.ref)) if fp.uuid else (None, fp.ref)
        out.append(AlignCandidate(
            key=f"{fp.key}/{number}",
            ref=job_ref, pad=p.number, package=fp.package, x=x, y=y,
            angle=frame.angle(p.angle), shape=p.shape, w=p.w, h=p.h,
            roundrect_rratio=p.roundrect_rratio, fiducial=is_fiducial(fp),
            covered_at=step,
            clearance=alike, nearest_any=any_,
        ))
    return out


# ---------------------------------------------------------------------------
# choosing


def _quality(c: AlignCandidate, n_steps: int, min_clearance: float) -> float:
    if c.fiducial:
        vis = 1.2
    elif c.covered_at is None:
        vis = 1.0
    else:  # covered during the job: later is better
        vis = 0.4 + 0.5 * (c.covered_at / max(n_steps, 1))
    clr = min(1.0, (c.clearance if math.isfinite(c.clearance) else 4 * min_clearance) / (2 * min_clearance))
    return vis * clr


def _hull_area(points: list[tuple[float, float]]) -> float:
    pts = sorted(set(points))
    if len(pts) < 3:
        return 0.0

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return abs(sum(hull[i][0] * hull[(i + 1) % len(hull)][1] - hull[(i + 1) % len(hull)][0] * hull[i][1]
                   for i in range(len(hull)))) / 2


def spread(points: list[tuple[float, float]], width: float, height: float) -> float:
    """0..1: how well the points span the board (1 = as good as it gets)."""
    if len(points) < 2:
        return 0.0
    if len(points) == 2:
        return math.dist(*points) / math.hypot(width, height)
    best = 0.5 if len(points) == 3 else 1.0   # largest triangle in a rectangle is half of it
    return min(1.0, _hull_area(points) / (width * height * best))


def name_picks(cands: list[AlignCandidate]) -> list[AlignPick]:
    """A = nearest the origin, then counter-clockwise around the centre."""
    if not cands:
        return []
    first = min(cands, key=lambda c: (c.x + c.y, c.x))
    cx = sum(c.x for c in cands) / len(cands)
    cy = sum(c.y for c in cands) / len(cands)
    a0 = math.atan2(first.y - cy, first.x - cx)
    ordered = sorted(cands, key=lambda c: (math.atan2(c.y - cy, c.x - cx) - a0) % (2 * math.pi))
    return [AlignPick(NAMES[i], c) for i, c in enumerate(ordered)]


def auto_pick(cands: list[AlignCandidate], width: float, height: float, count: int = DEFAULT_COUNT,
              min_clearance: float = DEFAULT_CLEARANCE_MM, n_steps: int = 0) -> list[AlignCandidate]:
    """Best ``count`` pads: distinct ones if there are enough, spread out, good quality."""
    count = max(2, min(4, count))
    pool = [c for c in cands if c.distinct(min_clearance)]
    need = min_clearance
    while len(pool) < count and need > 0.2:
        # not enough distinct pads: relax step by step, so the most distinct ones win (caller warns)
        need *= 0.9
        pool = [c for c in cands if c.clearance >= need]
    if len(pool) < count:
        pool = list(cands)
    if len(pool) < 2:
        return pool
    count = min(count, len(pool))
    q = {c.key: _quality(c, n_steps, min_clearance) for c in pool}
    diag = math.hypot(width, height)

    shortlist: dict[str, AlignCandidate] = {}
    for corner in ((0, 0), (width, 0), (width, height), (0, height)):
        ranked = sorted(pool, key=lambda c: math.dist((c.x, c.y), corner) / diag - 0.35 * q[c.key])
        for c in ranked[:SHORTLIST_PER_CORNER]:
            shortlist[c.key] = c
    short = list(shortlist.values())

    best, best_score = None, -1.0
    for combo in itertools.combinations(short, count):
        s = spread([(c.x, c.y) for c in combo], width, height)
        if count >= 3 and s < 0.08:   # (nearly) in a line: can't fix rotation well
            continue
        score = s * (sum(q[c.key] for c in combo) / count)
        if score > best_score:
            best, best_score = list(combo), score
    if best is None:  # everything nearly collinear: take the widest pair
        best = list(max(itertools.combinations(short, 2), key=lambda p: math.dist((p[0].x, p[0].y),
                                                                                    (p[1].x, p[1].y))))
    return best