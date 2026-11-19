"""Board alignment: find the job's alignment pads with the down camera and fit where the board
lies on the plate (position + rotation).

Coordinates: "down camera centred" toolhead XY, like place-test (the nozzle goes over such a
point at point + down_cam_offset_mm). Board frame: the job file's (oshe-pnp-job/1).

Pads are found by matching a pad-shaped template on the SATURATION channel: the solder mask is
almost fully saturated green (S ~250) while copper/HASL, silkscreen, tape and the background
are not; pads look bright, dark or sparkly depending on the light, but never saturated green
(2026-11-11 photos: brightness thresholds missed the darker pads, S thresholds merged pads with
silkscreen). Each pad of a chip resistor has a twin 1-2 mm away, so the pads are chosen as the
COMBINATION of candidates whose distances match the job, not one by one.
"""
import itertools
import json
import time

import cv2
import numpy as np


# -- pad detection -------------------------------------------------------------
def pad_template(w_px, h_px, ang_px_deg, margin_px):
    """Pad (dark = low saturation) inside a ring of solder mask (bright = saturated)."""
    R = int(np.hypot(w_px, h_px) / 2 + margin_px) + 2
    t = np.full((2 * R + 1, 2 * R + 1), 255, np.float32)
    box = cv2.boxPoints(((R, R), (w_px, h_px), ang_px_deg))
    cv2.fillPoly(t, [np.round(box * 16).astype(np.int32)], 0, cv2.LINE_AA, 4)
    m = np.zeros_like(t)
    box2 = cv2.boxPoints(((R, R), (w_px + 2 * margin_px, h_px + 2 * margin_px), ang_px_deg))
    cv2.fillPoly(m, [np.round(box2).astype(np.int32)], 1.0)
    return t, m


def find_pads(img, w_px, h_px, ang_px_deg, center_px=None, radius_px=None, min_score=0.5,
              margin_px=20, max_hits=12):
    """Pad-shaped spots, best first: [(xy_px, score)]. Sub-pixel from the score peak."""
    s = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)[..., 1].astype(np.float32)
    t, m = pad_template(w_px, h_px, ang_px_deg, margin_px)
    R = t.shape[0] // 2
    x0 = y0 = 0
    if center_px is not None and radius_px is not None:
        x0 = max(int(center_px[0] - radius_px - R), 0)
        y0 = max(int(center_px[1] - radius_px - R), 0)
        x1 = min(int(center_px[0] + radius_px + R) + 1, s.shape[1])
        y1 = min(int(center_px[1] + radius_px + R) + 1, s.shape[0])
        s = s[y0:y1, x0:x1]
    if s.shape[0] <= t.shape[0] or s.shape[1] <= t.shape[1]:
        return []
    r = np.nan_to_num(cv2.matchTemplate(s, t, cv2.TM_CCOEFF_NORMED, mask=m), nan=0.0, posinf=0.0, neginf=0.0)
    work, hits = r.copy(), []
    sep = int(0.6 * min(w_px, h_px))
    while len(hits) < max_hits:
        _, v, _, p = cv2.minMaxLoc(work)
        if v < min_score:
            break
        x, y = p
        dx = dy = 0.0
        if 0 < x < r.shape[1] - 1:
            a, b, c = r[y, x - 1], r[y, x], r[y, x + 1]
            dx = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) < 0 else 0.0
        if 0 < y < r.shape[0] - 1:
            a, b, c = r[y - 1, x], r[y, x], r[y + 1, x]
            dy = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) < 0 else 0.0
        xy = np.array([x + dx + R + x0, y + dy + R + y0])
        if center_px is None or radius_px is None or np.linalg.norm(xy - center_px) <= radius_px:
            hits.append((xy, float(v)))
        cv2.circle(work, p, sep, -1.0, -1)
    return hits


def px_angle(motion, machine_deg):
    """Machine-frame direction -> image direction (deg) through the motion map."""
    a = np.radians(machine_deg)
    d = motion.M @ np.array([np.cos(a), np.sin(a)])
    return float(np.degrees(np.arctan2(d[1], d[0])))


def pad_size_mm(pad):
    if pad["shape"] == "circle":
        return pad["d"], pad["d"]
    return pad["w"], pad["h"]


# -- geometry ------------------------------------------------------------------
def fit_rigid(board_pts, machine_pts):
    """machine = R(angle) @ board + t, least squares. Returns angle_deg, t, residuals (mm),
    scale (from a similarity fit, for information: should be ~1)."""
    B = np.asarray(board_pts, float)
    Mp = np.asarray(machine_pts, float)
    bc, mc = B.mean(0), Mp.mean(0)
    H = (B - bc).T @ (Mp - mc)
    U, S, Vt = np.linalg.svd(H)
    D = np.diag([1.0, np.sign(np.linalg.det(Vt.T @ U.T))])
    Rm = Vt.T @ D @ U.T
    t = mc - Rm @ bc
    res = Mp - (B @ Rm.T + t)
    scale = float(S.sum() / max(((B - bc) ** 2).sum(), 1e-12))
    return float(np.degrees(np.arctan2(Rm[1, 0], Rm[0, 0]))), t, res, scale


