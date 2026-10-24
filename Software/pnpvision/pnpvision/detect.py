"""Detectors. All work on UNDISTORTED images and return sub-pixel pixel coordinates."""
from dataclasses import dataclass

import cv2
import numpy as np


def _gray(img):
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


@dataclass
class Circle:
    center_px: tuple
    radius_px: float
    circularity: float


def find_circles(img, r_min_px, r_max_px, min_circularity=0.80,
                 polarity="both", external_only=False):
    """All round blobs, best circularity first. polarity: "bright" | "dark" | "both".
    external_only skips holes inside bigger shapes (e.g. the cells of the datum grid)."""
    g = cv2.GaussianBlur(_gray(img), (5, 5), 0)
    h, w = g.shape
    modes = {"dark": [cv2.THRESH_BINARY_INV], "bright": [cv2.THRESH_BINARY],
             "both": [cv2.THRESH_BINARY_INV, cv2.THRESH_BINARY]}[polarity]
    retr = cv2.RETR_EXTERNAL if external_only else cv2.RETR_LIST
    found = []
    for mode in modes:
        _, bw = cv2.threshold(g, 0, 255, mode | cv2.THRESH_OTSU)
        cnts, _ = cv2.findContours(bw, retr, cv2.CHAIN_APPROX_NONE)
        for c in cnts:
            a = cv2.contourArea(c)
            if not (np.pi * r_min_px**2 <= a <= np.pi * r_max_px**2):
                continue
            x, y, bw_, bh_ = cv2.boundingRect(c)
            if x <= 1 or y <= 1 or x + bw_ >= w - 1 or y + bh_ >= h - 1:
                continue                       # touches border -> clipped
            p = cv2.arcLength(c, True)
            circ = 4 * np.pi * a / (p * p) if p else 0
            if circ < min_circularity:
                continue
            m = cv2.moments(c)
            found.append(Circle((m["m10"] / m["m00"], m["m01"] / m["m00"]),
                                float(np.sqrt(a / np.pi)), circ))
    return sorted(found, key=lambda c: -c.circularity)


def find_circle(img, r_min_px, r_max_px, min_circularity=0.80):
    """Most circular blob, dark-on-light or light-on-dark.
    Use for: a marker dot, the nozzle tip ring seen by the up camera, round fiducials."""
    found = find_circles(img, r_min_px, r_max_px, min_circularity)
    return found[0] if found else None


@dataclass
class PartMeasure:
    center_px: tuple
    long_px: float
    short_px: float
    angle_px_deg: float      # long-axis angle in image, (-90, 90]
    area_px: float


def measure_part(img, nozzle_px, search_radius_px, min_area_px=200):
    """Segment the part held on the nozzle (up camera) and fit a rotated rectangle.
    FIRST-CUT: global Otsu on a crop around the nozzle. Real images will need tuning
    (lighting, nozzle colour, background); the output contract is what matters now."""
    h, w = img.shape[:2]
    nx, ny = nozzle_px
    r = int(search_radius_px)
    x0, y0 = max(int(nx) - r, 0), max(int(ny) - r, 0)
    x1, y1 = min(int(nx) + r, w), min(int(ny) + r, h)
    crop = cv2.GaussianBlur(_gray(img)[y0:y1, x0:x1], (5, 5), 0)
    best = None
    for mode in (cv2.THRESH_BINARY_INV, cv2.THRESH_BINARY):
        _, bw = cv2.threshold(crop, 0, 255, mode | cv2.THRESH_OTSU)
        cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        for c in cnts:
            a = cv2.contourArea(c)
            if a < min_area_px:
                continue
            x, y, cw, ch = cv2.boundingRect(c)
            if x <= 1 or y <= 1 or x + cw >= crop.shape[1] - 1 or y + ch >= crop.shape[0] - 1:
                continue                       # blob is the background, not the part
            (cx, cy), (rw, rh), ang = cv2.minAreaRect(c)
            if rw < rh:
                rw, rh, ang = rh, rw, ang + 90.0
            ang = (ang + 90.0) % 180.0 - 90.0
            # prefer the blob closest to the nozzle axis
            d = np.hypot(cx + x0 - nx, cy + y0 - ny)
            if best is None or d < best[0]:
                best = (d, PartMeasure((cx + x0, cy + y0), float(rw), float(rh), float(ang), float(a)))
    return None if best is None else best[1]
