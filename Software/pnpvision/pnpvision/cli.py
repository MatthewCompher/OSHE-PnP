"""python -m pnpvision <command>   (run from the project folder)"""
import argparse
import json
import os
import time
from functools import partial

import cv2

from . import config as C
from . import machine_state as MS
from .camera import Camera, SnapshotCamera
from .datum import DatumGeometry, measure_datum, to_datum_xy, to_machine_xy
import numpy as np
from .detect import find_circle, find_circles
from .lens import LensModel
from .moonraker import Moonraker
from .motion import MotionMap
from .servo import calibrate_motion, center_on, repeatability_test, visual_home
from .lighting import make_light, grab_lit
from .upcam import UpCam
from .rotation import Rotator
from .eventlog import EventLog


def open_cam(cfg, role):
    c = cfg["cameras"][role]
    lens = LensModel(C.rel(cfg, c["calibration"]))
    lc = cfg.get("lighting", {}).get(role, {})
    if lc.get("on_when_opened"):             # e.g. down light: switch on before measuring
        try:
            make_light(lc, make_mr(cfg)).on()
        except Exception as e:
            raise SystemExit(f"{role} camera: could not switch its light on through Moonraker "
                             f"({e}). Is Klipper running?")
        time.sleep(lc.get("settle_s", 0.3))
    if c.get("snapshot_url"):                 # normal case: share the camera with crowsnest
        cam = SnapshotCamera(c["snapshot_url"], c["width"], c["height"], name=role).start()
    else:                                     # direct V4L2 (crowsnest must not hold the device)
        cam = Camera(c["device"], c["width"], c["height"], c["fps"],
                     exposure=c.get("exposure", 0), name=role).start()
    return cam, lens


def dot_locator(a):
    """Circle finder configured from the --rmin/--rmax/--polarity/--thresh options."""
    return partial(find_circle, r_min_px=a.rmin, r_max_px=a.rmax, min_circularity=a.circ,
                   polarity=a.polarity, threshold=a.thresh)


# The nozzle bore is small (r ~15 px) and a glint or speck at its edge notches it: on 2026-11-14 a
# clean, steady bore scored 0.76-0.79, so bore searches accept a lower circularity than dots.
BORE_MIN_CIRC = 0.70


def bore_locator(bore):
    """Circle finder for a tip's bore over the up camera (tips.<name>.bore in machine.json)."""
    return partial(find_circle, r_min_px=bore.get("rmin", 8), r_max_px=bore.get("rmax", 30),
                   min_circularity=bore.get("circ", BORE_MIN_CIRC),
                   polarity=bore.get("polarity", "dark"), threshold=bore.get("thresh", 40))


def add_dot_args(p):
    p.add_argument("--rmin", type=float, default=15, help="dot min radius, px")
    p.add_argument("--rmax", type=float, default=120, help="dot max radius, px")
    p.add_argument("--polarity", default="both", choices=["both", "dark", "bright"],
                   help="dark dot on light, bright dot on dark, or either")
    p.add_argument("--thresh", type=float,
                   help="fixed 0-255 black/white cut-off instead of automatic "
                        "(e.g. --polarity bright --thresh 230 for the datum's white dots)")
    p.add_argument("--circ", type=float, default=0.80,
                   help="minimum circularity 0-1 (default 0.80; the nozzle bore over the up camera "
                        f"needs ~{BORE_MIN_CIRC})")


def make_mr(cfg):
    m = cfg["moonraker"]
    mc = cfg["machine"]
    return Moonraker(m["url"], m["feedrate_mm_min"], mc["x_range"], mc["y_range"], mc["z_range"],
                     safe_travel_z=mc.get("safe_travel_z"))


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


def cmd_find_dot(cfg, a):
    """One frame, no moves: list the round blobs the detector sees, with the chosen one
    marked, so --rmin/--rmax/--polarity/--thresh can be tuned before a real command."""
    cam, lens = open_cam(cfg, a.cam)
    try:
        img = lens.undistort(cam.fresh(settle_s=cfg["moonraker"]["settle_s"]))
    finally:
        cam.stop()
    found = find_circles(img, a.rmin, a.rmax, min_circularity=a.circ, polarity=a.polarity,
                         threshold=a.thresh)
    principal = np.array([lens.newK[0, 2], lens.newK[1, 2]])
    mpath = C.rel(cfg, cfg["cameras"][a.cam]["motion_map"])
    motion = MotionMap.load(mpath) if os.path.exists(mpath) else None
    out = img.copy()
    cv2.drawMarker(out, tuple(int(v) for v in principal), (0, 255, 255), cv2.MARKER_CROSS, 40, 1)
    print(f"{len(found)} round blob(s), best first (crosshair at {principal.round(1)}):")
    for i, c in enumerate(found[:8]):
        d = np.array(c.center_px) - principal
        mm = f"  = {motion.offset_mm(d).round(3)} mm" if motion else ""
        print(f"  {'*' if i == 0 else ' '} centre {np.round(c.center_px, 1)}  r {c.radius_px:.1f} px  "
              f"circ {c.circularity:.3f}  from crosshair {d.round(1)} px{mm}")
        col = (0, 0, 255) if i == 0 else (255, 128, 0)
        cv2.circle(out, tuple(int(v) for v in c.center_px), int(c.radius_px), col, 2 if i == 0 else 1)
    cv2.imwrite(a.out, out)
    print("wrote", a.out, "(red = the one commands would use)")


def cmd_focus_sweep(cfg, a):
    """Up camera: step the nozzle in Z (no X/Y moves) and score sharpness around the nozzle axis."""
    mr = make_mr(cfg)
    ms = MS.load(C.rel(cfg, "calibration/machine.json"))
    x, y, z_start = mr.position()
    if np.linalg.norm(np.subtract([x, y], ms["up_cam_xy_mm"])) > 3.0:
        raise SystemExit(f"move the nozzle over the up camera first (stored centre {ms['up_cam_xy_mm']})")
    if max(a.z0, a.z1) > 40.0:
        raise SystemExit("refusing Z > 40 over the up camera (plate ~Z50, lens just under it)")
    lc = cfg["lighting"]["up"]
    light = make_light(lc, mr)
    cam, lens = open_cam(cfg, "up")
    motion = MotionMap.load(C.rel(cfg, cfg["cameras"]["up"]["motion_map"]))
    cx, cy = lens.newK[0, 2], lens.newK[1, 2]
    r = int(a.radius / motion.mm_per_px)
    rows = []
    try:
        n = int(round(abs(a.z1 - a.z0) / a.step)) + 1
        for z in np.linspace(a.z0, a.z1, n):
            mr.move_abs(z=float(z), feedrate=300)
            img = grab_lit(cam, light, lens, lc["settle_s"], keep_on=True)
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            crop = g[max(int(cy) - r, 0):int(cy) + r, max(int(cx) - r, 0):int(cx) + r]
            sharp = float(cv2.Laplacian(crop, cv2.CV_64F).var())
            rows.append((float(z), sharp, float(crop.mean()), float((crop >= 250).mean() * 100)))
            print(f"Z{z:7.2f}  sharpness {sharp:9.1f}  mean {rows[-1][2]:5.1f}  saturated {rows[-1][3]:4.1f}%")
            cv2.imwrite(f"focus_z{z:.2f}.png", img)
    finally:
        cam.stop()
        mr.move_abs(z=min(z_start, a.z0, a.z1), feedrate=300)   # end at the highest of the Zs used
    best = max(rows, key=lambda t: t[1])
    print(f"sharpest at Z{best[0]:.2f} (images focus_z*.png). Nozzle left at Z{min(z_start, a.z0, a.z1):.2f}")


