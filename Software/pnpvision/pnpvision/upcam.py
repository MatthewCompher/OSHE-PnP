"""Up-facing camera: light the part on the nozzle, measure it, report offset/rotation/size.

Offsets are measured at the nozzle's CURRENT rotation. When the nozzle rotation axis is added
the placement logic should rotate first, re-inspect (or rotate the offset about the nozzle
axis), then correct - an offset from the nozzle axis changes direction as the nozzle turns.
"""
import numpy as np

from .detect import measure_part
from .lighting import grab_lit


class UpCam:
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

    def inspect(self, expected_mm=None, tol_mm=0.15, log=None, part_id=None, img=None):
        """expected_mm=(length, width) of the part body; tol_mm applies to each dimension.
        Returns dict(ok, reason, offset_mm=[x,y] machine frame, angle_deg, size_mm=[L,W])."""
        img = self.frame() if img is None else img
        mpp = self.motion.mm_per_px
        pm = measure_part(img, self.nozzle_px, self.search_radius_mm / mpp)
        if pm is None:
            res = {"ok": False, "reason": "no part found"}
        else:
            off = self.motion.offset_mm(np.array(pm.center_px) - self.nozzle_px)
            size = sorted([pm.long_px * mpp, pm.short_px * mpp], reverse=True)
            res = {"ok": True, "reason": "",
                   "offset_mm": [float(off[0]), float(off[1])],
                   "angle_deg": float(self.motion.direction_mm(pm.angle_px_deg)),
                   "size_mm": [float(size[0]), float(size[1])], "area_px": float(pm.area_px)}
            if expected_mm is not None:
                exp = sorted(expected_mm, reverse=True)
                bad = [abs(s - e) > tol_mm for s, e in zip(size, exp)]
                if any(bad):
                    res.update(ok=False, reason=f"size {size[0]:.2f}x{size[1]:.2f} mm vs "
                                                f"expected {exp[0]:.2f}x{exp[1]:.2f}")
        if log is not None:
            log.log("inspect", ok=res["ok"], part_id=part_id,
                    **{k: v for k, v in res.items() if k != "ok"})
        return res
