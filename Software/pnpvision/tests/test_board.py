"""Board alignment against a simulated down camera that sees every chip-resistor pad of the real
Test PCB job (so each alignment pad has its look-alike twin 1-2 mm away), plus pad detection
on a real photo."""
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
from pnpvision.board import BoardPose, align_board, choose_consistent, find_pads, fit_rigid
from pnpvision.motion import MotionMap

JOB = os.path.join(HERE, "..", "jobs", "Test PCB-top.job.json")
DOWN_M = np.array([[-58.67882222945361, 0.5203888122025544],
                   [0.6450336639632039, 59.203353131808996]])      # real map, 2026-11-11 (mirrored)
P_DOWN = np.array([877.6, 635.9])
# KiCad R_xxxx footprints: pad size (along the part, across) and pad centre distance from the part centre
PADS = {"R_0201_0603Metric": (0.46, 0.4, 0.32), "R_0402_1005Metric": (0.54, 0.64, 0.51),
        "R_0603_1608Metric": (0.8, 0.95, 0.825), "R_0805_2012Metric": (1.025, 1.4, 0.9125)}


def _rot(a):
    a = np.radians(a)
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


class Sim:
    def __init__(self, job, true_pose, start):
        self.xyz = [start[0], start[1], 30.0]
        self.pose = true_pose
        self.pads = []      # (machine centre, along-axis unit vector, w, h)
        for p in job["placements"]:
            w, h, d = PADS[p["package"]]
            ax = _rot(p["rot"] + true_pose.angle_deg) @ np.array([1.0, 0.0])
            c = true_pose.to_machine([p["x"], p["y"]])
            for s in (-1, 1):
                self.pads.append((c + s * d * ax, ax, w, h))
        self.rng = np.random.default_rng(1)

    def move_abs(self, x=None, y=None, z=None, feedrate=None):
        if x is not None:
            self.xyz[0] = x
        if y is not None:
            self.xyz[1] = y

    def frame(self):
        img = np.full((1080, 1920, 3), (130, 150, 5), np.uint8)          # saturated green mask
        cam = np.array(self.xyz[:2])
        for c, ax, w, h in self.pads:
            if np.linalg.norm(c - cam) > 20:
                continue
            ay = np.array([-ax[1], ax[0]])
            pts = [c + sx * w / 2 * ax + sy * h / 2 * ay for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            px = np.array([P_DOWN + DOWN_M @ (cam - q) for q in pts])
            cv2.fillPoly(img, [np.round(px * 16).astype(np.int32)], (175, 165, 150), cv2.LINE_AA, 4)
        noise = self.rng.normal(0, 6, img.shape)
        return np.clip(img + noise, 0, 255).astype(np.uint8)


def _run(true_angle, start_err, twin=False, rot_guess=90.0):
    job = json.load(open(JOB, encoding="utf-8"))
    true = BoardPose(true_angle, [175.3, 229.6])
    a = job["alignment"][0]
    start = true.to_machine([a["x"], a["y"]]) + start_err
    if twin:      # you centred on the OTHER pad of pad A's resistor
        part = next(p for p in job["placements"] if p["ref"] == a["ref"])
        start = 2 * true.to_machine([part["x"], part["y"]]) - true.to_machine([a["x"], a["y"]]) + start_err
    sim = Sim(job, true, start)
    pose, out = align_board(sim, sim.frame, MotionMap(DOWN_M, "camera"), P_DOWN, job, start, rot_guess,
                            say=lambda *x: None)
    return job, true, pose, out


def test_fit_rigid_and_choose():
    B = np.array([[0, 0], [30, 0], [0, 20.0]])
    true = BoardPose(91.0, [100, 200])
    M = np.array([true.to_machine(b) for b in B])
    ang, t, res, scale = fit_rigid(B, M)
    assert abs(ang - 91.0) < 1e-9 and np.allclose(t, [100, 200]) and abs(scale - 1) < 1e-9
    cands = [[M[0] + [1.8, 0], M[0]], [M[1], M[1] + [0, 1.8]], [M[2] + [1.0, 1.0], M[2]]]
    idx, rms, second = choose_consistent(B, cands)
    assert idx == [1, 0, 1] and rms < 1e-9 and second > 0.3


def test_align_board_simulated():
    for true_angle, err, twin in ((90.0, (0.3, -0.2), False), (92.5, (-0.2, 0.3), True), (87.0, (0.1, 0.1), False)):
        job, true, pose, out = _run(true_angle, np.array(err), twin)
        assert abs(pose.angle_deg - true_angle) < 0.05, (true_angle, pose.angle_deg)
        for p in job["placements"][::10]:
            e = np.linalg.norm(pose.to_machine([p["x"], p["y"]]) - true.to_machine([p["x"], p["y"]]))
            assert e < 0.03, (p["ref"], e)
        assert out["max_residual_mm"] < 0.03, out


def test_pads_found_on_real_photo():
    # 2026-11-11 down camera over the test PCB (tape across the top): the 8 pads of the clean
    # middle block (0603-size) must be found; silkscreen, glare and background are allowed to
    # score, alignment rejects them by geometry.
    img = cv2.imread(os.path.join(HERE, "..", "captures", "2026-11-11", "place_test_20261111_175604", "search1_raw.png"))
    if img is None:
        print("(real photo not available, skipped)")
        return
    hits = find_pads(img, 0.85 * 58.9, 0.95 * 58.9, 0.0, min_score=0.5, margin_px=20, max_hits=60)
    block = [(610, 400), (730, 400), (906, 394), (1140, 394), (610, 496), (734, 496), (906, 490), (1140, 490)]
    got = sum(any(np.linalg.norm(h[0] - b) < 25 for h in hits) for b in block)
    assert got >= 7, (got, [(np.round(h[0]), round(h[1], 2)) for h in hits])


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS", n)