def cmd_calibrate_motion(cfg, a):
    mr = make_mr(cfg)
    cam, lens = open_cam(cfg, a.cam)
    settle = cfg["moonraker"]["settle_s"]
    try:
        grab = lambda: lens.undistort(cam.fresh(settle_s=settle))
        locate = dot_locator(a)
        moving = "camera" if a.cam == "down" else "target"
        if a.cam == "up":
            # The nozzle tip is only sharp low over the up camera (below safe_travel_z), so
            # jog at the current height instead of lifting before every move.
            if 2 * a.step > mr.MAX_LOW_XY_MM:
                raise SystemExit(f"--step {a.step} too big for low jogs (max {mr.MAX_LOW_XY_MM / 2} mm)")
            move = lambda dx, dy: mr.move_rel(dx, dy, stay_low=True)
            z0 = mr.position()[2]
            print(f"up camera: calibrating with the nozzle tip at Z{z0:.3f} (jogs stay at this height)")
        else:
            move = mr.move_rel
        map_path = C.rel(cfg, cfg["cameras"][a.cam]["motion_map"])
        if a.center_only:
            if a.cam != "up":
                raise SystemExit("--center-only is for --cam up")
            mmap = MotionMap.load(map_path)
            print("using the existing motion map:", round(mmap.mm_per_px, 5), "mm/px")
        else:
            mmap = calibrate_motion(grab, locate, move, a.step, moving)
            print(json.dumps(mmap.describe(), indent=2))
            mmap.save(map_path)
        if a.cam == "up" and (a.find_center or a.center_only):
            ms_path = C.rel(cfg, "calibration/machine.json")
            old = MS.load(ms_path)
            target = (lens.newK[0, 2], lens.newK[1, 2])
            res = center_on(grab, locate, move, mmap, target, max_step_mm=mr.MAX_LOW_XY_MM * 0.8)
            print("centering:", res)
            if res["converged"]:
                x, y, z = mr.position()
                upd = {"up_cam_xy_mm": [x, y], "up_cam_focus_z": z}
                print("up camera optical axis at machine XY", (x, y), "nozzle tip in focus at Z", z)
                if any(old["up_cam_xy_mm"]):
                    # Up camera and down-camera frame are both fixed to the plate, so a change here
                    # means the nozzle moved relative to the down camera, by the same amount.
                    d = np.subtract([x, y], old["up_cam_xy_mm"])
                    off = np.add(old["down_cam_offset_mm"], d)
                    print(f"change since last time: {d.round(3)} mm -> down_cam_offset_mm would be "
                          f"{off.round(3)} (now {np.round(old['down_cam_offset_mm'], 3)})")
                    if a.update_offset:
                        upd["down_cam_offset_mm"] = off.tolist()
                        print("down_cam_offset_mm updated")
                    elif a.keep_offset:
                        print("saved the new centre only; down_cam_offset_mm unchanged (the feature "
                              "changed, not the nozzle)")
                    elif np.linalg.norm(d) > 0.02:
                        print("NOT saved. True only if the nozzle moved, not the up camera: check with "
                              "`datum` first, then re-run with --update-offset to save both.")
                        return
                MS.save(ms_path, **upd)
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
              "at the SAME height the down-camera motion map was calibrated at). Press Enter...")
        x1, y1, _ = mr.position()
        input("Now lift the nozzle to a safe Z (on this machine SMALLER Z = HIGHER, e.g. Z5) and "
              "jog X/Y only, roughly, so the dot is in the down camera's view. Press Enter...")
        grab = lambda: lens.undistort(cam.fresh(settle_s=settle))
        locate = dot_locator(a)
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


