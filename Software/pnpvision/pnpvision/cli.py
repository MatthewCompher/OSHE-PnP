"""python -m pnpvision <command>   (run from the project folder)"""
import argparse
import json
import time
from functools import partial

import cv2

from . import config as C
from . import machine_state as MS
from .camera import Camera
from .datum import DatumGeometry, measure_datum, to_datum_xy, to_machine_xy
import numpy as np
from .detect import find_circle
from .lens import LensModel
from .moonraker import Moonraker
from .motion import MotionMap
from .servo import calibrate_motion, center_on
from .lighting import make_light, grab_lit
from .upcam import UpCam
from .eventlog import EventLog


def open_cam(cfg, role):
    c = cfg["cameras"][role]
    lens = LensModel(C.rel(cfg, c["calibration"]))
    cam = Camera(c["device"], c["width"], c["height"], c["fps"],
                 exposure=c.get("exposure", 0), name=role).start()
    return cam, lens


def make_mr(cfg):
    m = cfg["moonraker"]
    mc = cfg["machine"]
    return Moonraker(m["url"], m["feedrate_mm_min"], mc["x_range"], mc["y_range"], mc["z_range"])


def cmd_check_lens(cfg, a):
    for role in (["up", "down"] if a.cam == "both" else [a.cam]):
        lens = LensModel(C.rel(cfg, cfg["cameras"][role]["calibration"]))
        print(role, json.dumps(lens.health(), indent=2))


def cmd_snapshot(cfg, a):
    cam, lens = open_cam(cfg, a.cam)
    try:
        if a.cam == "up" and a.lit:
            lc = cfg["lighting"]["up"]
            f = grab_lit(cam, make_light(lc, make_mr(cfg)), None, lc["settle_s"], lc["ambient_subtract"])
        else:
            f = cam.fresh()
        cv2.imwrite(f"{a.out}_raw.png", f)
        cv2.imwrite(f"{a.out}_undist.png", lens.undistort(f))
        print("wrote", f"{a.out}_raw.png", f"{a.out}_undist.png")
    finally:
        cam.stop()


def cmd_calibrate_motion(cfg, a):
    mr = make_mr(cfg)
    cam, lens = open_cam(cfg, a.cam)
    settle = cfg["moonraker"]["settle_s"]
    try:
        grab = lambda: lens.undistort(cam.fresh(settle_s=settle))
        locate = partial(find_circle, r_min_px=a.rmin, r_max_px=a.rmax)
        moving = "camera" if a.cam == "down" else "target"
        mmap = calibrate_motion(grab, locate, mr.move_rel, a.step, moving)
        print(json.dumps(mmap.describe(), indent=2))
        mmap.save(C.rel(cfg, cfg["cameras"][a.cam]["motion_map"]))
        if a.cam == "up" and a.find_center:
            target = (lens.newK[0, 2], lens.newK[1, 2])
            res = center_on(grab, locate, mr.move_rel, mmap, target)
            print("centering:", res)
            if res["converged"]:
                x, y, _ = mr.position()
                MS.save(C.rel(cfg, "calibration/machine.json"), up_cam_xy_mm=[x, y])
                print("up camera optical axis at machine XY", (x, y))
    finally:
        cam.stop()


def cmd_calibrate_offset(cfg, a):
    """Stamp method: nozzle XY over a dark dot -> record; centre down camera on the same dot -> record."""
    mr = make_mr(cfg)
    cam, lens = open_cam(cfg, "down")
    settle = cfg["moonraker"]["settle_s"]
    try:
        mmap = MotionMap.load(C.rel(cfg, cfg["cameras"]["down"]["motion_map"]))
        input("Jog the NOZZLE directly over the centre of a dark dot (marker dot on a white label "
              "stuck to the bed). Press Enter...")
        x1, y1, _ = mr.position()
        input("Now raise Z to the down camera's focus height and jog roughly so the dot is in view. "
              "Press Enter...")
        grab = lambda: lens.undistort(cam.fresh(settle_s=settle))
        locate = partial(find_circle, r_min_px=a.rmin, r_max_px=a.rmax)
        target = (lens.newK[0, 2], lens.newK[1, 2])
        res = center_on(grab, locate, mr.move_rel, mmap, target, tol_mm=0.01)
        print("centering:", res)
        if not res["converged"]:
            raise SystemExit("did not converge; offset not saved")
        x2, y2, _ = mr.position()
        off = [x1 - x2, y1 - y2]       # camera axis position relative to nozzle axis
        MS.save(C.rel(cfg, "calibration/machine.json"), down_cam_offset_mm=off)
        print("down_cam_offset_mm =", off, "(repeat 3-5x from different spots; spread = your error)")
    finally:
        cam.stop()


