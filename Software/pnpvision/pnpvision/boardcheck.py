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


BODY_MAX_VAL = 200         # pads and chip terminations are bright metal (V 228-255); bodies darker


def body_mask(img):
    """Chip-body pixels: not solder mask, and not bright metal (pads, terminations). A black
    resistor top reads V ~140 here; tan/brown capacitor bodies are kept by their warm hue."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    H, S, V = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green = (H >= GREEN_HUE[0]) & (H <= GREEN_HUE[1]) & (S >= GREEN_MIN_SAT) & (V >= GREEN_MIN_VAL)
    warm = (H < GREEN_HUE[0]) & (S >= GREEN_MIN_SAT)
    return (~green) & ((V < BODY_MAX_VAL) | warm)


def measure_body(img, center_px, px_per_mm, body_mm):
    """Where the chip body sits around the footprint centre. All body pixels within a window of
    0.75 x the part length are used together (robust to the body being cut by glare or a mark).
    -> dict(found, centre_px, angle_px_deg or None, area_px) ; angle only if clearly oblong."""
    L, W = sorted(body_mm, reverse=True)
    half = int(round(0.75 * L * px_per_mm))
    cx, cy = int(round(center_px[0])), int(round(center_px[1]))
    x0, y0 = max(cx - half, 0), max(cy - half, 0)
    m = body_mask(img[y0:cy + half, x0:cx + half]).astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    ys, xs = np.nonzero(m)
    need = 0.25 * L * W * px_per_mm ** 2
    if len(xs) < need:
        return {"found": False, "area_px": int(len(xs))}
    pts = np.column_stack([xs + x0, ys + y0]).astype(np.float32)
    c = pts.mean(axis=0)
    (rw, rh) = cv2.minAreaRect(pts)[1]
    ang = None
    if min(rw, rh) > 0 and max(rw, rh) / min(rw, rh) > 1.15:
        cov = np.cov((pts - c).T)
        ev, evec = np.linalg.eigh(cov)
        v = evec[:, np.argmax(ev)]
        ang = float(np.degrees(np.arctan2(v[1], v[0])))
    return {"found": True, "centre_px": [float(c[0]), float(c[1])], "angle_px_deg": ang, "area_px": int(len(xs))}


def wrap90(a):
    return (float(a) + 90.0) % 180.0 - 90.0


def annotate(img, center_px, px_per_mm, res, window_mm=WINDOW_MM):
    out = img.copy()
    h = int(round(0.5 * window_mm * px_per_mm))
    cx, cy = int(round(center_px[0])), int(round(center_px[1]))
    col = (0, 200, 0) if res["placed"] else (0, 0, 255)
    cv2.rectangle(out, (cx - h, cy - h), (cx + h, cy + h), col, 2)
    txt = f"{'PLACED' if res['placed'] else 'MISSING'} green {res['green'] if res['green'] is not None else '-'}"
    if res.get("err_mm") is not None:
        txt += f"  off {res['err_mm']:.2f} mm"
        if res.get("angle_err_deg") is not None:
            txt += f"  {res['angle_err_deg']:+.1f} deg"
    cv2.putText(out, txt, (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, col, 3)
    if res.get("body_px"):
        bx, by = (int(round(v)) for v in res["body_px"])
        cv2.drawMarker(out, (bx, by), (255, 0, 255), cv2.MARKER_TILTED_CROSS, 30, 2)
    cv2.drawMarker(out, (cx, cy), (0, 255, 255), cv2.MARKER_CROSS, 40, 1)
    return out


def px_per_mm(motion):
    """Down-camera scale from its MotionMap (pixels per mm, mean of both axes)."""
    M = np.asarray(motion.M, float)
    return float(np.mean([np.linalg.norm(M[:, 0]), np.linalg.norm(M[:, 1])]))
