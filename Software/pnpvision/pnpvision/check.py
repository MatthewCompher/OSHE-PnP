"""check-machine: after someone else used the gantry (head/nozzle off, cameras maybe bumped,
printer.cfg maybe edited), find out what still holds and what to redo, in a few minutes.

It only measures and reports; the one thing it can fix (with apply=True) is the up-camera centre
after the nozzle/tip was refitted, the same update run-job's tip re-centre does.

Checks, in order:
  1. Klipper still has the sections pnpvision needs (rotation stepper, valve, lights, VISION_HOME).
  2. Down camera over the homing dot: the dot must sit on the crosshair (= VISION_HOME was run).
  3. Down camera motion map: jog 1 mm in X and Y, the dot must move as the map predicts
     (else the camera was turned or refocused: redo calibrate-motion --cam down and what follows).
  4. Up camera: empty nozzle at the tip's inspect Z, centre on the tip's bore; the shift from the
     stored centre is how far the nozzle moved (refitted tip/head). Also a 0.5 mm map check.
Hardware is injected so it runs against a simulator in the tests.
"""
import numpy as np

from .moonraker import lift
from .servo import center_on

REQUIRED_OBJECTS = {
    "manual_stepper stepper_r": "nozzle rotation stepper",
    "output_pin valve": "vacuum valve",
    "gcode_macro VALVE_ON": "vacuum on macro",
    "gcode_macro VALVE_OFF": "vacuum off macro",
    "gcode_macro VISION_HOME": "VISION_HOME button",
    "neopixel up_light": "up-camera light LEDs",
    "gcode_macro UP_LIGHT_ON": "up-camera light macro",
    "gcode_macro VISION_LIGHT_ON": "down-camera light macro",
}

# thresholds
DOT_OK_MM = 0.05          # homing dot vs crosshair right after VISION_HOME
MAP_SCALE_OK = 0.03       # 3 % scale error
MAP_ANGLE_OK_DEG = 1.0
NOZZLE_OK_MM = 0.03       # up-camera centre shift that needs no update


def map_error(M, move_mm, shift_px):
    """How far a measured pixel shift is from the motion map's prediction: (scale error as a
    fraction, angle error in degrees)."""
    pred = np.asarray(M, float) @ np.asarray(move_mm, float)
    s = np.asarray(shift_px, float)
    scale = np.linalg.norm(s) / max(np.linalg.norm(pred), 1e-9) - 1.0
    ang = np.degrees(np.arctan2(pred[0] * s[1] - pred[1] * s[0], pred @ s))
    return float(scale), float(ang)


class Finding:
    def __init__(self, level, what, text):
        self.level, self.what, self.text = level, what, text     # level: OK | REDO | WARN

    def __str__(self):
        return f"{self.level:4s} {self.what}: {self.text}"


def check_klipper(objects):
    have = set(objects)
    missing = [f"[{k}] ({v})" for k, v in REQUIRED_OBJECTS.items() if k not in have]
    if missing:
        return Finding("REDO", "printer.cfg", "missing " + ", ".join(missing) +
                       ": copy those sections back from Software/Klipper/printer.cfg in the repo, restart Klipper")
    return Finding("OK", "printer.cfg", "all pnpvision sections present")


def _map_check(what, grab, locate, move_rel, motion, step_mm, redo):
    d0 = locate(grab())
    if d0 is None:
        return Finding("WARN", what, "feature lost before the map check")
    worst_s, worst_a = 0.0, 0.0
    for m in ((step_mm, 0.0), (0.0, step_mm)):
        move_rel(*m)
        d = locate(grab())
        move_rel(-m[0], -m[1])
        if d is None:
            return Finding("WARN", what, f"feature lost after a {step_mm} mm jog")
        sc, an = map_error(motion.M, m, np.subtract(d.center_px, d0.center_px))
        worst_s = max(worst_s, abs(sc), key=abs)
        worst_a = max(worst_a, abs(an), key=abs)
    txt = f"scale off {worst_s * 100:.1f} %, angle off {worst_a:.2f} deg"
    if worst_s > MAP_SCALE_OK or worst_a > MAP_ANGLE_OK_DEG:
        return Finding("REDO", what, txt + " -> camera turned or refocused: " + redo)
    return Finding("OK", what, txt)