def cmd_datum(cfg, a):
    """--teach: remember where the grid is.  --reference: record up-cam position in datum frame.
    (no flag): re-measure the datum and report drift of the up camera's machine position."""
    mr = make_mr(cfg)
    cam, lens = open_cam(cfg, "down")
    ms_path = C.rel(cfg, "calibration/machine.json")
    ms = MS.load(ms_path)
    settle = cfg["moonraker"]["settle_s"]
    try:
        if a.teach:
            input("Jog the down camera so the whole datum GRID is centred, sharp and well lit. "
                  "Press Enter...")
            x, y, z = mr.position()
            MS.save(ms_path, grid_view_xyz=[x, y, z])
            print("saved grid view", (x, y, z))
            return
        if not ms["grid_view_xyz"]:
            raise SystemExit("run `datum --teach` first")
        gx, gy, gz = ms["grid_view_xyz"]
        motion = MotionMap.load(C.rel(cfg, cfg["cameras"]["down"]["motion_map"]))
        g = DatumGeometry.from_cfg(cfg["datum"])
        off = np.array(ms["down_cam_offset_mm"], float)
        principal = np.array([lens.newK[0, 2], lens.newK[1, 2]])

        def view(x, y):
            mr.move_abs(x=x, y=y, z=gz)
            return lens.undistort(cam.fresh(settle_s=settle))

        def to_m(px, x, y):
            return np.array([x, y]) + off + motion.offset_mm(np.array(px) - principal)

        r_px = g.dot_diameter_mm / 2 / motion.mm_per_px
        pose = measure_datum(view, to_m, g, (gx, gy), off, cfg["datum"]["expected_rotation_deg"],
                             r_px, principal)
        print(f"datum rotation {pose['rot_deg']:.3f} deg, scale {pose['s']:.5f}, "
              f"fit rms {pose['rms_mm']:.4f} mm, origin at machine XY {pose['t'].round(3)}")
        print("grid-only fit:", {k: round(v, 4) for k, v in pose["grid_only"].items()})
        up = np.array(ms["up_cam_xy_mm"], float)
        if a.reference:
            if not up.any():
                raise SystemExit("measure up_cam_xy_mm first (calibrate-motion --cam up --find-center)")
            MS.save(ms_path, up_cam_in_datum_mm=to_datum_xy(pose, up).tolist())
            print("recorded up camera at datum XY", to_datum_xy(pose, up).round(3))
        elif ms["up_cam_in_datum_mm"]:
            pred = to_machine_xy(pose, ms["up_cam_in_datum_mm"])
            print("up camera machine XY now", pred.round(3), "| stored", up.round(3),
                  "| drift (mm)", (pred - up).round(3))
    finally:
        cam.stop()


def cmd_light_test(cfg, a):
    """Flash the up light N times, save one lit and one dark frame, report brightness."""
    lc = cfg["lighting"]["up"]
    light = make_light(lc, make_mr(cfg))
    cam, _ = open_cam(cfg, "up")
    try:
        for n in range(a.n):
            light.off(); dark = cam.fresh(settle_s=lc["settle_s"])
            light.on(); lit = cam.fresh(settle_s=lc["settle_s"])
            print(f"flash {n + 1}: mean dark {dark.mean():.1f}  mean lit {lit.mean():.1f}")
        light.off()
        cv2.imwrite("light_dark.png", dark); cv2.imwrite("light_lit.png", lit)
        print("wrote light_dark.png light_lit.png  (lit should be clearly brighter and not saturated)")
    finally:
        light.off()
        cam.stop()


def cmd_inspect_up(cfg, a):
    """Measure whatever is on the nozzle over the up camera (jog there first)."""
    mr = make_mr(cfg)
    lc = cfg["lighting"]["up"]
    cam, lens = open_cam(cfg, "up")
    try:
        motion = MotionMap.load(C.rel(cfg, cfg["cameras"]["up"]["motion_map"]))
        up = UpCam(cam, lens, make_light(lc, mr), motion, settle_s=lc["settle_s"],
                   ambient_subtract=lc["ambient_subtract"], keep_on=lc["keep_on"],
                   search_radius_mm=lc["search_radius_mm"])
        img = up.frame()
        cv2.imwrite("inspect_up.png", img)
        exp = tuple(a.size) if a.size else None
        res = up.inspect(exp, a.tol, EventLog(C.rel(cfg, cfg["log"]["db"])), img=img)
        print(json.dumps(res, indent=2), "\n(saved inspect_up.png)")
    finally:
        cam.stop()


def main():
    ap = argparse.ArgumentParser(prog="pnpvision")
    ap.add_argument("--config", default="config.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check-lens"); p.add_argument("--cam", default="both", choices=["up", "down", "both"])
    p = sub.add_parser("snapshot"); p.add_argument("--cam", required=True, choices=["up", "down"]); p.add_argument("--out", default="snap"); p.add_argument("--lit", action="store_true", help="(up) use the light rig")
    p = sub.add_parser("calibrate-motion")
    p.add_argument("--cam", required=True, choices=["up", "down"])
    p.add_argument("--step", type=float, default=1.0, help="jog size, mm")
    p.add_argument("--rmin", type=float, default=15, help="feature min radius, px")
    p.add_argument("--rmax", type=float, default=120, help="feature max radius, px")
    p.add_argument("--find-center", action="store_true", help="(up) also record nozzle-over-camera XY")
    p = sub.add_parser("calibrate-offset")
    p.add_argument("--rmin", type=float, default=15); p.add_argument("--rmax", type=float, default=120)

    p = sub.add_parser("light-test"); p.add_argument("--n", type=int, default=3)
    p = sub.add_parser("inspect-up")
    p.add_argument("--size", type=float, nargs=2, metavar=("L", "W"), help="expected part body, mm")
    p.add_argument("--tol", type=float, default=0.15)
    p = sub.add_parser("datum")
    p.add_argument("--teach", action="store_true"); p.add_argument("--reference", action="store_true")

    a = ap.parse_args()
    cfg = C.load(a.config)
    {"check-lens": cmd_check_lens, "snapshot": cmd_snapshot,
     "calibrate-motion": cmd_calibrate_motion, "calibrate-offset": cmd_calibrate_offset, "datum": cmd_datum,
     "light-test": cmd_light_test, "inspect-up": cmd_inspect_up}[a.cmd](cfg, a)
