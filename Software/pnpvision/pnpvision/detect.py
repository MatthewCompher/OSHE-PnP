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
                 polarity="both", external_only=False, threshold=None):
    """All round blobs, best circularity first. polarity: "bright" | "dark" | "both".
    external_only skips holes inside bigger shapes (e.g. the cells of the datum grid).
    threshold: None = automatic (Otsu) black/white cut-off for the whole frame; a number
    0-255 = fixed cut-off. Use a fixed high one (~230, polarity "bright") for a white dot on
    a sparkly or textured surface, where Otsu lets the glints merge into the dot."""
    g = cv2.GaussianBlur(_gray(img), (5, 5), 0)
    h, w = g.shape
    modes = {"dark": [cv2.THRESH_BINARY_INV], "bright": [cv2.THRESH_BINARY],
             "both": [cv2.THRESH_BINARY_INV, cv2.THRESH_BINARY]}[polarity]
    retr = cv2.RETR_EXTERNAL if external_only else cv2.RETR_LIST
    found = []
    for mode in modes:
        if threshold is None:
            _, bw = cv2.threshold(g, 0, 255, mode | cv2.THRESH_OTSU)
        else:
            _, bw = cv2.threshold(g, float(threshold), 255, mode)
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


def find_circle(img, r_min_px, r_max_px, min_circularity=0.80, polarity="both", threshold=None):
    """Most circular blob, dark-on-light or light-on-dark (see find_circles for options).
    Use for: a marker dot, the nozzle tip ring seen by the up camera, round fiducials."""
    found = find_circles(img, r_min_px, r_max_px, min_circularity, polarity, threshold=threshold)
    return found[0] if found else None


@dataclass
class PartMeasure:
    center_px: tuple
    long_px: float
    short_px: float
    angle_px_deg: float      # long-axis angle in image, (-90, 90]
    area_px: float


def symmetry_center(img, start_px, half_px, max_shift_px, starts=((0, 0),)):
    """Centre of 180-degree symmetry of what is around start_px (chip parts look the same
    turned half a turn), independent of colours and lighting. Correlates a window with its own
    180-degree rotation; the best shift s means the centre is window centre + s/2. Tries each
    start offset and keeps the best. Returns (center_px (x, y), score) or (None, 0).
    On a real 0805 on bare board (2026-11-11) every start up to 0.5 mm off landed within
    0.5 px; thresholding (measure_part) had found only half of that part there."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    g = g.astype(np.float32)
    m = 2 * int(max_shift_px)
    best = (None, 0.0)
    for dx, dy in starts:
        x0 = int(round(start_px[0] + dx)) - half_px
        y0 = int(round(start_px[1] + dy)) - half_px
        if x0 - m < 0 or y0 - m < 0 or x0 + 2 * half_px + 1 + m > g.shape[1] or y0 + 2 * half_px + 1 + m > g.shape[0]:
            continue
        win = g[y0:y0 + 2 * half_px + 1, x0:x0 + 2 * half_px + 1]
        rot = np.ascontiguousarray(win[::-1, ::-1])
        big = g[y0 - m:y0 + 2 * half_px + 1 + m, x0 - m:x0 + 2 * half_px + 1 + m]
        res = cv2.matchTemplate(big, rot, cv2.TM_CCOEFF_NORMED)
        _, v, _, (x, y) = cv2.minMaxLoc(res)
        if v > best[1]:
            best = (np.array([x0 + half_px + (x - m) / 2.0, y0 + half_px + (y - m) / 2.0]), float(v))
    return best


def outline_angle(img, center_px, long_px, short_px, step_deg=2):
    """Angle (deg, OpenCV box convention) at which a long x short rectangle centred on the part
    lines up best with the image's edges. Used to shape the part mask for matching."""
    g = cv2.GaussianBlur(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img, (5, 5), 0)
    g = g.astype(np.float32)
    mag = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    t = np.linspace(0, 1, 40, endpoint=False)[:, None]
    best = (0.0, -1.0)
    for th in np.arange(0, 180, step_deg):
        box = cv2.boxPoints((tuple(map(float, center_px)), (long_px, short_px), float(th)))
        pts = np.vstack([box[i] + (box[(i + 1) % 4] - box[i]) * t for i in range(4)])
        xi = np.clip(pts[:, 0].astype(int), 0, g.shape[1] - 1)
        yi = np.clip(pts[:, 1].astype(int), 0, g.shape[0] - 1)
        s = float(mag[yi, xi].mean())
        if s > best[1]:
            best = (float(th), s)
    return best[0]


