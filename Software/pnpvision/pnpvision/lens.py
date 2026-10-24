"""Load a calibration .npz (camera_matrix, dist_coeffs, image_size, rms) and undistort."""
import cv2
import numpy as np


class LensModel:
    def __init__(self, npz_path, alpha=0.0):
        d = np.load(npz_path)
        self.K = d["camera_matrix"].astype(np.float64)
        self.dist = d["dist_coeffs"].astype(np.float64).ravel()
        self.size = tuple(int(v) for v in d["image_size"])      # (w, h)
        self.rms = float(d["rms"]) if "rms" in d.files else None
        # alpha=0 -> crop to valid pixels only. newK is the camera matrix of the
        # *undistorted* image; every measurement downstream lives in that image.
        self.newK, self.roi = cv2.getOptimalNewCameraMatrix(
            self.K, self.dist, self.size, alpha, self.size)
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
            "corner_shift_px": shift.round(1).tolist(),
            "model_folds_inside_image": bool(len(fold)),
            "usable_note": ("distortion model folds back inside the frame - do not trust the "
                            "outer edge; measure near the centre or recalibrate"
                            if len(fold) else "ok"),
        }
