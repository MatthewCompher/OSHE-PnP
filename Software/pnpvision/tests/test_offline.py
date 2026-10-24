"""Hardware-free tests: run with  python -m pytest -q   (or python tests/test_offline.py)"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np, cv2

from pnpvision.lens import LensModel
from pnpvision.motion import MotionMap
from pnpvision.detect import find_circle, measure_part
from pnpvision.servo import calibrate_motion, center_on
from pnpvision.eventlog import EventLog

CAL = os.path.join(os.path.dirname(os.path.dirname(__file__)), "calibration")


def test_lens_loads_and_undistorts():
    for f in ("calibration_cam_A.npz", "calibration_cam_b.npz"):
        lens = LensModel(os.path.join(CAL, f))
        assert lens.size == (1280, 720)
        out = lens.undistort(np.full((720, 1280, 3), 128, np.uint8))
        assert out.shape == (720, 1280, 3)
        print(f, lens.health())


class World:
    """Simulated down camera over a dot. A camera move m shifts the scene by M @ m."""
    def __init__(self, M_true, dot_mm=(3.0, -2.0)):
        self.M = np.array(M_true); self.cam = np.zeros(2); self.dot = np.array(dot_mm)
    def move_rel(self, dx, dy): self.cam += (dx, dy)
    def grab(self):
        c = np.array([640, 360]) + self.M @ (self.cam - self.dot)
        img = np.full((720, 1280), 220, np.uint8)
        S = 4   # sub-pixel drawing
        cv2.circle(img, (int(round(c[0] * 2**S)), int(round(c[1] * 2**S))), 40 * 2**S, 30, -1,
                   cv2.LINE_AA, shift=S)
        return img


def test_circle_finder():
    img = np.full((720, 1280), 220, np.uint8); cv2.circle(img, (500, 300), 40, 30, -1, cv2.LINE_AA)
    c = find_circle(img, 15, 120)
    assert abs(c.center_px[0] - 500) < 0.6 and abs(c.center_px[1] - 300) < 0.6


def test_calibrate_and_center():
    # true: 40 px/mm, axes flipped in Y and rotated ~5 deg, scene moves opposite to camera
    th = np.radians(5); R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    M_true = -40.0 * R @ np.diag([1, -1])
    w = World(M_true)
    # World.grab: dot px = center + M @ (cam - dot)  (verified by shifts s = M m for a camera move m)
    mm = calibrate_motion(w.grab, lambda f: find_circle(f, 15, 120), w.move_rel, 1.0, "camera")
    assert np.allclose(mm.M, M_true, atol=1.0), mm.M
    assert abs(mm.mm_per_px - 1 / 40) < 5e-4
    res = center_on(w.grab, lambda f: find_circle(f, 15, 120), w.move_rel, mm, (640, 360), tol_mm=0.02)
    assert res["converged"], res
    assert np.linalg.norm(w.cam - w.dot) < 0.05, (w.cam, w.dot)


def test_measure_part_up_camera():
    img = np.full((720, 1280), 60, np.uint8)
    rect = ((650.0, 350.0), (80.0, 40.0), 30.0)      # 80x40 px part rotated 30 deg
    cv2.fillPoly(img, [cv2.boxPoints(rect).astype(np.int32)], 200)
    p = measure_part(img, (640, 360), 200)
    assert p is not None
    assert abs(p.center_px[0] - 650) < 1 and abs(p.center_px[1] - 350) < 1
    assert abs(p.long_px - 80) < 2 and abs(p.short_px - 40) < 2
    assert abs(p.angle_px_deg - 30) < 2
    # px->machine with a mirrored up camera (target moves): 40 px/mm, y flipped
    mm = MotionMap(np.diag([40.0, -40.0]), "target")
    off = mm.offset_mm(np.array(p.center_px) - (640, 360))
    assert np.allclose(off, [0.25, 0.25], atol=0.03), off     # (+10px,-10px) -> (+0.25,+0.25) mm
    assert abs(mm.direction_mm(30) - (-30)) < 2                # mirror flips angle sense


def test_eventlog_cph():
    log = EventLog(os.path.join(tempfile.mkdtemp(), "t.sqlite"))
    for i in range(11): log.log("place", ok=True, ts=1000 + i * 4.0)   # 4 s per part
    assert abs(log.cph() - 900) < 1


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS", n)
