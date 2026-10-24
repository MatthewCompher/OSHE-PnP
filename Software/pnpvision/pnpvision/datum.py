"""Datum finder: a 4x3 cell grid (white lines on black) plus three isolated dots.

The grid is measured by its 12 enclosed black CELLS (centroids are immune to line-width
error). The camera field of view (~30x17 mm) cannot hold grid and dots at once, so the
procedure is multi-view: fit the grid, predict where the dots are, drive the camera to
each, then fit everything together in MACHINE coordinates.

Datum frame: origin lower-left dot, +Y toward top of the drawing, viewed from above.
Pose = similarity transform datum -> machine:  m = s * R @ d + t
(s should be ~1.000; a different value means the print or the machine's steps/mm is off.)
"""
from dataclasses import dataclass

import cv2
import numpy as np

from .detect import find_circles


class DatumError(RuntimeError):
    pass


@dataclass
class DatumGeometry:
    pitch_mm: float = 4.0
    cols: int = 4
    rows: int = 3
    grid_center_mm: tuple = (15.0, 40.0)
    dots_mm: tuple = ((0.0, 0.0), (0.0, 30.0), (40.0, 40.0))
    dot_diameter_mm: float = 3.0

    @classmethod
    def from_cfg(cls, d):
        return cls(d["pitch_mm"], d["cols"], d["rows"], tuple(d["grid_center_mm"]),
                   tuple(tuple(p) for p in d["dots_mm"]), d["dot_diameter_mm"])

    def cell_xy(self, i, j):
        """Datum XY of the cell in row i (0 = lowest Y), column j (0 = lowest X)."""
        return (self.grid_center_mm[0] + (j - (self.cols - 1) / 2) * self.pitch_mm,
                self.grid_center_mm[1] + (i - (self.rows - 1) / 2) * self.pitch_mm)