def choose_consistent(board_pts, candidates):
    """candidates[i] = list of machine XY for pad i. Pick one per pad so the pairwise distances
    match the board best. Returns (indices, rms_mm, second_best_rms_mm)."""
    B = np.asarray(board_pts, float)
    n = len(B)
    pairs = list(itertools.combinations(range(n), 2))
    dB = {(i, j): np.linalg.norm(B[i] - B[j]) for i, j in pairs}
    scored = []
    for combo in itertools.product(*[range(len(c)) for c in candidates]):
        P = [np.asarray(candidates[i][k], float) for i, k in enumerate(combo)]
        e = [np.linalg.norm(P[i] - P[j]) - dB[i, j] for i, j in pairs]
        scored.append((float(np.sqrt(np.mean(np.square(e)))), combo))
    scored.sort()
    if not scored:
        return None, None, None
    second = scored[1][0] if len(scored) > 1 else float("inf")
    return list(scored[0][1]), scored[0][0], second


class BoardPose:
    """machine (camera-centred) XY = R(angle) @ board XY + t"""

    def __init__(self, angle_deg, t):
        self.angle_deg, self.t = float(angle_deg), np.asarray(t, float)

    def to_machine(self, b):
        a = np.radians(self.angle_deg)
        Rm = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        return Rm @ np.asarray(b, float) + self.t

    def part_angle(self, rot_deg):
        """Job `rot` (board frame, CCW) -> machine-frame angle."""
        return float(rot_deg) + self.angle_deg

    def to_dict(self):
        return {"angle_deg": self.angle_deg, "t": self.t.tolist()}

    @classmethod
    def from_dict(cls, d):
        return cls(d["angle_deg"], d["t"])


# -- the alignment run -----------------------------------------------------------
def align_board(mr, grab, motion, principal, job, start_xy, rot_guess_deg, search_mm=3.0,
                min_score=0.5, say=print, save=None):
    """You centre the down camera on (either pad of the part holding) alignment pad A.
    Returns a dict with the pose and per-pad results; raises RuntimeError if not sure."""
    save = save or (lambda name, img: None)
    principal = np.asarray(principal, float)
    pads = job["alignment"]
    if len(pads) < 2:
        raise RuntimeError("job has fewer than 2 alignment pads")
    ppm = 1.0 / motion.mm_per_px
    B = np.array([[p["x"], p["y"]] for p in pads], float)
    guess = BoardPose(rot_guess_deg, np.zeros(2))
    guess.t = np.asarray(start_xy, float) - guess.to_machine(B[0])

    def detect(p, xy, radius_mm):
        w, h = pad_size_mm(p)
        ang = px_angle(motion, guess.part_angle(p.get("rot", 0.0)))
        mr.move_abs(x=float(xy[0]), y=float(xy[1]))
        img = np.mean([grab().astype(np.float32) for _ in range(2)], axis=0).astype(np.uint8)
        hits = find_pads(img, w * ppm, h * ppm, ang, principal, radius_mm * ppm, min_score,
                         margin_px=0.35 * ppm)
        return img, [(np.asarray(xy, float) + motion.offset_mm(px - principal), sc, px) for px, sc in hits]

    # 1) candidates around each predicted pad
    cands = []
    for i, p in enumerate(pads):
        pred = guess.to_machine(B[i])
        img, hits = detect(p, pred, search_mm)
        vis = img.copy()
        for _, sc, px in hits:
            cv2.circle(vis, (int(px[0]), int(px[1])), int(0.5 * ppm), (0, 0, 255), 3)
            cv2.putText(vis, f"{sc:.2f}", (int(px[0] + 0.6 * ppm), int(px[1])), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        cv2.drawMarker(vis, tuple(int(v) for v in principal), (0, 255, 255), cv2.MARKER_CROSS, 60, 2)
        save(f"pad_{p['name']}_search", vis)
        say(f"  pad {p['name']} ({p.get('ref', '')} {p.get('pad', '')}): {len(hits)} candidate(s) within "
            f"{search_mm} mm of {np.round(pred, 2).tolist()} (scores {', '.join(f'{h[1]:.2f}' for h in hits[:6]) or 'none'})")
        if not hits:
            raise RuntimeError(f"no pad-like spot near pad {p['name']}: board rotation (--rot) or "
                               f"the start position off?")
        cands.append([h[0] for h in hits[:6]])
    # 2) the combination whose distances match the job
    idx, rms, second = choose_consistent(B, cands)
    say(f"  best pad combination: distance rms {rms:.3f} mm (next best {second:.3f} mm)")
    if rms > 0.25:
        raise RuntimeError(f"no combination of pads matches the job's distances (best rms {rms:.2f} mm)")
    if len(pads) >= 2 and second < max(3 * rms, 0.15):
        raise RuntimeError("two pad combinations fit about equally well (look-alike pads): "
                           "choose more distinct alignment pads in the slicer")
    # 3) centre on each chosen pad for the precise position (height-independent at the axis)
    found = []
    for i, p in enumerate(pads):
        xy = np.asarray(cands[i][idx[i]], float)
        for _ in range(2):
            img, hits = detect(p, xy, 0.5)
            if not hits:
                raise RuntimeError(f"lost pad {p['name']} while centring on it")
            xy = min(hits, key=lambda h: np.linalg.norm(h[0] - xy))[0]
        save(f"pad_{p['name']}_centred", img)
        found.append(xy)
    angle, t, res, scale = fit_rigid(B, found)
    pose = BoardPose(angle, t)
    out = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "job_board": job["board"]["name"],
           "side": job["board"]["side"], "pose": pose.to_dict(), "scale": scale,
           "pads": [{"name": p["name"], "board": B[i].tolist(), "machine": found[i].tolist(),
                     "residual_mm": res[i].tolist()} for i, p in enumerate(pads)],
           "max_residual_mm": float(np.linalg.norm(res, axis=1).max())}
    return pose, out
