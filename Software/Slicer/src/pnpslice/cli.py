"""Command line: ``pnpslice info BOARD`` and ``pnpslice check-gerbers BOARD DIR``."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .board import SIDES, Board, BoardError, load_board
from .crosscheck import check_against_gerbers
from .gcode import write_dryrun_gcode
from .job import build_job, default_filename, write_job
from .plate import ORIGIN_OFFSET_WARN_MM, build_plates
from .project import ProjectSettings
from .slicer import slice_plate

def board_summary(board: Board) -> dict:
    o = board.outline
    x0, y0, x1, y1 = o.bbox
    plates = []
    for plate in build_plates(board):
        offsets = [{"ref": p.ref, "package": p.package, "offset_mm": round(p.origin_offset, 3)}
                   for p in plate.parts if p.origin_offset > ORIGIN_OFFSET_WARN_MM]
        plates.append({
            "plate": plate.number,
            "side": plate.side,
            "parts": len(plate.parts),
            "packages": plate.package_counts(),
            "skipped": plate.skipped_counts(),
            "origin_not_at_pad_centre": offsets,
            "job_origin_in_kicad": list(plate.frame.origin_kicad),
        })
    return {
        "name": board.name,
        "file": board.path,
        "kicad": board.generator_version,
        "file_version": board.file_version,
        "thickness_mm": board.thickness,
        "outline": {
            "width_mm": round(o.width, 4),
            "height_mm": round(o.height, 4),
            "rectangle": o.is_rectangle,
            "vertices": len(o.outer),
            "cutouts": len(o.holes),
            "kicad_min_corner": [x0, y0],
            "kicad_max_corner": [x1, y1],
        },
        "plates": plates,
        "duplicate_refs": board.duplicate_refs(),
        "unannotated_refs": board.unannotated_refs(),
        "warnings": board.warnings,
    }


def _print_summary(s: dict) -> None:
    o = s["outline"]
    print(f"{s['name']}  (KiCad {s['kicad'] or '?'}, file format {s['file_version']})")
    shape = "rectangle" if o["rectangle"] else f"{o['vertices']}-point outline"
    print(f"  Outline   {o['width_mm']:.2f} x {o['height_mm']:.2f} mm {shape}, "
          f"{o['cutouts']} cut-out(s), {s['thickness_mm']} mm thick")
    (ax, ay), (bx, by) = o["kicad_min_corner"], o["kicad_max_corner"]
    print(f"  KiCad bbox ({ax:.3f}, {ay:.3f}) .. ({bx:.3f}, {by:.3f})")
    for p in s["plates"]:
        ox, oy = p["job_origin_in_kicad"]
        print(f"\n  Plate {p['plate']} - {p['side']}: {p['parts']} parts   "
              f"(job origin = KiCad ({ox:.3f}, {oy:.3f}){', mirrored' if p['side'] == 'bottom' else ''})")
        for pkg, n in p["packages"].items():
            print(f"    {n:4d} x {pkg}")
        for why, n in p["skipped"].items():
            print(f"    skipped {n} ({why})")
        if p["origin_not_at_pad_centre"]:
            print(f"    note: {len(p['origin_not_at_pad_centre'])} part(s) have their footprint origin "
                  f"more than {ORIGIN_OFFSET_WARN_MM} mm from their pad centre")

    problems = []
    if s["duplicate_refs"]:
        total = sum(s["duplicate_refs"].values())
        listing = ", ".join(f"{r} x{n}" for r, n in s["duplicate_refs"].items())
        problems.append(f"{total} parts share {len(s['duplicate_refs'])} reference(s): {listing}.\n"
                        "      Give every part its own reference (in the PCB editor: Tools > "
                        "Geographical Reannotate, or annotate the schematic and update the PCB).")
    if s["unannotated_refs"]:
        problems.append("unnumbered references: " + ", ".join(s["unannotated_refs"]))
    if problems or s["warnings"]:
        print("\n  Problems")
        for p in problems:
            print(f"    !! {p}")
        for w in s["warnings"]:
            print(f"    warning: {w}")
    else:
        print("\n  No problems found.")


def cmd_info(args) -> int:
    board = load_board(args.board)
    s = board_summary(board)
    if args.json:
        json.dump(s, sys.stdout, indent=2)
        print()
    else:
        _print_summary(s)
    return 1 if s["duplicate_refs"] or s["unannotated_refs"] else 0


def cmd_check_gerbers(args) -> int:
    board = load_board(args.board)
    results = check_against_gerbers(board, args.gerber_dir, tol=args.tol)
    ok = True
    for r in results:
        status = "OK " if r.ok else "BAD"
        print(f"[{status}] {r.side:6s} {r.matched}/{r.pads_checked} SMD pads match "
              f"{r.gerber_path.split('/')[-1].split(chr(92))[-1]} "
              f"(worst error {r.max_error * 1000:.2f} um)")
        if r.offset_used != (0.0, 0.0):
            print(f"       Gerbers use the drill/place origin {r.offset_used}")
        for ref, num, x, y in r.missing[:10]:
            print(f"       no Gerber pad for {ref} pad {num or '?'} at KiCad ({x:.4f}, {y:.4f})")
        if len(r.missing) > 10:
            print(f"       ... and {len(r.missing) - 10} more")
        if r.unexpected:
            print(f"       {len(r.unexpected)} Gerber pad flash(es) with no matching pad in the board file")
        ok &= r.ok
    sides = {r.side for r in results}
    for s in SIDES:
        if s not in sides:
            print(f"[ - ] {s:6s} no copper Gerber found for this side")
    return 0 if ok else 1


def cmd_slice(args) -> int:
    board = load_board(args.board)
    settings = ProjectSettings.load(args.board)
    if args.auto_number:
        settings.auto_number = True
    out_dir = args.out or os.path.dirname(os.path.abspath(args.board))
    sides = SIDES if args.side == "both" else (args.side,)
    status = 0
    for plate in build_plates(board):
        if plate.side not in sides:
            continue
        result = slice_plate(board, plate, settings)
        print(f"{plate.title.replace(chr(0xb7), '-')}: {len(result.placements)} placements")
        for issue in result.issues:
            print(f"  {'!!' if issue.is_error else 'warning:'} {issue.message}")
        if not result.ok:
            print("  -> not written")
            status = 1
            continue
        job = build_job(board, result)
        path = os.path.join(out_dir, default_filename(board, plate.side))
        write_job(path, job)
        print(f"  -> {path}")
        if args.gcode:
            print(f"  -> {write_dryrun_gcode(path, job)}")
    return status


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pnpslice", description="Pick-and-place slicer for KiCad boards")
    ap.add_argument("--version", action="version", version=f"pnpslice {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("info", help="summarise a .kicad_pcb: outline, plates (sides), parts, problems")
    p.add_argument("board")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("check-gerbers", help="check computed pad centres against the copper Gerbers")
    p.add_argument("board")
    p.add_argument("gerber_dir")
    p.add_argument("--tol", type=float, default=0.002, help="match tolerance in mm (default 0.002)")
    p.set_defaults(func=cmd_check_gerbers)

    p = sub.add_parser("slice", help="write the job file(s) for one or both sides")
    p.add_argument("board")
    p.add_argument("--side", choices=["top", "bottom", "both"], default="both")
    p.add_argument("-o", "--out", help="folder for the job files (default: next to the board)")
    p.add_argument("--auto-number", action="store_true",
                   help="number duplicate/unnumbered references automatically (job file only)")
    p.add_argument("--gcode", action="store_true",
                   help="also write <job>_dryrun.gcode (the placements as G-code, board coordinates)")
    p.set_defaults(func=cmd_slice)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (BoardError, FileNotFoundError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())