# ---- transforms ----------------------------------------------------------------------
def umeyama(src, dst):
    """Best proper similarity (no reflection) mapping src -> dst, both (N,2)."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    mu_s, mu_d = src.mean(0), dst.mean(0)
    S, D = src - mu_s, dst - mu_d
    U, sig, Vt = np.linalg.svd(D.T @ S / len(src))
    E = np.diag([1.0, 1.0 if np.linalg.det(U) * np.linalg.det(Vt) >= 0 else -1.0])
    R = U @ E @ Vt
    s = float((sig * np.diag(E)).sum() / ((S ** 2).sum() / len(src)))
    t = mu_d - s * R @ mu_s
    res = dst - (s * src @ R.T + t)
    return {"s": s, "R": R, "t": t,
            "rot_deg": float(np.degrees(np.arctan2(R[1, 0], R[0, 0]))),
            "rms_mm": float(np.sqrt((res ** 2).sum(1).mean()))}


def to_machine_xy(pose, d):
    return pose["s"] * np.asarray(d, float) @ pose["R"].T + pose["t"]


def to_datum_xy(pose, m):
    return (np.asarray(m, float) - pose["t"]) @ pose["R"] / pose["s"]


# ---- image level ---------------------------------------------------------------------
def detect_cells(img, g, area_tol=0.35):
    """Pixel centroids of the g.cols*g.rows enclosed dark cells, or None."""
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)   # white lines
    cnts, hier = cv2.findContours(bw, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if hier is None:
        return None
    hier, n, best = hier[0], g.cols * g.rows, None
    for i, (_, _, child, parent) in enumerate(hier):
        if parent != -1:
            continue
        holes, k = [], child
        while k != -1:
            holes.append(k)
            k = hier[k][0]
        if len(holes) >= n and (best is None or len(holes) > len(best)):
            best = holes
    if best is None:
        return None
    areas = np.array([cv2.contourArea(cnts[k]) for k in best])
    med = np.median(areas)
    keep = [k for k, a in zip(best, areas) if abs(a - med) <= area_tol * med]
    if len(keep) != n:
        return None
    pts = []
    for k in keep:
        m = cv2.moments(cnts[k])
        pts.append((m["m10"] / m["m00"], m["m01"] / m["m00"]))
    return np.array(pts)


def detect_dots(img, dot_r_px):
    return find_circles(img, 0.6 * dot_r_px, 1.6 * dot_r_px, 0.85,
                        polarity="bright", external_only=True)


# ---- lattice labelling in machine mm -------------------------------------------------
def lattice_fits(pts_mm, g):
    """Label 12 cell centres (machine mm) and fit datum->machine. Returns 2 fits, which
    differ by 180 degrees (the grid alone is symmetric). Each has 'src' (datum) / 'dst'."""
    pts = np.asarray(pts_mm, float)
    n = g.cols * g.rows
    if len(pts) != n or g.cols <= g.rows:
        return []
    c = pts.mean(0)
    dm = np.linalg.norm(pts[:, None] - pts[None], axis=2)
    np.fill_diagonal(dm, np.inf)
    pitch = float(np.median(dm.min(1)))
    u = np.linalg.svd(pts - c)[2][0]                 # long axis = along the columns
    v = np.array([-u[1], u[0]])                      # right-handed (top view of machine XY)
    a = (pts - c) @ u / pitch + (g.cols - 1) / 2
    b = (pts - c) @ v / pitch + (g.rows - 1) / 2
    j, i = np.rint(a).astype(int), np.rint(b).astype(int)
    if (np.abs(a - j).max() > 0.3 or np.abs(b - i).max() > 0.3 or len(set(zip(i, j))) != n
            or j.min() < 0 or i.min() < 0 or j.max() >= g.cols or i.max() >= g.rows):
        return []
    fits = []
    for flip in (False, True):
        ii, jj = (g.rows - 1 - i, g.cols - 1 - j) if flip else (i, j)
        src = np.array([g.cell_xy(r, q) for r, q in zip(ii, jj)])
        f = umeyama(src, pts)
        f.update(src=src, dst=pts, pitch_meas_mm=pitch)
        fits.append(f)
    return fits


def pick_by_prior(fits, prior_rot_deg):
    diff = lambda f: abs((f["rot_deg"] - prior_rot_deg + 180) % 360 - 180)
    return min(fits, key=diff)


# ---- multi-view procedure ------------------------------------------------------------
def measure_datum(view, to_machine, g, grid_view_xy, cam_offset, prior_rot_deg,
                  dot_r_px, principal_px, dot_tol_mm=1.0):
    """view(x, y) -> undistorted image after moving the TOOLHEAD to (x, y) and settling.
    to_machine(px_xy, x, y) -> machine mm of that pixel for that toolhead position.
    Returns dict(pose, grid_pose, dots_mm_measured, rms_mm)."""
    x, y = grid_view_xy
    cells_px = detect_cells(view(x, y), g)
    if cells_px is None:
        raise DatumError("grid cells not found (is the grid in view, in focus, and lit?)")
    cells_mm = np.array([to_machine(p, x, y) for p in cells_px])
    fits = lattice_fits(cells_mm, g)
    if not fits:
        raise DatumError("cell lattice could not be labelled")
    grid = pick_by_prior(fits, prior_rot_deg)
    src, dst = [grid["src"]], [grid["dst"]]
    dots_meas = []
    for k, d in enumerate(g.dots_mm):
        pred = to_machine_xy(grid, d)
        tx, ty = pred - np.asarray(cam_offset, float)        # toolhead XY that centres the dot
        found = detect_dots(view(tx, ty), dot_r_px)
        if not found:
            raise DatumError(f"dot {k} not found near predicted position {pred.round(2)}")
        c = min(found, key=lambda c: np.hypot(c.center_px[0] - principal_px[0],
                                              c.center_px[1] - principal_px[1]))
        m = np.asarray(to_machine(c.center_px, tx, ty), float)
        if np.linalg.norm(m - pred) > dot_tol_mm:
            raise DatumError(f"dot {k} is {np.linalg.norm(m - pred):.2f} mm from prediction "
                             "(wrong orientation prior, or wrong geometry)")
        dots_meas.append(m)
        src.append(np.asarray(d, float)[None])
        dst.append(m[None])
    pose = umeyama(np.vstack(src), np.vstack(dst))
    pose["grid_only"] = {k: grid[k] for k in ("s", "rot_deg", "rms_mm", "pitch_meas_mm")}
    pose["dots_mm_measured"] = np.array(dots_meas)
    return pose
