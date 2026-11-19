"""place_test against a simulated machine: toolhead, valve, parts that stick to the nozzle,
a down camera that sees parts (tan body, metal ends) and copper pads from above, and an up
camera that sees the part on the nozzle. The first part is aimed by hand; the rest are found
from a picture of the first one."""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pnpvision.motion import MotionMap
from pnpvision.detect import measure_part
from pnpvision.placetest import PartFinder, place_test, summarize
from pnpvision.rotation import Rotator, rotate_xy, shortest_turn

OFF_SET = np.array([8.328, 53.059])          # what the software believes
OFF_TRUE = OFF_SET + [0.12, -0.08]           # what the machine really has (calibration error)
UP_XY = np.array([85.84, 137.70])
DOWN_M = np.array([[-58.5, 0.4], [-0.3, 59.0]])     # camera moves (down cam, ~59 px/mm at the board)
UP_M = np.array([[0.27, -37.3], [38.6, 0.08]])      # target moves (up cam, 90 deg turned)
P_DOWN = np.array([960.0, 540.0])
P_UP = np.array([724.7, 382.6])
L_MM, W_MM, T_MM, WD = 2.0, 1.25, 0.85, 11.5
K = WD / (WD - T_MM)                                 # part tops look this much bigger / further out
FIRST = np.array([165.0, 252.7])
TARGETS = [np.array([155.39, 267.7]) + [-4.0 * i, 0] for i in range(3)]
TRUE_DIR = -1.0                                      # part deg per motor deg (measured)
PADS = [FIRST + d for d in ((-3.0, 2.5), (-1.6, 2.5), (4.0, -3.5), (5.4, -3.5), (2.5, 4.0), (-7.0, -3.0))]