def find_by_template(img, template, center_px=None, radius_px=None, threshold=0.8,
                     angles=tuple(range(0, 360, 12)), quarter_turns=(0,), scale=1.0, max_hits=20,
                     mask=None, _cropped=False):
    """Places where `template` (a picture of one part) appears in `img`, best first.
    Returns [(center_px (x, y) in img pixels, score 0..1)]. Normalised correlation on colour,
    with the template turned in 12 degree steps all the way round, so parts dropped by hand at
    any orientation still match. scale < 1 searches a shrunken copy (fast coarse search);
    positions are returned in full-size pixels.
    mask: 255 where the template is the PART (0 = background). Without it the background
    around the first part (pads, silkscreen) dominated: a real part on the board scored 0.75;
    with it 0.92, against 0.69 for the best pad/text (2026-11-11).
    center_px/radius_px: only accept matches within that circle (and only search around it)."""
    if center_px is not None and radius_px is not None and not _cropped:
        # search only a window around the circle: much faster on the Pi than the whole frame
        m = int(radius_px + max(template.shape[:2]) * 0.75) + 2
        x0 = max(int(center_px[0]) - m, 0)
        y0 = max(int(center_px[1]) - m, 0)
        win = img[y0:int(center_px[1]) + m, x0:int(center_px[0]) + m]
        hits = find_by_template(win, template, (center_px[0] - x0, center_px[1] - y0), radius_px,
                                threshold, angles, quarter_turns, scale, max_hits, mask, _cropped=True)
        return [((p[0] + x0, p[1] + y0), s) for p, s in hits]
    small = img if scale == 1.0 else cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    tpl0 = template if scale == 1.0 else cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    msk0 = None
    if mask is not None:
        msk0 = mask if scale == 1.0 else cv2.resize(mask, (tpl0.shape[1], tpl0.shape[0]),
                                                    interpolation=cv2.INTER_NEAREST)
    best = None
    for q in quarter_turns:
        tq = np.ascontiguousarray(np.rot90(tpl0, q))
        mq = None if msk0 is None else np.ascontiguousarray(np.rot90(msk0, q))
        h, w = tq.shape[:2]
        for ang in angles:
            if ang:
                m = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
                t = cv2.warpAffine(tq, m, (w, h), borderMode=cv2.BORDER_REPLICATE)
                mk = None if mq is None else cv2.warpAffine(mq, m, (w, h), flags=cv2.INTER_NEAREST)
            else:
                t, mk = tq, mq
            if small.shape[0] < h or small.shape[1] < w:
                continue
            if mk is None:
                r = cv2.matchTemplate(small, t, cv2.TM_CCOEFF_NORMED)
            else:
                r = cv2.matchTemplate(small, t, cv2.TM_CCOEFF_NORMED, mask=mk)
                r[~np.isfinite(r)] = -1.0          # flat areas give NaN/inf with a mask
            pad = np.full((small.shape[0], small.shape[1]), -1.0, np.float32)
            pad[h // 2:h // 2 + r.shape[0], w // 2:w // 2 + r.shape[1]] = r   # index = template centre
            best = pad if best is None else np.maximum(best, pad)
    if best is None:
        return []
    if center_px is not None and radius_px is not None:
        yy, xx = np.mgrid[0:best.shape[0], 0:best.shape[1]]
        cx, cy = center_px[0] * scale, center_px[1] * scale
        best[(xx - cx) ** 2 + (yy - cy) ** 2 > (radius_px * scale) ** 2] = -1.0
    sep = max(template.shape[:2]) * scale * 0.8          # one hit per part
    hits = []
    for _ in range(max_hits):
        _, score, _, (x, y) = cv2.minMaxLoc(best)
        if score < threshold:
            break
        # sub-pixel peak (parabola through the neighbours)
        dx = dy = 0.0
        if 0 < x < best.shape[1] - 1:
            l, c, rr = best[y, x - 1], best[y, x], best[y, x + 1]
            den = l - 2 * c + rr
            dx = 0.5 * (l - rr) / den if den < 0 else 0.0
        if 0 < y < best.shape[0] - 1:
            u, c, d = best[y - 1, x], best[y, x], best[y + 1, x]
            den = u - 2 * c + d
            dy = 0.5 * (u - d) / den if den < 0 else 0.0
        hits.append((((x + dx) / scale, (y + dy) / scale), float(score)))
        cv2.circle(best, (x, y), int(sep), -1.0, -1)
    return hits


def find_placed_part(ref, img, center_px, radius_px, expected_px, size_tol=0.2, min_threshold=35):
    """The part that appeared near center_px between `ref` (target before placing) and `img`
    (after), both taken from the same commanded camera position. Returns PartMeasure or None.

    Works for any part colour on any background (pads, silkscreen, tape): only what changed
    counts. Real photos (2026-11-11, part on double-sided tape) needed three things:
      * line the photos up first: the camera came back ~1 px off, and on the sparkly tape that
        alone lit up every edge in the difference;
      * look only in a window around the target;
      * join the pieces: the metal ends can match the background and drop out of the
        difference, so the part is the convex hull of the blobs near the biggest one."""
    ga = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY) if ref.ndim == 3 else ref
    gb = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    (sx, sy), _ = cv2.phaseCorrelate(ga.astype(np.float32), gb.astype(np.float32))
    if abs(sx) > 20 or abs(sy) > 20:                 # not the same view: don't trust the shift
        sx = sy = 0.0
    ref = cv2.warpAffine(ref, np.float32([[1, 0, sx], [0, 1, sy]]), (ref.shape[1], ref.shape[0]),
                         borderMode=cv2.BORDER_REPLICATE)
    r = int(radius_px)
    x0, y0 = max(int(center_px[0]) - r, 0), max(int(center_px[1]) - r, 0)
    x1, y1 = min(int(center_px[0]) + r, img.shape[1]), min(int(center_px[1]) + r, img.shape[0])
    a = cv2.GaussianBlur(ref[y0:y1, x0:x1], (7, 7), 0).astype(np.float32)
    b = cv2.GaussianBlur(img[y0:y1, x0:x1], (7, 7), 0).astype(np.float32)
    if a.ndim == 3:
        # The down light's colour / the camera's white balance shifted between photos
        # (2026-11-11: blue -25 %, red +80 %): even out each colour channel (medians = board,
        # the part is a small share of the window), then compare in Lab colour space.
        a = np.clip(a * (np.median(b.reshape(-1, 3), 0) / np.maximum(np.median(a.reshape(-1, 3), 0), 1.0)), 0, 255)
        la = cv2.cvtColor(a.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
        lb = cv2.cvtColor(b.astype(np.uint8), cv2.COLOR_BGR2LAB).astype(np.float32)
        d = np.sqrt(((lb - la) ** 2).sum(axis=2))
    else:
        d = np.abs(b - a * (np.median(b) / max(float(np.median(a)), 1.0)))
    mask = (d > max(min_threshold, 3.0 * float(np.median(d)))).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(mask)
    if n < 2:
        return None
    el, es = expected_px
    big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    if st[big, cv2.CC_STAT_AREA] < 0.15 * el * es:
        return None
    keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 0.02 * el * es and
            np.hypot(*(cen[i] - cen[big])) < 0.75 * el]
    pts = np.vstack([np.column_stack(np.nonzero(lab == i)[::-1]) for i in keep]).astype(np.int32)
    hull = cv2.convexHull(pts)
    (cx, cy), (rw, rh), ang = cv2.minAreaRect(hull)
    if rw < rh:
        rw, rh, ang = rh, rw, ang + 90.0
    if abs(rw - el) / el > size_tol or abs(rh - es) / es > size_tol:
        return None
    ang = (ang + 90.0) % 180.0 - 90.0
    return PartMeasure((cx + x0, cy + y0), float(rw), float(rh), float(ang), float(cv2.contourArea(hull)))