def check_machine(mr, ms, down, up, inspect_z, apply=False, say=print):
    """down/up: dicts with grab(), locate(img), motion (MotionMap), target_px.
    ms: machine.json dict (visual_home, up_cam_xy_mm, down_cam_offset_mm); with apply=True the
    up-camera centre and down-camera offset in ms are updated in place (caller saves).
    Returns a list of Findings."""
    out = []

    def add(f):
        out.append(f)
        say(str(f))

    add(check_klipper(mr.objects()))
    if not mr.is_homed():
        add(Finding("REDO", "homing", "machine not homed: run VISION_HOME, then check-machine again"))
        return out

    # -- down camera on the homing dot -------------------------------------------------------
    vh = ms.get("visual_home")
    if not vh:
        add(Finding("WARN", "down camera", "no visual_home in machine.json: skipped"))
    else:
        mr.move_abs(x=float(vh["xy"][0]), y=float(vh["xy"][1]))
        d = down["locate"](down["grab"]())
        if d is None:
            add(Finding("REDO", "down camera", "homing dot not seen at its taught position: camera moved a lot, "
                        "or the datum moved. Jog the camera over dot 0 and check with find-dot"))
        else:
            off = down["motion"].offset_mm(np.subtract(d.center_px, down["target_px"]))
            e = float(np.linalg.norm(off))
            if e > DOT_OK_MM:
                add(Finding("REDO", "homing", f"dot {e:.3f} mm off the crosshair: run VISION_HOME (if it was just "
                            "run, the down camera or the datum moved)"))
            else:
                add(Finding("OK", "homing", f"dot {e:.3f} mm from the crosshair"))
            add(_map_check("down camera map", down["grab"], down["locate"], mr.move_rel, down["motion"], 1.0,
                           "calibrate-motion --cam down, then calibrate-offset/place-test offset (rows 4, 7, 7b)"))

    # -- up camera on the empty nozzle's bore --------------------------------------------------
    old = np.asarray(ms["up_cam_xy_mm"], float)
    mr.move_abs(x=float(old[0]), y=float(old[1]))
    mr.move_abs(z=float(inspect_z), feedrate=300)
    try:
        move_low = lambda dx, dy: mr.move_rel(dx, dy, stay_low=True)
        res = center_on(up["grab"], up["locate"], move_low, up["motion"], up["target_px"],
                        max_step_mm=mr.MAX_LOW_XY_MM * 0.8)
        if not res["converged"]:
            add(Finding("REDO", "up camera", f"could not centre on the nozzle bore ({res.get('reason')}): "
                        "check the tip is fitted and the up light is on (UP_LIGHT_ON); find-dot --cam up"))
        else:
            x, y, _ = mr.position()
            shift = np.array([x, y]) - old
            s = float(np.linalg.norm(shift))
            if s <= NOZZLE_OK_MM:
                add(Finding("OK", "nozzle", f"tip within {s:.3f} mm of the stored centre"))
            elif apply:
                ms["up_cam_xy_mm"] = [float(x), float(y)]
                ms["down_cam_offset_mm"] = (np.asarray(ms["down_cam_offset_mm"], float) + shift).tolist()
                add(Finding("OK", "nozzle", f"tip moved {np.round(shift, 3).tolist()} mm: up-camera centre and "
                            "down-camera offset updated"))
            else:
                add(Finding("REDO", "nozzle", f"tip moved {np.round(shift, 3).tolist()} mm (refitted?): "
                            "re-run with --apply to update the centre and offset"))
            add(_map_check("up camera map", up["grab"], up["locate"], move_low, up["motion"], 0.5,
                           "calibrate-motion --cam up --step 1 (row 8), then the centre again (row 8b)"))
    finally:
        lift(mr, feedrate=600)
    return out
