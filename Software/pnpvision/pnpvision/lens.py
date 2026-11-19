"""Load a calibration .npz (camera_matrix, dist_coeffs, image_size, rms) and undistort."""
import cv2
import numpy as np


def square_new_K(K, dist, in_size, out_size, centered=False):
    """Camera matrix for the undistorted image: SQUARE pixels (fx == fy) and as wide a view
    as possible with only valid pixels (no black edges). The optical axis sits where
    getOptimalNewCameraMatrix(alpha=0) puts it (off-centre on these lenses); centered=True
    moves it to the frame centre instead, which costs ~17% of the down camera's view.

    cv2.getOptimalNewCameraMatrix(alpha=0) fills the frame by scaling X and Y differently
    (on these wide lenses fy/fx came out 1.24 down, 1.17 up), which stretches circles into
    ovals and makes px->mm differ per axis. Keep this function identical to the copy in
    Archive/USB Camera Calibration Vibecode Project/undistort_stream.py so the Mainsail
    view and pnpvision share one image geometry.
    """
    K = np.asarray(K, np.float64)
    dist = np.asarray(dist, np.float64).ravel()
    w, h = in_size
    W, H = out_size
    if centered:
        cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
    else:
        k0, _ = cv2.getOptimalNewCameraMatrix(K, dist, (w, h), 0.0, (W, H))
        cx, cy = float(k0[0, 2]), float(k0[1, 2])
    # Radius where the radial model folds back (rd stops growing): beyond it projected
    # points can land inside the frame by accident, so treat it as invalid.
    k1, k2, k3 = dist[0], dist[1], dist[4] if dist.size > 4 else 0.0
    r = np.linspace(0, 5, 5001)
    fold = np.where(np.diff(r * (1 + k1 * r**2 + k2 * r**4 + k3 * r**6)) <= 0)[0]
    r_fold = r[fold[0]] if len(fold) else np.inf
    n = 200
    u = np.r_[np.linspace(0, W - 1, n), np.linspace(0, W - 1, n), np.zeros(n), np.full(n, W - 1.0)]
    v = np.r_[np.zeros(n), np.full(n, H - 1.0), np.linspace(0, H - 1, n), np.linspace(0, H - 1, n)]

    def valid(f):
        x, y = (u - cx) / f, (v - cy) / f
        if np.max(np.hypot(x, y)) >= r_fold:
            return False
        p, _ = cv2.projectPoints(np.c_[x, y, np.ones_like(x)].reshape(-1, 1, 3),
                                 np.zeros(3), np.zeros(3), K, dist)
        p = p.reshape(-1, 2)
        return bool(np.all((p[:, 0] >= 0) & (p[:, 0] <= w - 1) & (p[:, 1] >= 0) & (p[:, 1] <= h - 1)))

    lo, hi = 1e-3, 1e3 * max(K[0, 0], K[1, 1]) * max(W / w, H / h)
    for _ in range(60):                       # smallest f (widest view) that is still valid
        mid = np.sqrt(lo * hi)
        lo, hi = (lo, mid) if valid(mid) else (mid, hi)
    return np.array([[hi, 0, cx], [0, hi, cy], [0, 0, 1]], np.float64)


class LensModel:
    def __init__(self, npz_path):
        d = np.load(npz_path)
        self.K = d["camera_matrix"].astype(np.float64)
        self.dist = d["dist_coeffs"].astype(np.float64).ravel()
        self.size = tuple(int(v) for v in d["image_size"])      # (w, h)
        self.rms = float(d["rms"]) if "rms" in d.files else None
        # newK is the camera matrix of the *undistorted* image; every measurement
        # downstream lives in that image. Square pixels; optical axis = newK[:2, 2].
        self.newK = square_new_K(self.K, self.dist, self.size, self.size)
        self._m1, self._m2 = cv2.initUndistortRectifyMap(
            self.K, self.dist, None, self.newK, self.size, cv2.CV_16SC2)

    def undistort(self, img):
        h, w = img.shape[:2]
        if (w, h) != self.size:
            raise ValueError(f"frame is {w}x{h} but calibration is {self.size[0]}x{self.size[1]}")
        return cv2.remap(img, self._m1, self._m2, cv2.INTER_LINEAR)

    def undistort_points(self, pts_px):
        p = np.asarray(pts_px, np.float32).reshape(-1, 1, 2)
        return cv2.undistortPoints(p, self.K, self.dist, P=self.newK).reshape(-1, 2)

    def health(self):
        """Flag calibrations whose distortion model misbehaves inside the image."""
        w, h = self.size
        fx, fy = self.K[0, 0], self.K[1, 1]
        k1, k2, _, _, k3 = self.dist
        r_corner = float(np.hypot((w / 2) / fx, (h / 2) / fy))
        r = np.linspace(0, r_corner * 1.0, 400)
        rd = r * (1 + k1 * r**2 + k2 * r**4 + k3 * r**6)
        fold = np.where(np.diff(rd) <= 0)[0]
        corners = np.array([[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]], np.float32)
        shift = np.linalg.norm(self.undistort_points(corners) - corners, axis=1)
        return {
            "rms_px": self.rms,
            "hfov_deg": float(np.degrees(2 * np.arctan(w / 2 / fx))),
            "undistorted_f_px": float(self.newK[0, 0]),
            "undistorted_fov_deg": [float(np.degrees(2 * np.arctan(w / 2 / self.newK[0, 0]))),
                                    float(np.degrees(2 * np.arctan(h / 2 / self.newK[1, 1])))],
            "corner_shift_px": shift.round(1).tolist(),
            "model_folds_inside_image": bool(len(fold)),
            "usable_note": ("distortion model folds back inside the frame - do not trust the "
                            "outer edge; measure near the centre or recalibrate"
                            if len(fold) else "ok"),
        }