def cmd_repeatability(cfg, a):
    """Down camera over a fixed dot: travel away and back N times, measure where it lands."""
    mr = make_mr(cfg)
    if a.feed:
        mr.feedrate = a.feed
    cam, lens = open_cam(cfg, "down")
    settle = cfg["moonraker"]["settle_s"]
    try:
        mmap = MotionMap.load(C.rel(cfg, cfg["cameras"]["down"]["motion_map"]))
        grab = lambda: lens.undistort(cam.fresh(settle_s=settle))
        locate = dot_locator(a)
        target = (lens.newK[0, 2], lens.newK[1, 2])
        res = center_on(grab, locate, mr.move_rel, mmap, target, tol_mm=0.01)
        print("centering on the dot:", res)
        if not res["converged"]:
            raise SystemExit("could not centre on the dot; is it in view and at the calibrated height?")
        x, y, z = mr.position()
        print(f"\nAbout to run {a.n} cycles from X{x:.2f} Y{y:.2f}: travel {a.radius[0]:g}-{a.radius[1]:g} mm "
              f"away (8 directions) and back at F{mr.feedrate:.0f}"
              + (f", re-homing X/Y (G28 X Y) every {a.home_every} cycles" if a.home_every else "") + ".")
        print(f"Every X/Y move first lifts the nozzle to Z <= {mr.safe_travel_z} "
              f"(now Z{z:.2f}); make sure nothing within that radius is taller than that clearance.")
        input("Press Enter to start (Ctrl+C to cancel)...")
        out = repeatability_test(grab, locate, mmap, mr.move_abs, mr.position, n=a.n,
                                 radius_mm=tuple(a.radius), limits=mr.limits,
                                 home=lambda: mr.gcode("G28 X Y"), home_every=a.home_every, seed=a.seed)
        out["settings"] = {"start_xyz": [x, y, z], "feedrate": mr.feedrate, "radius_mm": a.radius,
                           "home_every": a.home_every, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        print(json.dumps(out["summary"], indent=2))
        path = C.rel(cfg, "results/repeatability_" + time.strftime("%Y%m%d_%H%M%S") + ".json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(out, f, indent=2)
        print("saved", path)
    finally:
        cam.stop()


def cmd_home(cfg, a):
    """Visual homing on a fixed dot (datum dot 0). --teach once; then use instead of plain G28.
    --notify: also report the result in the Mainsail console (used by the VISION_HOME macro,
    which starts this in the background and so cannot show its output)."""
    if not a.notify:
        return _home(cfg, a)
    mr = make_mr(cfg)

    def respond(msg, error=False):
        msg = " ".join(str(msg).replace('"', "'").split())[:250]
        try:
            mr.gcode(f'RESPOND {"TYPE=error " if error else ""}MSG="{msg}"')
        except Exception:
            pass
    try:
        respond("VISION_HOME: " + _home(cfg, a))
    except BaseException as e:            # SystemExit too: those carry the useful message
        respond(f"VISION_HOME FAILED: {e}", error=True)
        raise


def _home(cfg, a):
    mr = make_mr(cfg)
    ms_path = C.rel(cfg, "calibration/machine.json")
    cam, lens = open_cam(cfg, "down")
    settle = cfg["moonraker"]["settle_s"]
    try:
        motion = MotionMap.load(C.rel(cfg, cfg["cameras"]["down"]["motion_map"]))
        grab = lambda: lens.undistort(cam.fresh(settle_s=settle))
        target = (lens.newK[0, 2], lens.newK[1, 2])
        if a.teach:
            if not mr.is_homed():
                raise SystemExit("home the machine first (G28), then jog the homing dot under the crosshair")
            locate = dot_locator(a)
            res = center_on(grab, locate, mr.move_rel, motion, target, tol_mm=0.01, max_iter=8)
            print("centering:", res)
            if not res["converged"]:
                raise SystemExit("could not centre on the dot; check --polarity/--thresh with `snapshot`")
            x, y, _ = mr.position()
            MS.save(ms_path, visual_home={"xy": [x, y], "rmin": a.rmin, "rmax": a.rmax,
                                          "polarity": a.polarity, "thresh": a.thresh,
                                          "taught": time.strftime("%Y-%m-%d %H:%M:%S")})
            print(f"taught homing dot at X{x:.4f} Y{y:.4f} (saved in {ms_path}).\n"
                  "This XY now DEFINES the machine frame: positions measured later (up camera, "
                  "feeders, boards) are only valid against it, so don't re-teach casually.")
            return f"taught homing dot at X{x:.4f} Y{y:.4f}"
        vh = MS.load(ms_path).get("visual_home")
        if not vh:
            raise SystemExit("run `home --teach` first")
        locate = partial(find_circle, r_min_px=vh["rmin"], r_max_px=vh["rmax"],
                         polarity=vh["polarity"], threshold=vh["thresh"])
        if a.no_g28:
            home = None
        elif mr.is_homed():
            home = lambda: mr.gcode("G28 X Y")
        else:
            home = lambda: mr.gcode("G28")         # first home after power-up: Z too

        def set_xy(x, y):
            z = mr.position()[2]
            mr.gcode(f"SET_KINEMATIC_POSITION X={x:.4f} Y={y:.4f} Z={z:.4f}")

        out = visual_home(grab, locate, motion, target, mr.move_abs, mr.position, set_xy,
                          vh["xy"], home=home)
        d = locate(grab())                          # check: no move, dot should sit on target
        check = "check: dot not found"
        if d is not None:
            chk = motion.offset_mm(np.array(d.center_px) - target)
            print(f"check after reset: dot {np.linalg.norm(chk):.4f} mm from the crosshair")
            check = f"check {np.linalg.norm(chk):.4f} mm"
        path = C.rel(cfg, "results/visual_home_log.csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a") as f:
            if new:
                f.write("time,g28,homing_error_x_mm,homing_error_y_mm\n")
            e = out["homing_error_mm"]
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')},{home is not None},{e[0]:.4f},{e[1]:.4f}\n")
        return (f"OK, frame was off X{e[0]:+.3f} Y{e[1]:+.3f} mm, reset to "
                f"X{vh['xy'][0]:.3f} Y{vh['xy'][1]:.3f}, {check}")
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
            # XY only: the down camera isn't on Z, so lowering the nozzle never helps the
            # view and could put it into the bin/clamps (it sits ~53 mm from the camera).
            mr.move_abs(x=x, y=y)
            return lens.undistort(cam.fresh(settle_s=settle))

        def to_m(px, x, y):
            return np.array([x, y]) + off + motion.offset_mm(np.array(px) - principal)

        r_px = g.dot_diameter_mm / 2 / motion.mm_per_px
        pose = measure_datum(view, to_m, g, (gx, gy), off, cfg["datum"]["expected_rotation_deg"],
                             r_px, principal, grid_threshold=cfg["datum"].get("grid_threshold"),
                             dot_threshold=cfg["datum"].get("dot_threshold"))
        print(f"datum rotation {pose['rot_deg']:.3f} deg, scale {pose['s']:.5f}, "
              f"fit rms {pose['rms_mm']:.4f} mm, origin at machine XY {pose['t'].round(3)}")
        print("grid-only fit:", {k: round(v, 4) for k, v in pose["grid_only"].items()},
              "(grid read off ONE image: its scale depends on image scale at the datum's height)")
        print("dots-only fit:", {k: round(v, 4) for k, v in pose["dots_only"].items()},
              "(each dot centred: scale = machine mm vs design mm, independent of height)")
        dm = pose["dots_mm_measured"]
        for (i, j) in ((0, 1), (0, 2), (1, 2)):
            design = float(np.linalg.norm(np.subtract(g.dots_mm[j], g.dots_mm[i])))
            meas = float(np.linalg.norm(dm[j] - dm[i]))
            print(f"  dot {i}-{j}: measured {meas:.3f} mm, design {design:.3f} mm ({(meas / design - 1) * 100:+.2f}%)")
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


def cmd_place_test(cfg, a):
    """You centre the down camera on the first part; it picks, inspects, places on the next
    target and measures, then finds the next part itself (looks like the first one)."""
    from .placetest import PartFinder, place_test, summarize
    mr = make_mr(cfg)
    ms_path = C.rel(cfg, "calibration/machine.json")
    ms = MS.load(ms_path)
    if not any(ms["up_cam_xy_mm"]) or not any(ms["down_cam_offset_mm"]):
        raise SystemExit("up camera centre / down-camera offset not calibrated yet")
    if a.inspect_z is None:
        a.inspect_z = ms.get("up_cam_focus_z") or 34.5
    for name, z in (("pick", a.pick_z), ("place", a.place_z), ("inspect", a.inspect_z)):
        if not (mr.safe_travel_z < z <= 40.0):
            raise SystemExit(f"--{name}-z {z} looks wrong (expected between Z{mr.safe_travel_z} and Z40)")
    step = np.array(a.step, float)
    if a.parts:
        # targets = footprints of the aligned board (align-board first); angle from the job
        from .board import BoardPose
        if not a.job or not ms.get("board_pose"):
            raise SystemExit("--parts needs --job and a saved board pose (run align-board first)")
        with open(a.job, encoding="utf-8") as f:
            by_ref = {p["ref"]: p for p in json.load(f)["placements"]}
        missing = [r for r in a.parts if r not in by_ref]
        if missing:
            raise SystemExit(f"not in the job: {missing}")
        pose = BoardPose.from_dict(ms["board_pose"]["pose"])
        targets = [pose.to_machine([by_ref[r]["x"], by_ref[r]["y"]]) for r in a.parts]
        a.rotate_to = [round(pose.part_angle(by_ref[r]["rot"]), 3) for r in a.parts]
        a.n = len(targets)
        for r, t, ang in zip(a.parts, targets, a.rotate_to):
            print(f"  {r} ({by_ref[r]['package']}, rot {by_ref[r]['rot']}): target {np.round(t, 3).tolist()}, "
                  f"machine angle {ang:.1f} deg")
    elif a.target is None:
        raise SystemExit("give --target X Y (or --job and --parts)")
    else:
        targets = [np.array(a.target, float) + i * step for i in range(a.n)]
    lo, hi = np.min(targets, 0), np.max(targets, 0)
    wd = cfg["cameras"]["down"].get("working_distance_mm", 11.5)
    x0, y0, _ = mr.position()
    first = np.array([x0, y0])
    print(f"first part: the one under the down camera now, at {np.round(first, 3).tolist()}; the rest "
          f"are found automatically within the camera view from there (about +-12 mm X, +-6 mm Y); "
          f"part {a.size[0]}x{a.size[1]}x{a.thickness} mm")
    print(f"{a.n} targets from {np.round(targets[0], 3).tolist()} every {a.step} mm "
          f"(last {np.round(targets[-1], 3).tolist()}); box X {lo[0]:.2f}..{hi[0]:.2f} Y {lo[1]:.2f}..{hi[1]:.2f}")
    print(f"pick Z{a.pick_z}, place Z{a.place_z}, inspect Z{a.inspect_z}; up-camera correction "
          f"{'ON' if a.correct else 'OFF'}; accel {a.accel} mm/s^2; down_cam_offset {ms['down_cam_offset_mm']}")
    if a.rotate_to is not None:
        print(f"rotation: turn each part to {a.rotate_to} deg (re-check within {a.angle_tol} deg); "
              f"the nozzle is first turned to motor 0")
    print("Visual home (VISION_HOME) must have been done since the last re-home, and the up light left on.")
    if input("Start? [y/N] ").strip().lower() != "y":
        return
    old_accel = mr.status("toolhead").get("max_accel")
    down_cam, down_lens = open_cam(cfg, "down")
    up_cam, up_lens = open_cam(cfg, "up")
    lc = cfg["lighting"]["up"]
    settle = cfg["moonraker"]["settle_s"]
    try:
        if a.accel:
            mr.gcode(f"SET_VELOCITY_LIMIT ACCEL={a.accel}")
        down_motion = MotionMap.load(C.rel(cfg, cfg["cameras"]["down"]["motion_map"]))
        up_motion = MotionMap.load(C.rel(cfg, cfg["cameras"]["up"]["motion_map"]))
        up = UpCam(up_cam, up_lens, make_light(lc, mr), up_motion, settle_s=lc["settle_s"],
                   ambient_subtract=lc["ambient_subtract"], keep_on=True,
                   search_radius_mm=lc["search_radius_mm"])
        log = EventLog(C.rel(cfg, cfg["log"]["db"]))
        stamp = time.strftime("%Y%m%d_%H%M%S")
        img_dir = f"place_test_{stamp}"
        os.makedirs(img_dir, exist_ok=True)
        shots = [0]

        def save(name, img):
            cv2.imwrite(os.path.join(img_dir, name + ".png"), img)

        def up_inspect(size):
            img = up.frame()
            shots[0] += 1
            save(f"up{shots[0]}", img)
            return up.inspect(tuple(size), a.tol, log, img=img)

        rotator = None
        if a.rotate_to is not None:
            rotator = Rotator.from_config(mr.gcode, cfg["rotation"])
            rotator.zero()           # software tracks the angle from here (G28 zero)
        down_grab = lambda: down_lens.undistort(down_cam.fresh(settle_s=settle))
        principal = np.array([down_lens.newK[0, 2], down_lens.newK[1, 2]])
        k_height = wd / (wd - a.thickness)
        finder = PartFinder(mr, down_grab, down_motion, principal, tuple(a.size), k_height, first,
                            avoid=targets, save=save)
        save("first_part_template", finder.template)
        if finder.mask is not None:
            save("first_part_mask", finder.mask)
        results = place_test(
            mr, down_grab, down_motion, principal, up_inspect, ms, finder, targets,
            size_mm=tuple(a.size), thickness_mm=a.thickness, working_distance_mm=wd,
            pick_z=a.pick_z, place_z=a.place_z, inspect_z=a.inspect_z,
            vac_ms=a.vac_ms, release_ms=a.release_ms, correct=a.correct, save=save,
            rotator=rotator, rotate_to=(a.rotate_to[0] if a.rotate_to and len(a.rotate_to) == 1 else a.rotate_to), angle_tol_deg=a.angle_tol)
        summary = summarize(results, ms["down_cam_offset_mm"], a.correct)
        print("\n" + json.dumps(summary, indent=2))
        path = C.rel(cfg, f"results/place_test_{stamp}.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump({"settings": vars(a) | {"targets": [t.tolist() for t in targets]},
                       "machine": ms, "results": results, "summary": summary}, f, indent=2, default=str)
        print("saved", path, f"(images in {img_dir}/)")
        if a.apply_offset and summary.get("ok", 0) >= 3:
            MS.save(ms_path, down_cam_offset_mm=summary["suggested_down_cam_offset_mm"])
            print("down_cam_offset_mm updated to", summary["suggested_down_cam_offset_mm"])
        elif a.apply_offset:
            print("not applying the offset: need at least 3 good cycles")
    finally:
        try:
            mr.move_abs(z=mr.safe_travel_z, feedrate=600)
        except Exception as e:
            print("could not lift the nozzle:", e)
        if a.accel and old_accel:
            mr.gcode(f"SET_VELOCITY_LIMIT ACCEL={old_accel}")
        down_cam.stop()
        up_cam.stop()


def cmd_align_board(cfg, a):
    """Centre the down camera on alignment pad A (either pad of that part); finds all the job's
    alignment pads, fits the board's position and rotation, saves calibration/board_pose.json."""
    from .board import align_board
    with open(a.job, encoding="utf-8") as f:
        job = json.load(f)
    if job.get("format") != "oshe-pnp-job/1":
        raise SystemExit(f"{a.job}: not an oshe-pnp-job/1 file")
    mr = make_mr(cfg)
    x0, y0, _ = mr.position()
    pa = job["alignment"][0]
    print(f"board '{job['board']['name']}' ({job['board']['side']}), {len(job['alignment'])} alignment pads; "
          f"start: camera on pad {pa['name']} ({pa.get('ref', '')} pad {pa.get('pad', '')}) at "
          f"[{x0:.3f}, {y0:.3f}], board turned about {a.rot} deg (CCW seen from above)")
    cam, lens = open_cam(cfg, "down")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    img_dir = f"align_{stamp}"
    os.makedirs(img_dir, exist_ok=True)
    save = lambda name, img: cv2.imwrite(os.path.join(img_dir, name + ".png"), img)
    try:
        motion = MotionMap.load(C.rel(cfg, cfg["cameras"]["down"]["motion_map"]))
        principal = np.array([lens.newK[0, 2], lens.newK[1, 2]])
        grab = lambda: lens.undistort(cam.fresh(settle_s=cfg["moonraker"]["settle_s"]))
        try:
            pose, out = align_board(mr, grab, motion, principal, job, (x0, y0), a.rot,
                                    search_mm=a.search, min_score=a.min_score, save=save)
        except RuntimeError as e:
            raise SystemExit(f"alignment failed: {e} (images in {img_dir}/)")
        for p in out["pads"]:
            print(f"  pad {p['name']}: at {np.round(p['machine'], 3).tolist()}, residual "
                  f"{np.round(p['residual_mm'], 3).tolist()} mm")
        print(f"board rotation {pose.angle_deg:.3f} deg, origin at {np.round(pose.t, 3).tolist()}, "
              f"scale {out['scale']:.4f}, worst pad residual {out['max_residual_mm']:.3f} mm")
        out["job"] = os.path.abspath(a.job)
        MS.save(C.rel(cfg, "calibration/machine.json"), board_pose=out)
        print("saved as board_pose in calibration/machine.json")
        # look at some placements: the crosshair should sit between each part's pads
        refs = a.show or [p["ref"] for p in job["alignment"] if p.get("ref")]
        by_ref = {p["ref"]: p for p in job["placements"]}
        for ref in refs:
            if ref not in by_ref:
                print(f"  (no placement {ref})")
                continue
            pl = by_ref[ref]
            xy = pose.to_machine([pl["x"], pl["y"]])
            mr.move_abs(x=float(xy[0]), y=float(xy[1]))
            img = grab()
            cv2.drawMarker(img, tuple(int(v) for v in principal), (0, 255, 255), cv2.MARKER_CROSS, 80, 2)
            save(f"show_{ref}", img)
            print(f"  {ref} ({pl['package']}, rot {pl['rot']}): camera at {np.round(xy, 3).tolist()}, "
                  f"part angle on the machine {pose.part_angle(pl['rot']):.1f} deg")
        print(f"images in {img_dir}/")
    finally:
        cam.stop()


def _feeder_bus(cfg, sim=False):
    from .feeders import SerialFeederBus, SimFeederBus
    if sim:
        return SimFeederBus()
    fc = cfg.get("feeders", {})
    return SerialFeederBus(fc.get("port", "/dev/ttyUSB0"), fc.get("baud", 115200),
                           fc.get("timeout_s", 8.0))


def _feeders_path(cfg):
    return C.rel(cfg, cfg.get("feeders", {}).get("file", "calibration/feeders.json"))


def cmd_tip(cfg, a):
    """Record a nozzle tip's measured heights and/or declare which tip is on the nozzle now."""
    path = C.rel(cfg, "calibration/machine.json")
    ms = MS.load(path)
    tips = dict(ms.get("tips") or {})
    t = dict(tips.get(a.name, {}))
    if a.board_touch_z is not None:
        t["board_touch_z"] = a.board_touch_z
    if a.inspect_z is not None:
        t["inspect_z"] = a.inspect_z
    tips[a.name] = t
    upd = {"tips": tips}
    if a.current:
        upd["current_tip"] = a.name
    MS.save(path, **upd)
    print(f"tip {a.name}: {t}" + ("  (now the current tip)" if a.current else ""))


def cmd_teach_feeder(cfg, a):
    """Nozzle lowered by eye onto the part in the pocket: save that XY and Z as the feeder's pick."""
    from .feeders import FeederBank, Feeder
    mr = make_mr(cfg)
    x, y, z = mr.position()
    ms = MS.load(C.rel(cfg, "calibration/machine.json"))
    path = _feeders_path(cfg)
    bank = FeederBank.load(path)
    d = {"id": a.id, "kind": "manual" if a.manual else "servo", "xy": [x, y], "part_top_z": z,
         "teach_tip": ms.get("current_tip"), "package": a.package, "value": a.value or "",
         "learned_xy": [0.0, 0.0]}
    if not a.manual:
        if a.servo is None:
            raise SystemExit("give --servo N (or --manual)")
        d["servo"] = a.servo
    if a.tape_angle is not None:
        d["tape_angle_deg"] = a.tape_angle
    old = bank.get(a.id)
    if old is not None:
        bank.feeders.remove(old)
    bank.feeders.append(Feeder(d))
    bank.feeders.sort(key=lambda fd: fd.d["xy"][0])
    bank.save(path)
    print(f"feeder {a.id}: pick at X{x:.3f} Y{y:.3f}, part top Z{z:.3f} (tip {d['teach_tip']}), {d}")
    for w in bank.check_spacing():
        print("  check:", w)


def cmd_teach_bin(cfg, a):
    mr = make_mr(cfg)
    x, y, _ = mr.position()
    MS.save(C.rel(cfg, "calibration/machine.json"), reject_bin_xy=[x, y])
    print(f"reject bin at X{x:.3f} Y{y:.3f} (parts are dropped from Z{mr.safe_travel_z})")


def cmd_feed(cfg, a):
    bus = _feeder_bus(cfg)
    try:
        for i in range(a.times):
            t0 = time.time()
            bus.feed(a.servo)
            bus.wait(a.servo)
            print(f"feed {i + 1}/{a.times} on servo {a.servo}: done in {time.time() - t0:.2f} s")
    finally:
        bus.close()


def _find_job(cfg, name):
    """A job file path, or a job name from jobs/ (spaces may be written as _, .job.json optional)."""
    if os.path.isfile(name):
        return name
    d = C.rel(cfg, "jobs")
    names = sorted(f for f in os.listdir(d) if f.endswith(".job.json")) if os.path.isdir(d) else []
    for f in names:
        stem = f[:-len(".job.json")]
        if name in (f, stem, stem.replace(" ", "_")):
            return os.path.join(d, f)
    raise SystemExit(f"no job {name!r}: jobs/ has " +
                     (", ".join(n[:-9].replace(" ", "_") for n in names) or "nothing"))


def cmd_run_job(cfg, a):
    """--hmi: started from the touchscreen (RUN_JOB macro): prompts become dialogs, messages go to
    the Klipper console, errors are shown there too, and only one job runs at a time."""
    if not a.hmi:
        return _run_job(cfg, a, None)
    from .hmi import Hmi
    hmi = Hmi(make_mr(cfg))
    lock = None
    try:
        try:
            import fcntl
            lock = open("/tmp/pnpvision_run_job.lock", "w")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except ImportError:
            pass
        except OSError:
            raise SystemExit("a job is already running (PNP_STOP to end it)")
        hmi.start()
        return _run_job(cfg, a, hmi)
    except BaseException as e:            # SystemExit too: those carry the useful message
        hmi.error(f"RUN_JOB failed: {e}")
        raise
    finally:
        if lock is not None:
            lock.close()


def _run_job(cfg, a, hmi):
    from .board import BoardPose
    from .feeders import FeederBank
    from .runner import JobError, dry_run, plan_job, run_job
    say = hmi.say if hmi else print
    ask = hmi.ask if hmi else input
    a.job = _find_job(cfg, a.job)
    with open(a.job, encoding="utf-8") as f:
        job = json.load(f)
    if job.get("format") != "oshe-pnp-job/1":
        raise SystemExit(f"{a.job}: not an oshe-pnp-job/1 file")
    ms_path = C.rel(cfg, "calibration/machine.json")
    ms = MS.load(ms_path)
    if a.align:
        from types import SimpleNamespace
        rot = a.rot
        if rot is None and ms.get("board_pose"):
            rot = round(BoardPose.from_dict(ms["board_pose"]["pose"]).angle_deg, 1)
        if rot is None:
            raise SystemExit("--align needs --rot (no earlier alignment to take the board angle from)")
        say(f"aligning the board (camera must be on alignment pad A, board at about {rot} deg)...")
        cmd_align_board(cfg, SimpleNamespace(job=a.job, rot=rot, search=3.0, min_score=0.5, show=[]))
        ms = MS.load(ms_path)
        say(f"board aligned: {BoardPose.from_dict(ms['board_pose']['pose']).angle_deg:.2f} deg, "
            f"worst pad residual {ms['board_pose'].get('max_residual_mm', 0):.3f} mm")
    bp = ms.get("board_pose")
    if not bp:
        raise SystemExit("no board pose: run align-board first")
    if bp.get("job_board") != job["board"]["name"]:
        say(f"WARNING: the saved board pose is for '{bp.get('job_board')}', this job is '{job['board']['name']}'")
    pose = BoardPose.from_dict(bp["pose"])
    packages = cfg.get("packages", {})
    only = set(a.only) if a.only else None
    mr = make_mr(cfg)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    img_dir = f"job_{stamp}"
    os.makedirs(img_dir, exist_ok=True)
    if a.dry_run:
        cam, lens = open_cam(cfg, "down")
        principal = (int(lens.newK[0, 2]), int(lens.newK[1, 2]))
        try:
            def look(xy, name):
                mr.move_abs(x=float(xy[0]), y=float(xy[1]))
                img = lens.undistort(cam.fresh(settle_s=cfg["moonraker"]["settle_s"]))
                cv2.drawMarker(img, principal, (0, 255, 255), cv2.MARKER_CROSS, 80, 2)
                cv2.imwrite(os.path.join(img_dir, name + ".png"), img)
            dry_run(job, pose, look, packages, only)
        finally:
            cam.stop()
        print(f"dry run done; photos (crosshair = where each part's centre goes) in {img_dir}/")
        return
    tips = ms.get("tips") or {}
    bus = _feeder_bus(cfg, sim=a.no_feeders)
    bank = FeederBank.load(_feeders_path(cfg), bus, ask=ask)
    for fd in bank.feeders:
        fd.by_hand = a.no_feeders
    steps, problems = plan_job(job, bank, tips, packages, only)
    say(f"job '{job['board']['name']}': {len(steps)} placements; tips in order: "
          f"{list(dict.fromkeys(s['tip'] for s in steps))}; feeders: "
          f"{sorted({s['feeder'].id for s in steps if s['feeder']})}")
    if problems:
        bus.close()
        raise SystemExit("job can't run:\n  " + "\n  ".join(problems))
    say("Before starting: VISION_HOME done, align-board done for this board, UP_LIGHT_ON, "
        "feeders loaded with a part in each pick pocket.")
    if ask("Start? [y/N] ").strip().lower() != "y":
        bus.close()
        return
    log_db = EventLog(C.rel(cfg, cfg["log"]["db"]))
    log = lambda event, ok=None, **d: log_db.log(event, ok=ok, **d)
    up_cam, up_lens = open_cam(cfg, "up")
    lc = cfg["lighting"]["up"]
    try:
        up_motion = MotionMap.load(C.rel(cfg, cfg["cameras"]["up"]["motion_map"]))
        up = UpCam(up_cam, up_lens, make_light(lc, mr), up_motion, settle_s=lc["settle_s"],
                   ambient_subtract=lc["ambient_subtract"], keep_on=True,
                   search_radius_mm=lc["search_radius_mm"])
        shots = [0]

        def up_inspect(body):
            img = up.frame()
            shots[0] += 1
            cv2.imwrite(os.path.join(img_dir, f"up{shots[0]:04d}.png"), img)
            tol = 0.3
            return up.inspect(tuple(body) if body else None, tol, log_db, img=img)

        def recentre(tip):
            """New tip: find its bore over the up camera, move the stored centre and the
            down-camera offset by the same shift (like calibrate-motion --center-only --update-offset)."""
            from .servo import center_on
            t = tips[tip]
            bore = t.get("bore", {})
            locate = bore_locator(bore)
            old = np.asarray(ms["up_cam_xy_mm"], float)
            mr.move_abs(x=float(old[0]), y=float(old[1]))
            mr.move_abs(z=t["inspect_z"], feedrate=300)
            grab = lambda: up_lens.undistort(up_cam.fresh(settle_s=cfg["moonraker"]["settle_s"]))
            res = center_on(grab, locate, lambda dx, dy: mr.move_rel(dx, dy, stay_low=True), up_motion,
                            (up_lens.newK[0, 2], up_lens.newK[1, 2]), max_step_mm=mr.MAX_LOW_XY_MM * 0.8)
            mr.move_abs(z=mr.safe_travel_z, feedrate=600)
            if not res["converged"]:
                raise SystemExit(f"could not find tip {tip}'s bore over the up camera ({res}); set "
                                 f"tips.{tip}.bore detector settings in machine.json (rmin/rmax/thresh)")
            x, y, _ = mr.position()
            d = np.array([x, y]) - old
            ms["up_cam_xy_mm"] = [x, y]
            ms["down_cam_offset_mm"] = (np.asarray(ms["down_cam_offset_mm"], float) + d).tolist()
            MS.save(ms_path, up_cam_xy_mm=ms["up_cam_xy_mm"], down_cam_offset_mm=ms["down_cam_offset_mm"],
                    current_tip=tip)
            return f"shift {np.round(d, 3).tolist()} mm"

        rot = Rotator.from_config(mr.gcode, cfg["rotation"])
        stats = {}
        results = run_job(job, pose, ms, mr, up_inspect, rot, bank, tips, packages, only,
                          current_tip=a.tip or ms.get("current_tip"),
                          recentre=None if a.no_recentre else recentre,
                          reject_xy=ms.get("reject_bin_xy"), ask=ask, say=say, log=log, retries=a.retries,
                          verify_empty=not a.no_verify, stats=stats,
                          stop_requested=hmi.stop_requested if hmi else None,
                          z_feeds=cfg.get("run", {}).get("z_feeds"),
                          show_pick=getattr(a, "show_pick", False))
    except JobError as e:
        raise SystemExit(str(e))
    finally:
        try:
            mr.move_abs(z=mr.safe_travel_z, feedrate=600)
        except Exception as e:
            print("could not lift the nozzle:", e)
        up_cam.stop()
        bank.save(_feeders_path(cfg))          # keeps what the feeders learned
        bus.close()
    path = C.rel(cfg, f"results/job_{stamp}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"job": os.path.abspath(a.job), "pose": bp, "timing": stats, "results": results}, f,
                  indent=2, default=str)
    say(f"saved results/job_{stamp}.json (up-camera images in {img_dir}/)")


def cmd_check_machine(cfg, a):
    """After someone else used the gantry: what still holds, what to redo (see check.py)."""
    from .check import check_machine
    mr = make_mr(cfg)
    ms_path = C.rel(cfg, "calibration/machine.json")
    ms = MS.load(ms_path)
    tip = a.tip or ms.get("current_tip")
    t = (ms.get("tips") or {}).get(tip, {})
    inspect_z = a.inspect_z or t.get("inspect_z") or ms.get("up_cam_focus_z") or 34.5
    print(f"tip {tip or '?'}: inspect Z{inspect_z}, stored up-camera centre {ms['up_cam_xy_mm']}, "
          f"down-camera offset {ms['down_cam_offset_mm']}")
    if not a.yes and input("The NOZZLE must be EMPTY and the head/tip fitted (it goes down to the inspect Z "
                           "over the up camera). Go on? [y/N] ").strip().lower() != "y":
        return
    down_cam, down_lens = open_cam(cfg, "down")
    up_cam, up_lens = open_cam(cfg, "up")
    lc = cfg["lighting"]["up"]
    settle = cfg["moonraker"]["settle_s"]
    try:
        vh = ms.get("visual_home") or {}
        down = {"grab": lambda: down_lens.undistort(down_cam.fresh(settle_s=settle)),
                "locate": partial(find_circle, r_min_px=vh.get("rmin", 15), r_max_px=vh.get("rmax", 120),
                                  polarity=vh.get("polarity", "both"), threshold=vh.get("thresh")),
                "motion": MotionMap.load(C.rel(cfg, cfg["cameras"]["down"]["motion_map"])),
                "target_px": (down_lens.newK[0, 2], down_lens.newK[1, 2])}
        light = make_light(lc, mr)
        bore = t.get("bore", {})
        up = {"grab": lambda: grab_lit(up_cam, light, up_lens, lc["settle_s"], False, keep_on=True),
              "locate": bore_locator(bore),
              "motion": MotionMap.load(C.rel(cfg, cfg["cameras"]["up"]["motion_map"])),
              "target_px": (up_lens.newK[0, 2], up_lens.newK[1, 2])}
        found = check_machine(mr, ms, down, up, inspect_z, apply=a.apply)
    finally:
        down_cam.stop()
        up_cam.stop()
    if a.apply:
        MS.save(ms_path, up_cam_xy_mm=ms["up_cam_xy_mm"], down_cam_offset_mm=ms["down_cam_offset_mm"])
    redo = [f for f in found if f.level != "OK"]
    print("\n" + ("ALL OK" if not redo else f"{len(redo)} thing(s) to look at:\n  " +
                  "\n  ".join(str(f) for f in redo)))
    print("Not checked here (needs you): the tip's board touch Z if the tip was taken off "
          "(`tip NAME --board-touch-z Z`), and align-board if the board moved.")


def cmd_make_launchers(cfg, a):
    """One tiny .gcode file per job (and an _ALIGN variant): selecting it in the touchscreen's
    print list runs RUN_JOB, which starts run-job --hmi in the background."""
    d = C.rel(cfg, "jobs")
    jobs = sorted(f[:-len(".job.json")] for f in os.listdir(d) if f.endswith(".job.json"))
    if not os.path.isdir(a.gcodes):
        raise SystemExit(f"{a.gcodes} not found (give --gcodes)")
    extra = " NO_FEEDERS=1" if a.no_feeders else ""
    for stem in jobs:
        name = stem.replace(" ", "_")
        for suffix, flag, what in (("", "", "uses the last board alignment"),
                                   ("_ALIGN", " ALIGN=1", "aligns the board first: down camera on pad A")):
            path = os.path.join(a.gcodes, f"PNP_{name}{suffix}.gcode")
            with open(path, "w") as f:
                f.write(f"; pnpvision launcher for jobs/{stem}.job.json ({what})\n"
                        f"RUN_JOB JOB={name}{flag}{extra}\n")
            print("wrote", path)


def cmd_set_offset(cfg, a):
    """Write down_cam_offset_mm directly (e.g. the average job error of several place-tests)."""
    path = C.rel(cfg, "calibration/machine.json")
    old = MS.load(path)["down_cam_offset_mm"]
    MS.save(path, down_cam_offset_mm=[float(a.x), float(a.y)])
    print(f"down_cam_offset_mm: {np.round(old, 4).tolist()} -> {[a.x, a.y]}")


def main():
    ap = argparse.ArgumentParser(prog="pnpvision")
    ap.add_argument("--config", default="config.toml")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("check-lens"); p.add_argument("--cam", default="both", choices=["up", "down", "both"])
    p = sub.add_parser("snapshot"); p.add_argument("--cam", required=True, choices=["up", "down"]); p.add_argument("--out", default="snap"); p.add_argument("--lit", action="store_true", help="(up) use the light rig")
    p = sub.add_parser("find-dot", help="no moves: show which round blobs the detector finds")
    p.add_argument("--cam", required=True, choices=["up", "down"])
    p.add_argument("--out", default="find_dot.png")
    add_dot_args(p)
    p = sub.add_parser("focus-sweep", help="up cam: step Z over the camera, score sharpness")
    p.add_argument("--z0", type=float, required=True, help="first Z (smaller = higher)")
    p.add_argument("--z1", type=float, required=True, help="last Z (max 40)")
    p.add_argument("--step", type=float, default=0.5)
    p.add_argument("--radius", type=float, default=2.0, help="scored area around the nozzle axis, mm")
    p = sub.add_parser("calibrate-motion")
    p.add_argument("--cam", required=True, choices=["up", "down"])
    p.add_argument("--step", type=float, default=1.0, help="jog size, mm")
    add_dot_args(p)
    p.add_argument("--find-center", action="store_true", help="(up) also record nozzle-over-camera XY")
    p.add_argument("--center-only", action="store_true",
                   help="(up) keep the motion map, only re-centre (e.g. after the nozzle was remounted)")
    p.add_argument("--update-offset", action="store_true",
                   help="(up) also shift down_cam_offset_mm by the change in the centre")
    p.add_argument("--keep-offset", action="store_true",
                   help="(up) save the new centre but leave down_cam_offset_mm alone (use when you "
                        "switch to a different feature, e.g. the real tip instead of the holder face)")
    p = sub.add_parser("calibrate-offset")
    add_dot_args(p)

    p = sub.add_parser("repeatability", help="down cam over a dot: go away and back N times, measure landing scatter")
    p.add_argument("--n", type=int, default=20, help="cycles")
    p.add_argument("--radius", type=float, nargs=2, default=[30.0, 80.0], metavar=("MIN", "MAX"),
                   help="how far away each cycle travels, mm")
    p.add_argument("--home-every", type=int, default=0, help="re-home X/Y every N cycles (0 = never)")
    p.add_argument("--feed", type=float, help="feedrate mm/min (default: config.toml)")
    p.add_argument("--seed", type=int, help="random seed for the travel distances")
    add_dot_args(p)

    p = sub.add_parser("home", help="visual homing: G28 X Y, then re-zero X/Y on the homing dot")
    p.add_argument("--teach", action="store_true",
                   help="record the dot under the crosshair as the homing reference (once)")
    p.add_argument("--no-g28", action="store_true", help="skip G28: only re-reference on the dot")
    p.add_argument("--notify", action="store_true", help="also report the result in the Mainsail console")
    add_dot_args(p)

    p = sub.add_parser("light-test"); p.add_argument("--n", type=int, default=3)
    p = sub.add_parser("inspect-up")
    p.add_argument("--size", type=float, nargs=2, metavar=("L", "W"), help="expected part body, mm")
    p.add_argument("--tol", type=float, default=0.3, help="allowed size error per side, mm")
    p = sub.add_parser("place-test", help="centre the down camera on a part first; then pick, inspect, "
                                          "place, measure, and find the next parts automatically")
    p.add_argument("--target", type=float, nargs=2, metavar=("X", "Y"),
                   help="first place target, down camera centred on it (toolhead XY)")
    p.add_argument("--step", type=float, nargs=2, default=[4.0, 0.0], metavar=("DX", "DY"),
                   help="target spacing, mm (default 4 0 = along +X)")
    p.add_argument("--n", type=int, default=5, help="parts to place (= targets)")
    p.add_argument("--size", type=float, nargs=2, default=[2.0, 1.25], metavar=("L", "W"))
    p.add_argument("--thickness", type=float, default=0.85, help="part height, mm (for the down-camera scale)")
    p.add_argument("--tol", type=float, default=0.3, help="allowed size error per side, mm")
    p.add_argument("--pick-z", type=float, default=37.8)
    p.add_argument("--place-z", type=float, default=37.7)
    p.add_argument("--inspect-z", type=float, help="default: up_cam_focus_z from calibration (else 34.5)")
    p.add_argument("--vac-ms", type=int, default=300, help="wait after VALVE_ON before lifting")
    p.add_argument("--release-ms", type=int, default=500, help="wait after VALVE_OFF before lifting")
    p.add_argument("--accel", type=float, default=2000, help="max accel during the test (0 = leave)")
    p.add_argument("--correct", action="store_true", help="apply the up-camera offset when placing")
    p.add_argument("--apply-offset", action="store_true",
                   help="save the suggested down_cam_offset_mm (needs >= 3 good cycles)")
    p.add_argument("--rotate-to", type=float, nargs="+",
                   help="turn each part to this machine-frame angle (deg, long axis from +X) before placing; "
                        "several angles = used in turn (target 1 gets the first, ...)")
    p.add_argument("--angle-tol", type=float, default=1.0,
                   help="(with --rotate-to) turn again if the re-inspected angle is off by more, deg")
    p.add_argument("--job", help="job file, for --parts")
    p.add_argument("--parts", nargs="+", metavar="REF",
                   help="place onto these footprints of the aligned board (align-board first), turned to "
                        "their job angle; replaces --target/--step/--n/--rotate-to")
    p = sub.add_parser("align-board", help="centre the down camera on alignment pad A first; finds the "
                       "board's position and rotation from the job's alignment pads")
    p.add_argument("job", help="oshe-pnp-job/1 file")
    p.add_argument("--rot", type=float, required=True,
                   help="rough board rotation on the plate, deg CCW seen from above (within ~5 deg)")
    p.add_argument("--search", type=float, default=3.0, help="look this far around each predicted pad, mm")
    p.add_argument("--min-score", type=float, default=0.5, help="pad template match threshold")
    p.add_argument("--show", nargs="*", help="placements (refs) to photograph afterwards "
                   "(default: the parts that own the alignment pads)")
    p = sub.add_parser("run-job", help="place a job on the aligned board from the feeders "
                       "(align-board first; --dry-run = camera tour, no parts)")
    p.add_argument("job")
    p.add_argument("--dry-run", action="store_true", help="no parts: photograph every placement spot")
    p.add_argument("--only", nargs="+", metavar="REF", help="place only these parts")
    p.add_argument("--tip", help="tip on the nozzle now (default: current_tip in machine.json)")
    p.add_argument("--retries", type=int, default=3, help="picks per part before asking you")
    p.add_argument("--no-verify", action="store_true", help="skip the empty-nozzle check after placing")
    p.add_argument("--show-pick", action="store_true",
                   help="debug, hand-loaded parts: park the down camera over the pick spot before each "
                        "feed prompt (put the part under the crosshair)")
    p.add_argument("--no-recentre", action="store_true", help="don't re-centre after a tip change")
    p.add_argument("--no-feeders", action="store_true",
                   help="no feeder Nano: servo feeders don't stroke (load parts by hand)")
    p.add_argument("--align", action="store_true",
                   help="align the board first (down camera on alignment pad A); angle from --rot or the last alignment")
    p.add_argument("--rot", type=float, help="(with --align) rough board rotation, deg CCW")
    p.add_argument("--hmi", action="store_true",
                   help="started from the touchscreen (RUN_JOB macro): dialogs instead of keyboard prompts")
    p = sub.add_parser("make-launchers", help="write a PNP_<job>.gcode file per job into the print list, "
                       "so a job can be started from the touchscreen")
    p.add_argument("--gcodes", default=os.path.expanduser("~/printer_data/gcodes"),
                   help="Klipper's gcode folder (default ~/printer_data/gcodes)")
    p.add_argument("--no-feeders", action="store_true", help="launchers run with NO_FEEDERS=1")
    p = sub.add_parser("tip", help="record a nozzle tip's heights and/or make it the current tip")
    p.add_argument("name", help="e.g. N14")
    p.add_argument("--board-touch-z", type=float, help="Z where this tip touches the bare board top")
    p.add_argument("--inspect-z", type=float, help="Z with a part on this tip in focus over the up camera")
    p.add_argument("--current", action="store_true", help="this tip is on the nozzle now")
    p = sub.add_parser("teach-feeder", help="nozzle lowered onto the part in the pocket: save the pick spot")
    p.add_argument("id", help="e.g. F1")
    p.add_argument("--servo", type=int, help="servo number on the feeder Nano")
    p.add_argument("--manual", action="store_true", help="manual track (no servo)")
    p.add_argument("--package", required=True, help="KiCad footprint name, as in the job")
    p.add_argument("--value", help="only parts with this value (default: any)")
    p.add_argument("--tape-angle", type=float,
                   help="machine angle of the part's rot-0 orientation in the pocket (parts with a pin 1)")
    p = sub.add_parser("teach-bin", help="nozzle over the reject bin: save it")
    p = sub.add_parser("feed", help="stroke a servo feeder (tests the Nano)")
    p.add_argument("servo", type=int)
    p.add_argument("--times", type=int, default=1)
    p = sub.add_parser("check-machine", help="after the gantry was used for something else: checks "
                       "printer.cfg, homing, both camera maps and the nozzle centre; reports what to redo")
    p.add_argument("--apply", action="store_true",
                   help="if the nozzle tip moved, save the new up-camera centre and down-camera offset")
    p.add_argument("--tip", help="tip on the nozzle (default: current_tip in machine.json)")
    p.add_argument("--inspect-z", type=float, help="default: the tip's inspect_z")
    p.add_argument("--yes", action="store_true", help="don't ask (nozzle is empty)")
    p = sub.add_parser("set-offset", help="set the down-camera-to-nozzle offset (mm) directly")
    p.add_argument("x", type=float)
    p.add_argument("y", type=float)
    p = sub.add_parser("datum")
    p.add_argument("--teach", action="store_true"); p.add_argument("--reference", action="store_true")

    a = ap.parse_args()
    cfg = C.load(a.config)
    {"check-lens": cmd_check_lens, "snapshot": cmd_snapshot, "find-dot": cmd_find_dot, "focus-sweep": cmd_focus_sweep, "place-test": cmd_place_test,
     "set-offset": cmd_set_offset, "check-machine": cmd_check_machine, "make-launchers": cmd_make_launchers, "align-board": cmd_align_board, "run-job": cmd_run_job,
     "tip": cmd_tip, "teach-feeder": cmd_teach_feeder, "teach-bin": cmd_teach_bin, "feed": cmd_feed,
     "calibrate-motion": cmd_calibrate_motion, "calibrate-offset": cmd_calibrate_offset, "datum": cmd_datum,
     "repeatability": cmd_repeatability, "home": cmd_home,
     "light-test": cmd_light_test, "inspect-up": cmd_inspect_up}[a.cmd](cfg, a)
