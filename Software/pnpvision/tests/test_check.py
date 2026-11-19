"""check-machine against a simulated gantry: nothing changed / nozzle refitted off-centre /
down camera twisted / printer.cfg section lost."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pnpvision.check import REQUIRED_OBJECTS, check_machine, map_error
from pnpvision.motion import MotionMap

DOWN_M = np.array([[-58.679, 0.520], [0.645, 59.203]])
UP_M = np.array([[0.274, -37.309], [38.616, 0.077]])
DOT = np.array([40.0, 60.0])            # toolhead XY that centres the down camera on the homing dot
UP_XY = np.array([85.841, 137.697])
PRINC_D = np.array([877.6, 635.9])
PRINC_U = np.array([640.0, 360.0])


def rot(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


class Dot:
    def __init__(self, px):
        self.center_px = tuple(px)


class Gantry:
    MAX_LOW_XY_MM = 3.0
    safe_travel_z = 30.0

    def __init__(self, nozzle_shift=(0.0, 0.0), down_twist_deg=0.0, objects=None, home_err=(0.0, 0.0)):
        self.xyz = [100.0, 100.0, 30.0]
        self.nozzle_shift = np.asarray(nozzle_shift, float)
        self.true_down_M = rot(down_twist_deg) @ DOWN_M
        self.objs = list(REQUIRED_OBJECTS) if objects is None else objects
        self.home_err = np.asarray(home_err, float)

    # machine
    def objects(self):
        return self.objs

    def is_homed(self):
        return True

    def position(self):
        return tuple(self.xyz)

    def move_abs(self, x=None, y=None, z=None, feedrate=None, stay_low=False):
        if (x is not None or y is not None) and not stay_low and self.xyz[2] > self.safe_travel_z:
            self.xyz[2] = self.safe_travel_z
        for i, v in enumerate((x, y, z)):
            if v is not None:
                self.xyz[i] = v

    def move_rel(self, dx=0.0, dy=0.0, dz=0.0, feedrate=None, stay_low=False):
        x, y, z = self.xyz
        self.move_abs(x + dx, y + dy, z + dz if dz else None, stay_low=stay_low)

    # cameras: pixel = principal + M @ (toolhead - where the feature is centred)
    def down_px(self):
        p = PRINC_D + self.true_down_M @ (np.array(self.xyz[:2]) - DOT - self.home_err)
        return p if np.all(np.abs(p - PRINC_D) < 500) else None

    def up_px(self):
        if self.xyz[2] < 34.0:
            return None
        return PRINC_U + UP_M @ (np.array(self.xyz[:2]) - UP_XY + self.nozzle_shift)


def _cams(g):
    down = {"grab": g.down_px, "locate": lambda px: None if px is None else Dot(px),
            "motion": MotionMap(DOWN_M, "camera"), "target_px": PRINC_D}
    up = {"grab": g.up_px, "locate": lambda px: None if px is None else Dot(px),
          "motion": MotionMap(UP_M, "target"), "target_px": PRINC_U}
    return down, up


def _ms():
    return {"visual_home": {"xy": DOT.tolist()}, "up_cam_xy_mm": UP_XY.tolist(),
            "down_cam_offset_mm": [8.385, 52.930]}


def _levels(found):
    return {f.what: f.level for f in found}


def test_map_error():
    assert np.allclose(map_error(DOWN_M, (1, 0), DOWN_M @ [1, 0]), (0, 0), atol=1e-9)
    s, a = map_error(DOWN_M, (1, 0), rot(2.0) @ DOWN_M @ [1, 0] * 1.05)
    assert abs(s - 0.05) < 1e-6 and abs(abs(a) - 2.0) < 1e-6, (s, a)


def test_all_ok():
    g = Gantry()
    down, up = _cams(g)
    found = check_machine(g, _ms(), down, up, 34.5, say=lambda *a: None)
    assert all(f.level == "OK" for f in found), [str(f) for f in found]
    assert g.xyz[2] == 30.0                                          # nozzle lifted at the end


def test_nozzle_refitted():
    g = Gantry(nozzle_shift=(0.2, -0.15))
    down, up = _cams(g)
    ms = _ms()
    found = check_machine(g, ms, down, up, 34.5, say=lambda *a: None)
    assert _levels(found)["nozzle"] == "REDO" and ms["up_cam_xy_mm"] == UP_XY.tolist()
    ms = _ms()
    found = check_machine(g, ms, down, up, 34.5, apply=True, say=lambda *a: None)
    assert _levels(found)["nozzle"] == "OK", [str(f) for f in found]
    shift = np.subtract(ms["up_cam_xy_mm"], UP_XY)
    assert np.allclose(shift, [-0.2, 0.15], atol=0.03), shift
    assert np.allclose(np.subtract(ms["down_cam_offset_mm"], [8.385, 52.930]), shift)


def test_down_camera_twisted_and_not_homed():
    g = Gantry(down_twist_deg=3.0, home_err=(0.3, 0.0))
    down, up = _cams(g)
    lv = _levels(check_machine(g, _ms(), down, up, 34.5, say=lambda *a: None))
    assert lv["down camera map"] == "REDO" and lv["homing"] == "REDO", lv
    assert lv["nozzle"] == "OK", lv


def test_printer_cfg_section_lost():
    g = Gantry(objects=[o for o in REQUIRED_OBJECTS if o != "manual_stepper stepper_r"])
    down, up = _cams(g)
    found = check_machine(g, _ms(), down, up, 34.5, say=lambda *a: None)
    f = found[0]
    assert f.level == "REDO" and "stepper_r" in f.text, str(f)


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS", n)
