"""MotionMap: how a toolhead move shows up in a camera image.

s = M @ m      s: feature shift in pixels (undistorted image), m: toolhead move in mm.

One 2x2 matrix captures scale, rotation AND axis flips between image and machine,
so we never have to guess which way the camera is mounted. The same fit works for
  moving="camera"  (down cam rides on the toolhead; scene appears to shift opposite)
  moving="target"  (up cam is fixed; the nozzle moves through its view)

Scale is only valid for the depth where the feature was measured (mm/px changes
with working distance), so calibrate at the Z you will actually work at.
"""
import json
from pathlib import Path

import numpy as np


class MotionMap:
    def __init__(self, M, moving="camera"):
        assert moving in ("camera", "target")
        self.M = np.asarray(M, float).reshape(2, 2)
        self.Minv = np.linalg.inv(self.M)
        self.moving = moving

    @classmethod
    def fit(cls, moves_mm, shifts_px, moving="camera"):
        A = np.asarray(moves_mm, float)
        B = np.asarray(shifts_px, float)
        X, res, rank, _ = np.linalg.lstsq(A, B, rcond=None)   # A @ X = B  ->  M = X.T
        mm = cls(X.T, moving)
        mm.fit_rms_px = float(np.sqrt(np.mean((A @ X - B) ** 2)))
        return mm

    # -- conversions -------------------------------------------------------
    def to_move_mm(self, err_px):
        """Toolhead move that drives a feature at `err_px` (from target point) to zero."""
        return -self.Minv @ np.asarray(err_px, float)

    def offset_mm(self, err_px):
        """Machine-frame XY of the observed feature relative to the optical axis."""
        sign = -1.0 if self.moving == "camera" else 1.0
        return sign * (self.Minv @ np.asarray(err_px, float))

    def direction_mm(self, angle_deg_px):
        """Image-plane direction (deg) -> machine-plane direction (deg), mod 180."""
        a = np.radians(angle_deg_px)
        d = self.Minv @ np.array([np.cos(a), np.sin(a)])
        ang = np.degrees(np.arctan2(d[1], d[0]))
        return (ang + 90.0) % 180.0 - 90.0      # (-90, 90]

    @property
    def mm_per_px(self):
        return float(1.0 / np.sqrt(abs(np.linalg.det(self.M))))

    def describe(self):
        s = np.linalg.svd(self.M, compute_uv=False)
        return {"mm_per_px": self.mm_per_px,
                "anisotropy": float(s.max() / s.min()),
                "M": self.M.tolist(), "moving": self.moving,
                "fit_rms_px": getattr(self, "fit_rms_px", None)}

    # -- persistence -------------------------------------------------------
    def save(self, path):
        Path(path).write_text(json.dumps({"M": self.M.tolist(), "moving": self.moving}, indent=2))

    @classmethod
    def load(cls, path):
        d = json.loads(Path(path).read_text())
        return cls(d["M"], d["moving"])