class World:
    """Positions in 'down camera centred' coordinates. The nozzle tip is at toolhead - OFF_TRUE."""
    def __init__(self, parts, slip=(0.05, -0.03)):
        self.xyz = [FIRST[0] + 0.08, FIRST[1] - 0.06, 30.0]   # you centred the camera by eye
        self.safe_travel_z = 30.0
        self.parts = list(parts)        # (xy, angle_deg, stuck) lying on the board
        self.held = None                # (offset from the nozzle axis, machine-frame angle)
        self.slip = np.array(slip)
        self.motor = 0.0

    def position(self):
        return tuple(self.xyz)

    def move_abs(self, x=None, y=None, z=None, feedrate=None):
        if (x is not None or y is not None) and self.xyz[2] > self.safe_travel_z + 1e-6:
            self.xyz[2] = self.safe_travel_z        # same lift rule as Moonraker.move_abs
        if x is not None:
            self.xyz[0] = x
        if y is not None:
            self.xyz[1] = y
        if z is not None:
            self.xyz[2] = z

    def nozzle(self):
        return np.array(self.xyz[:2]) - OFF_TRUE

    def gcode(self, script):
        for line in script.splitlines():
            if line.startswith("VALVE_ON") and self.held is None and self.xyz[2] > 37.3:
                for i, (p, ang, stuck) in enumerate(self.parts):
                    if np.linalg.norm(p - self.nozzle()) < 0.6 and not stuck:
                        # board parts: `ang` 0 = long axis along machine Y (machine angle 90)
                        self.held = (p - self.nozzle() + self.slip, ang + 90.0)
                        self.parts.pop(i)
                        break
            elif line.startswith("VALVE_OFF") and self.held is not None:
                if self.xyz[2] > 37.3:
                    self.parts.append((self.nozzle() + self.held[0], self.held[1] - 90.0, False))
                self.held = None
            elif line.startswith("MANUAL_STEPPER"):
                m = float(line.split("MOVE=")[1].split()[0])
                d = TRUE_DIR * (m - self.motor)
                self.motor = m
                if self.held is not None:
                    self.held = (rotate_xy(self.held[0], d), self.held[1] + d)

    @staticmethod
    def _box(img, c, ax, ay, colour):
        pts = np.array([c + s * ax / 2 + t * ay / 2 for s, t in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
        cv2.fillPoly(img, [np.round(pts * 16).astype(np.int32)], colour, cv2.LINE_AA, 4)

    def down_frame(self):
        img = np.full((1080, 1920, 3), (60, 120, 40), np.uint8)      # green board (BGR)
        cam = np.array(self.xyz[:2])
        for p in PADS:                                                 # bare copper pads
            self._box(img, P_DOWN + DOWN_M @ (cam - p), DOWN_M @ np.array([0, -1.0]),
                      DOWN_M @ np.array([-1.0, 0]), (190, 200, 205))
        for p, ang, _ in self.parts:                                   # tan body, metal ends
            a = np.radians(ang)
            u = np.array([-np.sin(a), np.cos(a)])                      # long axis (machine Y at 0 deg)
            v = np.array([np.cos(a), np.sin(a)])
            c = P_DOWN + K * (DOWN_M @ (cam - p))
            self._box(img, c, K * (DOWN_M @ (-L_MM * u)), K * (DOWN_M @ (-W_MM * v)), (90, 140, 170))
            for s in (-1, 1):
                ce = P_DOWN + K * (DOWN_M @ (cam - (p + s * 0.8 * u)))
                self._box(img, ce, K * (DOWN_M @ (-0.4 * u)), K * (DOWN_M @ (-W_MM * v)), (200, 205, 210))
        noise = np.random.default_rng(int(cam.sum() * 100) % 1000).normal(0, 3, img.shape)
        return np.clip(img + noise, 0, 255).astype(np.uint8)

    def up_inspect(self, size):
        img = np.full((720, 1280), 105, np.uint8)
        if self.held is not None and np.linalg.norm(np.array(self.xyz[:2]) - UP_XY) < 0.01:
            q = self.nozzle() + self.held[0] - (UP_XY - OFF_TRUE)
            a = np.radians(self.held[1])
            lv, sv = np.array([np.cos(a), np.sin(a)]), np.array([-np.sin(a), np.cos(a)])
            self._box(img, P_UP + UP_M @ q, UP_M @ (L_MM * lv), UP_M @ (W_MM * sv), 200)
        um = MotionMap(UP_M, "target")
        pm = measure_part(img, P_UP, 3.0 / um.mm_per_px, expected_px=(L_MM / um.mm_per_px, W_MM / um.mm_per_px))
        if pm is None:
            return {"ok": False, "reason": "no part found"}
        return {"ok": True, "reason": "", "offset_mm": um.offset_mm(np.array(pm.center_px) - P_UP).tolist(),
                "angle_deg": float(um.direction_mm(pm.angle_px_deg)), "size_mm": [pm.long_px * um.mm_per_px, pm.short_px * um.mm_per_px]}


def _run(correct, rotate_to=None):
    # first part (aimed by hand), a stuck one nearby, three more dropped loosely by hand
    parts = [(FIRST, 0.0, False), (FIRST + (-2.6, 0.3), 5.0, True), (FIRST + (4.2, 1.0), -8.0, False),
             (FIRST + (-6.0, -2.0), 92.0, False), (FIRST + (9.0, 3.5), 178.0, False)]
    w = World(parts)
    ms = {"down_cam_offset_mm": OFF_SET.tolist(), "up_cam_xy_mm": UP_XY.tolist()}
    mm = MotionMap(DOWN_M, "camera")
    finder = PartFinder(w, w.down_frame, mm, P_DOWN, (L_MM, W_MM), K, np.array(w.xyz[:2]),
                        avoid=TARGETS, say=lambda *a: None)
    rot = Rotator(w.gcode, direction=TRUE_DIR) if rotate_to is not None else None
    res = place_test(w, w.down_frame, mm, P_DOWN, w.up_inspect, ms, finder, TARGETS,
                     thickness_mm=T_MM, working_distance_mm=WD, correct=correct, say=lambda *a: None,
                     rotator=rot, rotate_to=rotate_to)
    return w, res, summarize(res, OFF_SET, correct)


def test_place_test_uncorrected_measures_offset_error():
    w, res, s = _run(correct=False)
    assert s["ok"] == 3, res
    assert any(r["status"].startswith("pick failed") for r in res), res     # the stuck part
    # every pick is aimed at a real part's true centre (hand-dropped, rotated, among pads)
    real = [FIRST + d for d in ((0, 0), (-2.6, 0.3), (4.2, 1.0), (-6.0, -2.0), (9.0, 3.5))]
    for r in res:
        err = min(np.linalg.norm(np.array(r["picked_from"]) - t) for t in real)
        assert err < 0.05, (r["picked_from"], err)
    assert np.allclose(s["suggested_down_cam_offset_mm"], OFF_TRUE, atol=0.04), s


def test_place_test_corrected_lands_off_by_offset_error():
    w, res, s = _run(correct=True)
    assert s["ok"] == 3, res
    assert np.allclose(s["mean_landing_error_mm"], OFF_SET - OFF_TRUE, atol=0.04), s
    assert np.allclose(s["suggested_down_cam_offset_mm"], OFF_TRUE, atol=0.04), s


def test_shortest_turn():
    assert shortest_turn(0, 95.3) == -95.3 + 180
    assert abs(shortest_turn(0, 36.6) + 36.6) < 1e-9
    assert abs(shortest_turn(30, -84.7) - (-65.3)) < 1e-9
    assert shortest_turn(10, 10) == 0


def test_place_test_rotates_parts_to_target():
    for target in (0.0, 30.0, -60.0):
        w, res, s = _run(correct=True, rotate_to=target)
        assert s["ok"] == 3, res
        assert s["max_abs_angle_error_deg"] < 1.5, s
        # the offset must be re-measured after turning: an off-centre grab swings with the part
        assert np.allclose(s["mean_landing_error_mm"], OFF_SET - OFF_TRUE, atol=0.04), s
        for r in res:
            for t in r.get("turns", []):
                got = np.array(t["inspect"]["offset_mm"])
                assert np.linalg.norm(got - t["predicted_offset_mm"]) < 0.03, t


def test_place_test_angle_sweep():
    w, res, s = _run(correct=True, rotate_to=[0.0, 60.0, 120.0])
    assert s["ok"] == 3, res
    assert s["angle_targets_deg"] == [0.0, 60.0, 120.0], s
    assert s["max_abs_angle_error_deg"] < 1.5, s


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS", n)
