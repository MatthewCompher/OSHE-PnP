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


def repeatability_test(grab, locate, motion, move_abs, position, n=20, radius_mm=(30.0, 80.0),
                       limits=None, home=None, home_every=0, ref_shots=3, seed=None, log=print):
    """Return-to-position test. The toolhead starts over a fixed feature (down cam,
    moving="camera"). Each cycle travels to a far point and comes back to the same
    commanded XY; the feature's pixel shift, mapped through `motion`, is how far the
    toolhead actually landed from where it landed the first time.

    Far points cycle through 8 compass directions (so every approach side is covered
    equally) at a random distance in radius_mm, shortened to stay inside `limits`
    {"x": (lo, hi), "y": (lo, hi)}. home(): optional re-home every `home_every` cycles.
    Returns dict(cycles=[...], summary={...})."""
    rng = np.random.default_rng(seed)
    x0, y0 = position()[:2]

    def measure():
        d = locate(grab())
        if d is None:
            raise RuntimeError("feature lost - is it still in view?")
        return np.array(d.center_px, float)

    # Reference = average of a few shots without moving; their spread is the noise floor.
    shots = np.array([measure() for _ in range(max(1, ref_shots))])
    ref_px = shots.mean(axis=0)
    noise_mm = np.abs((shots - ref_px) @ motion.Minv.T).max(axis=0)
    log(f"start XY ({x0:.3f}, {y0:.3f}); camera/detection noise ~{noise_mm.round(4).tolist()} mm")

    cycles = []
    for i in range(n):
        ang = np.radians(45.0 * (i % 8) + rng.uniform(-10, 10))
        u = np.array([np.cos(ang), np.sin(ang)])
        r = rng.uniform(*radius_mm)
        if limits:                                   # shorten to stay inside the travel limits
            for k, axis in enumerate("xy"):
                lo, hi = limits[axis]
                p0 = (x0, y0)[k]
                if u[k] > 1e-9:
                    r = min(r, (hi - p0) / u[k])
                elif u[k] < -1e-9:
                    r = min(r, (lo - p0) / u[k])
        r = max(r - 0.5, 0.0)
        far = np.array([x0, y0]) + r * u
        move_abs(x=float(far[0]), y=float(far[1]))
        homed = bool(home and home_every and (i + 1) % home_every == 0)
        if homed:
            home()
        move_abs(x=x0, y=y0)
        # Feature shift s = M @ m for a camera move m  ->  landing error m = Minv @ s
        err = motion.Minv @ (measure() - ref_px)
        c = {"i": i + 1, "from_deg": round(float(np.degrees(ang)) % 360, 1), "dist_mm": round(float(r), 1),
             "homed": homed, "err_x_mm": float(err[0]), "err_y_mm": float(err[1])}
        cycles.append(c)
        log(f"{c['i']:3d}  from {c['from_deg']:5.1f} deg, {c['dist_mm']:5.1f} mm{'  (re-homed)' if homed else ''}"
            f"   err X {err[0]:+.4f}  Y {err[1]:+.4f} mm")

    E = np.array([[c["err_x_mm"], c["err_y_mm"]] for c in cycles])
    U = np.array([[np.cos(np.radians(c["from_deg"])), np.sin(np.radians(c["from_deg"]))] for c in cycles])

    def side_gap(k):
        # mean error when the far point was on the + side of this axis minus on the - side
        # (= returning while moving in - vs +): a steady gap is backlash / belt slack.
        plus, minus = E[U[:, k] > 0.3, k], E[U[:, k] < -0.3, k]
        if len(plus) and len(minus):
            return float(plus.mean() - minus.mean())
        return None

    summary = {
        "n": len(cycles),
        "noise_floor_mm": noise_mm.round(4).tolist(),
        "std_mm": E.std(axis=0).round(4).tolist() if len(E) else None,
        "max_abs_mm": np.abs(E).max(axis=0).round(4).tolist() if len(E) else None,
        "max_radial_mm": round(float(np.hypot(E[:, 0], E[:, 1]).max()), 4) if len(E) else None,
        "mean_mm": E.mean(axis=0).round(4).tolist() if len(E) else None,
        "direction_gap_mm": [None if g is None else round(g, 4) for g in (side_gap(0), side_gap(1))],
        "drift_mm_over_run": (np.polyfit(np.arange(len(E)), E, 1)[0] * (len(E) - 1)).round(4).tolist()
        if len(E) > 2 else None,
    }
    if any(c["homed"] for c in cycles):
        H = E[[c["homed"] for c in cycles]]
        summary["after_rehome_max_abs_mm"] = np.abs(H).max(axis=0).round(4).tolist()
    return {"cycles": cycles, "summary": summary}


def visual_home(grab, locate, motion, target_px, move_abs, position, set_xy, taught_xy,
                home=None, tol_mm=0.01, log=print):
    """Homing-fiducial correction. Sensorless X/Y homing lands up to ~2 mm off; a fixed dot
    (datum dot 0) does not move. Optionally home(), go to where the down camera sat centred
    over the dot when it was taught, centre on it, then declare "this is taught_xy" with
    set_xy(x, y) (SET_KINEMATIC_POSITION). Only shifts the frame (homing never rotates it).
    Returns dict(homing_error_mm=[dx, dy] = where the frame was vs the taught one, ...)."""
    if home:
        home()
    tx, ty = float(taught_xy[0]), float(taught_xy[1])
    move_abs(x=tx, y=ty)

    def move_rel(dx, dy):
        x, y = position()[:2]
        move_abs(x=x + dx, y=y + dy)

    res = center_on(grab, locate, move_rel, motion, target_px, tol_mm=tol_mm, max_iter=8)
    if not res["converged"]:
        raise RuntimeError(f"visual home: could not centre on the homing dot ({res}). "
                           "Is it in view near the taught position, lit, and detected with the "
                           "taught settings?")
    mx, my = position()[:2]
    err = [mx - tx, my - ty]          # commanded XY that actually put the camera over the dot
    set_xy(tx, ty)
    log(f"visual home: frame was off by X {err[0]:+.4f} Y {err[1]:+.4f} mm; "
        f"position reset to X{tx:.4f} Y{ty:.4f}")
    return {"homing_error_mm": err, "centering": res}
