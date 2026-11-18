"""Up-facing camera: light the part on the nozzle, measure it, report offset/rotation/size.

Offsets are measured at the nozzle's CURRENT rotation. When the nozzle rotation axis is added
the placement logic should rotate first, re-inspect (or rotate the offset about the nozzle
axis), then correct - an offset from the nozzle axis changes direction as the nozzle turns.
"""
import numpy as np

from .detect import interior_dark_fraction, measure_part
from .lighting import grab_lit


class UpCam:
    MIN_FILL = 0.75     # blob area / its rotated bounding box; below this it is not a chip
    FLIP_DARK = 0.4     # resistors: inner half darker than this share = upside down (black top)

    def __init__(self, cam, lens, light, motion, nozzle_px=None, settle_s=0.2,
                 ambient_subtract=False, keep_on=False, search_radius_mm=6.0):
        self.cam, self.lens, self.light, self.motion = cam, lens, light, motion
        # Nozzle axis in the UNDISTORTED image. By construction of `calibrate-motion --find-center`
        # this is the principal point, at the Z where that was done.
        self.nozzle_px = (np.array(nozzle_px, float) if nozzle_px is not None
                          else np.array([lens.newK[0, 2], lens.newK[1, 2]]))
        self.settle_s, self.ambient_subtract, self.keep_on = settle_s, ambient_subtract, keep_on
        self.search_radius_mm = search_radius_mm

    def frame(self):
        return grab_lit(self.cam, self.light, self.lens, self.settle_s,
                        self.ambient_subtract, self.keep_on)

    def inspect(self, expected_mm=None, tol_mm=0.15, log=None, part_id=None, img=None, min_width_frac=None,
                flip_check=False):
        """expected_mm=(length, width) of the part body; tol_mm applies to each dimension.
        Returns dict(ok, reason, offset_mm=[x,y] machine frame, angle_deg, size_mm=[L,W])."""
        img = self.frame() if img is None else img
        mpp = self.motion.mm_per_px
        radius_mm = self.search_radius_mm
        if expected_mm is not None:
            # Look only a little beyond the part itself. A wide search finds the nozzle's own
            # concentric rings (the collar measured 8.3 mm) instead of a small chip.
            radius_mm = min(radius_mm, 0.5 * float(np.hypot(*expected_mm)) + 1.0)
        exp_px = None if expected_mm is None else tuple(sorted(expected_mm, reverse=True)[i] / mpp for i in (0, 1))
        pm = measure_part(img, self.nozzle_px, radius_mm / mpp, expected_px=exp_px)
        if pm is None:
            res = {"ok": False, "reason": "no part found"}
        else:
            off = self.motion.offset_mm(np.array(pm.center_px) - self.nozzle_px)
            size = sorted([pm.long_px * mpp, pm.short_px * mpp], reverse=True)
            fill = pm.area_px / max(pm.long_px * pm.short_px, 1.0)
            res = {"ok": True, "reason": "",
                   "offset_mm": [float(off[0]), float(off[1])],
                   "angle_deg": float(self.motion.direction_mm(pm.angle_px_deg)),
                   "size_mm": [float(size[0]), float(size[1])], "area_px": float(pm.area_px),
                   "fill": float(fill)}
            if fill < self.MIN_FILL:
                # a real chip fills its bounding box (0.89-0.92 measured); an empty nozzle's
                # rings give crescents (0.40 measured on 2026-11-11)
                res = {"ok": False, "reason": f"no part found (best blob fill {fill:.2f} is not a rectangle)",
                       "fill": float(fill)}
            elif expected_mm is not None:
                exp = sorted(expected_mm, reverse=True)
                bad = [abs(s - e) > tol_mm for s, e in zip(size, exp)]
                if any(bad):
                    res.update(ok=False, reason=f"size {size[0]:.2f}x{size[1]:.2f} mm vs "
                                                f"expected {exp[0]:.2f}x{exp[1]:.2f}")
                elif min_width_frac and size[1] < min_width_frac * exp[1]:
                    # a chip on its side shows its THICKNESS as its width (0603: 0.58 measured vs
                    # 0.87-0.96 flat, 2026-11-18); flat parts read ~0.1 mm wider than nominal
                    res.update(ok=False, reason=f"too narrow: {size[1]:.2f} mm wide vs "
                                                f"{exp[1]:.2f} expected (on its side?)")
            if res.get("ok") and flip_check:
                dark = interior_dark_fraction(img, pm)
                res["dark_frac"] = round(dark, 3)
                if dark > self.FLIP_DARK:
                    res.update(ok=False, reason=f"upside down: dark top facing the camera "
                                                f"({dark:.0%} of the centre dark)")
        if log is not None:
            log.log("inspect", ok=res["ok"], part_id=part_id,
                    **{k: v for k, v in res.items() if k != "ok"})
        return res
