"""Compare the board model's pad centres with KiCad's copper Gerbers.

If every SMD pad we compute lands on a pad flash in the Gerber for that side,
the parser, the footprint rotation maths and the bottom-side handling all
agree with KiCad itself.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

from .board import Board
from .gerber import GerberFile, read_gerber

GRID = 0.01  # mm bucket size for matching


@dataclass
class SideCheck:
    side: str
    gerber_path: str
    pads_checked: int = 0
    matched: int = 0
    max_error: float = 0.0
    offset_used: tuple[float, float] = (0.0, 0.0)
    missing: list[tuple[str, str, float, float]] = field(default_factory=list)  # (ref, pad, x, y) KiCad frame
    unexpected: list[tuple[float, float]] = field(default_factory=list)         # Gerber flashes with no pad

    @property
    def ok(self) -> bool:
        return self.pads_checked > 0 and not self.missing and not self.unexpected


def find_copper_gerbers(directory: str) -> dict[str, str]:
    """{'top': path, 'bottom': path} found by each file's %TF.FileFunction."""
    found: dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(directory, "*"))):
        if not os.path.isfile(path) or os.path.getsize(path) > 200_000_000:
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                head = fh.read(4000)
        except OSError:
            continue
        if "%TF.FileFunction,Copper," not in head:
            continue
        line = head.split("%TF.FileFunction,Copper,", 1)[1].split("*", 1)[0]
        if line.endswith(",Top"):
            found["top"] = path
        elif line.endswith(",Bot"):
            found["bottom"] = path
    return found


def find_gerber_dir(start: str) -> str | None:
    """``start`` itself, or the first folder inside it, that holds copper Gerbers.

    ``start`` may be a folder or a file (then its folder is used). Hidden
    folders such as KiCad's ``.history`` are skipped.
    """
    top = start if os.path.isdir(start) else os.path.dirname(os.path.abspath(start))
    for folder, dirs, _ in os.walk(top):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        if find_copper_gerbers(folder):
            return folder
    return None


def _match(pads, flashes, offset, tol):
    buckets: dict[tuple[int, int], list[int]] = {}
    for i, f in enumerate(flashes):
        buckets.setdefault((round(f[0] / GRID), round(f[1] / GRID)), []).append(i)
    used = set()
    missing, max_err = [], 0.0
    ox, oy = offset
    for ref, num, x, y in pads:
        gx, gy = x - ox, -(y - oy)  # KiCad frame -> Gerber frame
        kx, ky = round(gx / GRID), round(gy / GRID)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i in buckets.get((kx + dx, ky + dy), ()):
                    if i in used:
                        continue
                    d = ((flashes[i][0] - gx) ** 2 + (flashes[i][1] - gy) ** 2) ** 0.5
                    if d <= tol and (best is None or d < best[0]):
                        best = (d, i)
        if best is None:
            missing.append((ref, num, x, y))
        else:
            used.add(best[1])
            max_err = max(max_err, best[0])
    unexpected = [flashes[i] for i in range(len(flashes)) if i not in used]
    return missing, unexpected, max_err


def check_side(board: Board, gerber: GerberFile, side: str, tol: float = 0.002) -> SideCheck:
    layer = "F.Cu" if side == "top" else "B.Cu"
    pads = [(fp.ref, p.number, p.x, p.y)
            for fp in board.footprints for p in fp.pads
            if p.kind == "smd" and layer in p.layers]
    flashes = [(f.x, f.y) for f in gerber.flashes if f.function.startswith("SMDPad")]

    result = SideCheck(side=side, gerber_path=gerber.path, pads_checked=len(pads))
    attempts = [(0.0, 0.0)]
    if board.aux_origin != (0.0, 0.0):
        attempts.append(board.aux_origin)  # Gerbers plotted with "use drill/place file origin"
    best = None
    for off in attempts:
        missing, unexpected, err = _match(pads, flashes, off, tol)
        if best is None or len(missing) < len(best[1]):
            best = (off, missing, unexpected, err)
    off, missing, unexpected, err = best
    result.offset_used = off
    result.missing = missing
    result.unexpected = unexpected
    result.matched = len(pads) - len(missing)
    result.max_error = err
    return result


def check_against_gerbers(board: Board, directory: str, tol: float = 0.002) -> list[SideCheck]:
    files = find_copper_gerbers(directory)
    if not files:
        raise FileNotFoundError(f"no copper Gerbers (with %TF.FileFunction) found in {directory}")
    return [check_side(board, read_gerber(files[s]), s, tol) for s in ("top", "bottom") if s in files]