def interior_dark_fraction(img, pm, shrink=0.5, rel=0.8):
    """Share of the part's inner half (a rectangle shrink x its size, same centre and angle) that is
    darker than rel x the part's bright level (90th percentile over the whole part). A chip
    resistor seen from below shows its white ceramic underside (interior ~ as bright as the
    rim); picked upside down it shows its black top inside a white outline (2026-11-18: interior
    ~150 vs ~247 of 255). Returns 0..1."""
    g = _gray(img)
    rect = (tuple(map(float, pm.center_px)), (float(pm.long_px), float(pm.short_px)), float(pm.angle_px_deg))
    full = np.zeros(g.shape, np.uint8)
    cv2.fillPoly(full, [cv2.boxPoints(rect).astype(np.int32)], 255)
    inner = np.zeros(g.shape, np.uint8)
    small = (rect[0], (rect[1][0] * shrink, rect[1][1] * shrink), rect[2])
    cv2.fillPoly(inner, [cv2.boxPoints(small).astype(np.int32)], 255)
    if not full.any() or not inner.any():
        return 0.0
    ref = float(np.percentile(g[full > 0], 90))
    return float((g[inner > 0] < rel * ref).mean())


def measure_part(img, nozzle_px, search_radius_px, min_area_px=200, expected_px=None):
    """Segment the part held on the nozzle (up camera) and fit a rotated rectangle.

    expected_px=(long, short) body size in pixels: try several black/white cut-offs and keep
    the blob whose size matches best. Needed for chip parts, whose bright metal ends and
    mid-grey body split apart under Otsu (it measured one end, 1.37 x 0.58 mm, of an 0805).
    The cut-offs are relative to the median of the crop (= the nozzle face behind the part).
    Without expected_px: Otsu, blob closest to the nozzle axis (first-cut behaviour)."""
    h, w = img.shape[:2]
    nx, ny = nozzle_px
    r = int(search_radius_px)
    x0, y0 = max(int(nx) - r, 0), max(int(ny) - r, 0)
    x1, y1 = min(int(nx) + r, w), min(int(ny) + r, h)
    crop = cv2.GaussianBlur(_gray(img)[y0:y1, x0:x1], (5, 5), 0)
    masks = []
    for mode in (cv2.THRESH_BINARY_INV, cv2.THRESH_BINARY):
        masks.append(cv2.threshold(crop, 0, 255, mode | cv2.THRESH_OTSU)[1])
    if expected_px is not None:
        med = float(np.median(crop))
        k = np.ones((3, 3), np.uint8)
        for d in (8, 12, 16, 20, 25, 30, 40, 50):
            for mode, t in ((cv2.THRESH_BINARY, med + d), (cv2.THRESH_BINARY_INV, med - d)):
                if 0 < t < 255:
                    bw = cv2.threshold(crop, t, 255, mode)[1]
                    masks.append(cv2.morphologyEx(bw, cv2.MORPH_OPEN, k))
    best = None
    for bw in masks:
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
            d = np.hypot(cx + x0 - nx, cy + y0 - ny)
            if expected_px is None:
                score = d                      # prefer the blob closest to the nozzle axis
            else:
                el, es = expected_px
                fill = a / max(rw * rh, 1.0)   # 1 = solid rectangle; rings/crescents score low
                score = abs(rw - el) / el + abs(rh - es) / es + 0.2 * d / max(r, 1) + (1.0 - fill)
            if best is None or score < best[0]:
                best = (score, PartMeasure((cx + x0, cy + y0), float(rw), float(rh), float(ang), float(a)))
    return None if best is None else best[1]
