"""Closed-loop vision moves and motion calibration. Hardware is injected as callables,
so the same code runs against real cameras/Moonraker or a simulator."""
import numpy as np

from .motion import MotionMap


def calibrate_motion(grab, locate, move_rel, step_mm=1.0, moving="camera"):
    """Jog the toolhead +-step in X and Y, track one feature, fit MotionMap.
    grab() -> undistorted frame (already settled); locate(frame) -> object with .center_px.
    Keep step small enough that the feature stays in view (1 mm ~ 40 px at 0.025 mm/px)."""
    def loc():
        d = locate(grab())
        if d is None:
            raise RuntimeError("feature not found during motion calibration")
        return np.array(d.center_px, float)

    here = np.zeros(2)
    moves, pts = [], []

    def goto(target):
        nonlocal here
        dx, dy = target - here
        move_rel(dx, dy)
        here = target.copy()

    for t in ([0, 0], [step_mm, 0], [-step_mm, 0], [0, step_mm], [0, -step_mm], [0, 0]):
        t = np.array(t, float)
        goto(t)
        moves.append(t)
        pts.append(loc())
    p0 = pts[0]
    return MotionMap.fit(moves, [p - p0 for p in pts], moving)


def center_on(grab, locate, move_rel, motion, target_px, tol_mm=0.02,
              max_iter=6, max_step_mm=5.0):
    """Iteratively move the toolhead until the located feature sits at target_px.
    Returns dict(converged, iters, err_mm, last_err_px)."""
    err_mm = None
    for i in range(1, max_iter + 1):
        d = locate(grab())
        if d is None:
            return {"converged": False, "iters": i, "err_mm": err_mm, "reason": "not found"}
        err_px = np.array(d.center_px, float) - np.asarray(target_px, float)
        err_mm = float(np.linalg.norm(motion.offset_mm(err_px)))
        if err_mm <= tol_mm:
            return {"converged": True, "iters": i, "err_mm": err_mm, "last_err_px": err_px.tolist()}
        mv = motion.to_move_mm(err_px)
        n = np.linalg.norm(mv)
        if n > max_step_mm:                       # never take a wild step on a bad detection
            mv *= max_step_mm / n
        move_rel(float(mv[0]), float(mv[1]))
    return {"converged": False, "iters": max_iter, "err_mm": err_mm, "reason": "max_iter"}
