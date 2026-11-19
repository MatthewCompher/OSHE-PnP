"""Write and check oshe-pnp-job/1 files, following JOB_FORMAT.md (v1 draft 2026-11-09).

One file per board side. Board coordinates in mm, angles in degrees, file
order = placement order. Feeder and nozzle are left out ("missing = assigned
at the machine"). Do-not-populate parts are kept with "skip": true. The
optional "source" block records the generator and input file.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import os
import re

from . import __version__
from .board import Board
from .slicer import SliceResult

FORMAT = "oshe-pnp-job/1"
SHAPES = ("rect", "roundrect", "oval", "circle")


class JobError(ValueError):
    pass


def _r(v: float, nd: int = 4) -> float:
    v = round(float(v), nd)
    return 0.0 if v == 0 else v


def _from_origin(points: list[list[float]]) -> list[list[float]]:
    """Same polygon, listed starting from the corner nearest (0, 0)."""
    k = min(range(len(points)), key=lambda i: points[i][0] + points[i][1])
    return points[k:] + points[:k]


def alignment_entry(pick) -> dict:
    """One alignment pad: centre, shape and size, as vision should look for it."""
    c = pick.cand
    e = {"name": pick.name, "x": _r(c.x), "y": _r(c.y)}
    shape = c.job_shape
    if shape == "circle":
        e.update(shape="circle", d=_r(c.w, 3))
    else:
        e.update(shape=shape, w=_r(c.w, 3), h=_r(c.h, 3), rot=_r(c.angle, 3))
        if shape == "roundrect":
            e["corner_r"] = _r(min(c.w, c.h) * c.roundrect_rratio, 3)  # extra field: corner radius
    e["ref"] = c.ref          # optional in the spec: which footprint and pad this is
    e["pad"] = c.pad
    return e


def default_filename(board: Board, side: str) -> str:
    return f"{board.name}-{side}.job.json"


def build_job(board: Board, result: SliceResult, created: _dt.datetime | None = None) -> dict:
    """The job file as a dict. Raises JobError if the slice has errors."""
    if result.errors:
        raise JobError("can't write a job file while there are errors:\n- " +
                       "\n- ".join(i.message for i in result.errors))
    if not result.placements:
        raise JobError("nothing to place on this side")
    plate = result.plate
    created = created or _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)

    placements = []
    for pl in result.placements:
        p = pl.part
        entry = {
            "ref": pl.ref,
            "value": p.value,
            "package": p.package,
            "x": _r(p.x),
            "y": _r(p.y),
            "rot": _r(p.rot, 3),
            "height_mm": _r(pl.height, 3),
        }
        if pl.skip:
            entry["skip"] = True
        if pl.ref != p.ref:
            entry["kicad_ref"] = p.ref  # extra field: the name in KiCad, for auto-numbered parts
        placements.append(entry)

    return {
        "format": FORMAT,
        "source": {
            "generator": f"pnpslice {__version__}",
            "inputs": [os.path.basename(board.path)],
            "date": created.isoformat(),
        },
        "board": {
            "name": board.name,
            "side": plate.side,
            "outline_mm": _from_origin([[_r(x), _r(y)] for x, y in plate.outline]),
            "thickness_mm": _r(board.thickness, 3),
        },
        "alignment": [alignment_entry(a) for a in result.alignment],
        "placements": placements,
    }


def validate_job(job: dict) -> list[str]:
    """Problems with a job dict per JOB_FORMAT.md, as readable strings. Empty list = valid."""
    errs: list[str] = []

    def num(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)

    def text(v):
        return isinstance(v, str)

    if job.get("format") != FORMAT:
        errs.append(f"format: expected '{FORMAT}', got {job.get('format')!r}")
    if "source" in job and not isinstance(job["source"], dict):
        errs.append("source: must be an object if present")

    b = job.get("board")
    if not isinstance(b, dict):
        errs.append("board: missing")
        b = {}
    if not text(b.get("name")) or not b.get("name"):
        errs.append("board.name: missing")
    if b.get("side") not in ("top", "bottom"):
        errs.append("board.side: must be 'top' or 'bottom'")
    outline = b.get("outline_mm")
    if not (isinstance(outline, list) and len(outline) >= 3 and
            all(isinstance(p, list) and len(p) == 2 and num(p[0]) and num(p[1]) for p in outline)):
        errs.append("board.outline_mm: needs 3 or more [x, y] points")
        outline = None
    else:
        if outline[0] == outline[-1]:
            errs.append("board.outline_mm: must not repeat the first point at the end")
        if abs(min(p[0] for p in outline)) > 1e-6 or abs(min(p[1] for p in outline)) > 1e-6:
            errs.append("board.outline_mm: lower-left of the bounding box must be (0, 0)")
    if not (num(b.get("thickness_mm")) and b["thickness_mm"] > 0):
        errs.append("board.thickness_mm: must be a positive number")

    al = job.get("alignment")
    if not isinstance(al, list):
        errs.append("alignment: missing")
        al = []
    elif not 2 <= len(al) <= 4:
        errs.append(f"alignment: needs 2 to 4 pads, has {len(al)}")
    names = set()
    for i, a in enumerate(al):
        where = f"alignment[{i}]"
        if not isinstance(a, dict):
            errs.append(f"{where}: not an object")
            continue
        if not text(a.get("name")) or not a["name"] or a["name"] in names:
            errs.append(f"{where}.name: missing or repeated")
        names.add(a.get("name"))
        if not (num(a.get("x")) and num(a.get("y"))):
            errs.append(f"{where}: x and y must be numbers")
        shape = a.get("shape")
        if shape == "circle":
            if not (num(a.get("d")) and a["d"] > 0):
                errs.append(f"{where}.d: must be a positive number")
        elif shape in ("rect", "roundrect", "oval"):
            if not all(num(a.get(k)) and a[k] > 0 for k in ("w", "h")):
                errs.append(f"{where}: w and h must be positive numbers")
        else:
            errs.append(f"{where}.shape: must be one of {', '.join(SHAPES)}")
        if "rot" in a and not num(a["rot"]):
            errs.append(f"{where}.rot: must be a number")
        for k in ("ref", "pad"):
            if k in a and not text(a[k]):
                errs.append(f"{where}.{k}: must be a string")

    pl = job.get("placements")
    if not isinstance(pl, list) or not pl:
        errs.append("placements: missing or empty")
        pl = []
    seen = set()
    inside = None
    if outline:
        from .geometry import point_in_polygon

        def inside(x, y):
            if point_in_polygon(x, y, outline):
                return True
            # on the edge counts as inside
            n = len(outline)
            for k in range(n):
                (x1, y1), (x2, y2) = outline[k], outline[(k + 1) % n]
                dx, dy = x2 - x1, y2 - y1
                t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / ((dx * dx + dy * dy) or 1)))
                if math.hypot(x - (x1 + t * dx), y - (y1 + t * dy)) < 1e-6:
                    return True
            return False

        for i, a in enumerate(al):
            if isinstance(a, dict) and num(a.get("x")) and num(a.get("y")) and not inside(a["x"], a["y"]):
                errs.append(f"alignment[{i}]: ({a['x']}, {a['y']}) is outside the board")
    for i, p in enumerate(pl):
        where = f"placements[{i}]"
        if not isinstance(p, dict):
            errs.append(f"{where}: not an object")
            continue
        ref = p.get("ref")
        if not text(ref) or not ref:
            errs.append(f"{where}.ref: missing")
        elif ref in seen:
            errs.append(f"{where}.ref: '{ref}' is used more than once")
        else:
            seen.add(ref)
        for k in ("value", "package"):
            if not text(p.get(k)):
                errs.append(f"{where}.{k}: must be a string")
        for k in ("x", "y", "rot"):
            if not num(p.get(k)):
                errs.append(f"{where}.{k}: must be a number")
        if not (num(p.get("height_mm")) and p["height_mm"] > 0):
            errs.append(f"{where}.height_mm: must be a positive number")
        if inside and num(p.get("x")) and num(p.get("y")) and not inside(p["x"], p["y"]):
            errs.append(f"{where}: ({p['x']}, {p['y']}) is outside the board outline")
        if num(p.get("rot")) and not -180 < p["rot"] <= 180:
            errs.append(f"{where}.rot: must be in (-180, 180]")
        for k in ("feeder", "nozzle"):
            if k in p and not text(p[k]):
                errs.append(f"{where}.{k}: must be a string")
        if "skip" in p and not isinstance(p["skip"], bool):
            errs.append(f"{where}.skip: must be true or false")
    return errs


def write_job(path: str, job: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(dumps(job))
    os.replace(tmp, path)


def dumps(job: dict) -> str:
    """JSON with one placement per line: easy to read and to diff."""
    head = {k: v for k, v in job.items() if k not in ("alignment", "placements")}
    text = json.dumps(head, indent=2, ensure_ascii=False)[:-2]  # drop the closing "\n}"
    # [x, y] pairs on one line each
    text = re.sub(r"\[\s+(-?[0-9.eE+-]+),\s+(-?[0-9.eE+-]+)\s+\]", r"[\1, \2]", text)
    parts = [text]
    for key in ("alignment", "placements"):
        items = job.get(key, [])
        if not items:
            parts.append(f',\n  "{key}": []')
        else:
            rows = ",\n".join("    " + json.dumps(it, ensure_ascii=False) for it in items)
            parts.append(f',\n  "{key}": [\n{rows}\n  ]')
    return "".join(parts) + "\n}\n"