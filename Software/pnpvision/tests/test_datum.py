"""Simulated datum: renders the real CAD geometry through a fake down camera, then recovers its pose."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import numpy as np, cv2
from pnpvision.datum import (DatumGeometry, measure_datum, to_datum_xy, to_machine_xy, umeyama)
from pnpvision.motion import MotionMap

G = DatumGeometry()
PRINCIPAL = np.array([640.0, 360.0])


def pose_of(rot_deg, t, s=1.0):
    a = np.radians(rot_deg)
    return {"s": s, "R": np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]]), "t": np.array(t, float)}


def render(cam_xy, M, pose, g=G, line=0.8):
    h, w = 720, 1280
    yy, xx = np.mgrid[0:h, 0:w]
    P = np.stack([xx, yy], -1).reshape(-1, 2).astype(float)
    m = cam_xy - (np.linalg.inv(M) @ (P - PRINCIPAL).T).T       # pixel -> machine mm
    d = to_datum_xy(pose, m)
    gx, gy = d[:, 0] - g.grid_center_mm[0], d[:, 1] - g.grid_center_mm[1]
    hw = g.cols * g.pitch_mm / 2 + line / 2
    hh = g.rows * g.pitch_mm / 2 + line / 2
    white = (np.abs(gx) <= hw) & (np.abs(gy) <= hh)
    uj, ui = gx / g.pitch_mm + (g.cols - 1) / 2, gy / g.pitch_mm + (g.rows - 1) / 2
    j, i = np.rint(uj), np.rint(ui)
    half = (g.pitch_mm - line) / 2
    in_cell = ((j >= 0) & (j < g.cols) & (i >= 0) & (i < g.rows)
               & (np.abs((uj - j) * g.pitch_mm) < half) & (np.abs((ui - i) * g.pitch_mm) < half))
    white &= ~in_cell
    for dot in g.dots_mm:
        white |= np.hypot(*(d - dot).T) <= g.dot_diameter_mm / 2
    img = np.where(white, 225, 28).astype(np.uint8).reshape(h, w)
    img = cv2.GaussianBlur(img, (0, 0), 1.0)
    noise = np.random.default_rng(0).normal(0, 2, img.shape)
    return np.clip(img + noise, 0, 255).astype(np.uint8)


def run(true_rot, prior, grid_err=(0.8, -0.6)):
    th = np.radians(7)
    M = -40.0 * np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]]) @ np.diag([1, -1])
    motion = MotionMap(M, "camera")
    pose_true = pose_of(true_rot, (120.3, 85.2))
    cam_offset = np.array([-32.1, 4.7])
    view = lambda x, y: render(np.array([x, y]) + cam_offset, M, pose_true)
    to_m = lambda px, x, y: np.array([x, y]) + cam_offset + motion.offset_mm(np.array(px) - PRINCIPAL)
    gc = to_machine_xy(pose_true, G.grid_center_mm)
    start = gc - cam_offset + np.array(grid_err)
    r_px = G.dot_diameter_mm / 2 / motion.mm_per_px
    out = measure_datum(view, to_m, G, start, cam_offset, prior, r_px, PRINCIPAL)
    # compare in machine space at the dots and grid
    pts = np.array(G.dots_mm + (G.grid_center_mm,))
    err = np.linalg.norm(to_machine_xy(out, pts) - to_machine_xy(pose_true, pts), axis=1).max()
    return out, err


def test_pose_recovered():
    out, err = run(3.0, prior=0.0)
    print("rot", round(out["rot_deg"], 3), "scale", round(out["s"], 5), "rms mm", round(out["rms_mm"], 4), "max err mm", round(err, 4))
    assert err < 0.02 and abs(out["s"] - 1) < 5e-4 and abs(out["rot_deg"] - 3.0) < 0.1


def test_resolves_180_symmetry_with_prior():
    out, err = run(183.0, prior=180.0)
    assert err < 0.02 and abs((out["rot_deg"] - 183.0 + 180) % 360 - 180) < 0.1


def test_wrong_prior_is_caught():
    try:
        run(3.0, prior=180.0)       # tells it the datum is turned around -> dots won't be where predicted
    except Exception as e:
        print("caught:", type(e).__name__, e); return
    raise AssertionError("should have failed")


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS", n)
