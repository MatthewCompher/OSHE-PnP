"""Is a part sitting on its footprint? Down camera over the footprint centre, after placing.

An empty footprint shows green solder mask between its two pads; a placed chip covers that gap
with its body (black resistor top, tan/brown capacitor). So: the share of mask-green pixels in a
small window at the footprint centre. 2026-11-17 photo (Test PCB, down light on): placed 0603
0.00, five empty footprints 0.94-1.00. A part placed far enough off to uncover the centre reads
as MISSING, which is the right call for "placed correctly".
"""
import cv2
import numpy as np

GREEN_HUE = (35, 100)      # OpenCV hue (0-180): this board's mask reads 88-93, a resistor body 107
GREEN_MIN_SAT = 60
GREEN_MIN_VAL = 50
WINDOW_MM = 0.6            # square window side at the footprint centre (0603 pad gap ~0.8 mm)
GREEN_MAX = 0.5            # green share below this = a part covers the centre


def green_share(img, center_px, half_px):
    cx, cy = int(round(center_px[0])), int(round(center_px[1]))
    h = max(int(round(half_px)), 2)
    roi = img[max(cy - h, 0):cy + h, max(cx - h, 0):cx + h]
    if roi.size == 0:
        return None
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    g = (H >= GREEN_HUE[0]) & (H <= GREEN_HUE[1]) & (S >= GREEN_MIN_SAT) & (V >= GREEN_MIN_VAL)
    return float(g.mean())


def check_footprint(img, center_px, px_per_mm, window_mm=WINDOW_MM, green_max=GREEN_MAX):
    """-> dict(placed, green, reason)."""
    g = green_share(img, center_px, 0.5 * window_mm * px_per_mm)
    if g is None:
        return {"placed": False, "green": None, "reason": "footprint outside the image"}
    placed = g < green_max
    return {"placed": bool(placed), "green": round(g, 3),
            "reason": "" if placed else f"bare mask at the footprint centre (green {g:.2f})"}


def annotate(img, center_px, px_per_mm, res, window_mm=WINDOW_MM):
    out = img.copy()
    h = int(round(0.5 * window_mm * px_per_mm))
    cx, cy = int(round(center_px[0])), int(round(center_px[1]))
    col = (0, 200, 0) if res["placed"] else (0, 0, 255)
    cv2.rectangle(out, (cx - h, cy - h), (cx + h, cy + h), col, 2)
    txt = f"{'PLACED' if res['placed'] else 'MISSING'} green {res['green'] if res['green'] is not None else '-'}"
    cv2.putText(out, txt, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, col, 3)
    return out


def px_per_mm(motion):
    """Down-camera scale from its MotionMap (pixels per mm, mean of both axes)."""
    M = np.asarray(motion.M, float)
    return float(np.mean([np.linalg.norm(M[:, 0]), np.linalg.norm(M[:, 1])]))
