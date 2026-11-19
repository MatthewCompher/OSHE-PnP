#!/usr/bin/env python3
"""
ChArUco capture + OpenCV calibration for the PnP down camera (headless Pi).

Grabs stills from the crowsnest snapshot URL instead of opening the camera
directly, so crowsnest keeps running and you can aim the board using the live
Mainsail webcam view in your browser.

Workflow:
  1. Open the live stream in a browser (http://<pi-ip>/) to aim the board.
  2. Jog the toolhead over the board; vary tilt and position every shot.
  3. In this script's terminal:
        <Enter>  capture a still (saved only if enough ChArUco corners found)
        k        calibrate from everything captured this run
        q        quit
  4. Open captures/<name>/annotated/*.png in VS Code to verify detections.

Board (from the calibrx.io generator):
  7 x 5 squares, 8 mm squares, 6 mm markers, DICT_4X4_50, start id 0.
After printing, replace the sizes below with what you MEASURE with calipers.

Needs OpenCV 4.7+ or 5.x (uses cv2.aruco.CharucoDetector). Check with:
    python3 -c "import cv2; print(cv2.__version__)"
"""

import argparse
import glob
import os
import time
import urllib.request

import cv2
import numpy as np

# ---- Board configuration (match your printed board) ------------------------
SQUARES_X, SQUARES_Y = 7, 5          # squares, not inner corners
SQUARE_SIZE_MM = 8.0                 # measure the printed square with calipers
MARKER_SIZE_MM = 6.0                 # measure the printed marker with calipers
ARUCO_DICT = cv2.aruco.DICT_4X4_50
LEGACY_BOARD = False                 # flip to True if corners won't detect
# ----------------------------------------------------------------------------

MIN_CORNERS = 8                      # min ChArUco corners to keep/use a frame

# Outlier rejection at calibration time: drop images whose own RMS is above
# max(OUTLIER_FLOOR_PX, OUTLIER_FACTOR x median image RMS), then re-solve.
OUTLIER_FACTOR = 3.0
OUTLIER_FLOOR_PX = 1.0
MAX_REJECT_PASSES = 3


def make_board():
    dictionary = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    board = cv2.aruco.CharucoBoard(
        (SQUARES_X, SQUARES_Y), SQUARE_SIZE_MM, MARKER_SIZE_MM, dictionary
    )
    if LEGACY_BOARD:
        board.setLegacyPattern(True)
    return board, dictionary


def make_detector(board):
    """CharucoDetector tuned for a close-up camera that sees only part of the board.

    minMarkers=1 lets a chessboard corner be used when just one of its two
    neighbouring markers is visible (the default needs both), which roughly
    doubles the corners per frame when the board overfills the view. Each
    corner is still sub-pixel refined on the real chessboard saddle point.
    The looser polygon fit tolerates marker edges bent by lens distortion.
    """
    cp = cv2.aruco.CharucoParameters()
    cp.minMarkers = 1
    cp.tryRefineMarkers = True
    dp = cv2.aruco.DetectorParameters()
    dp.polygonalApproxAccuracyRate = 0.08
    dp.adaptiveThreshWinSizeMin = 3
    dp.adaptiveThreshWinSizeMax = 53
    dp.adaptiveThreshWinSizeStep = 4
    return cv2.aruco.CharucoDetector(board, cp, dp)


def detect(detector, gray):
    """detectBoard with shapes normalized to the OpenCV 4.x layout.

    OpenCV 5 returns ChArUco corners as (N, 2) and ids as (N,), which the
    drawing/matching functions reject; reshape to (N, 1, 2) / (N, 1) so the
    rest of the script works the same on 4.7+ and 5.x.
    """
    cc, ci, mc, mi = detector.detectBoard(gray)
    if ci is not None and len(ci) > 0:
        cc = np.asarray(cc, np.float32).reshape(-1, 1, 2)
        ci = np.asarray(ci, np.int32).reshape(-1, 1)
    else:
        cc, ci = None, None
    if mi is not None and len(mi) > 0:
        mc = tuple(np.asarray(c, np.float32).reshape(1, 4, 2) for c in mc)
        mi = np.asarray(mi, np.int32).reshape(-1, 1)
    else:
        mc, mi = (), None
    return cc, ci, mc, mi


def grab(url):
    """Fetch one JPEG snapshot and decode to BGR. Returns frame or None."""
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = r.read()
    except Exception as e:
        print(f"  snapshot fetch failed: {e}")
        return None
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        print("  could not decode snapshot (is the URL serving a JPEG?)")
    return frame


def annotate(frame, cc, ci, mc, mi):
    vis = frame.copy()
    if mi is not None and len(mi) > 0:
        cv2.aruco.drawDetectedMarkers(vis, mc, mi)
    if ci is not None and len(ci) > 0:
        cv2.aruco.drawDetectedCornersCharuco(vis, cc, ci, (0, 0, 255))
    return vis


def calibrate(image_dir, board, detector):
    paths = sorted(glob.glob(os.path.join(image_dir, "capture_*.png")))
    if len(paths) < 5:
        print(f"Need ~5+ captures (15-25 is better); found {len(paths)}.")
        return

    all_obj, all_img, names, img_size, used = [], [], [], None, 0
    for p in paths:
        img = cv2.imread(p)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img_size = gray.shape[::-1]
        cc, ci, mc, mi = detect(detector, gray)
        n = 0 if ci is None else len(ci)
        if n >= MIN_CORNERS:
            obj, imgp = board.matchImagePoints(cc, ci)
            if obj is not None and len(obj) >= 6:
                # OpenCV 5 returns (N, 3)/(N, 2); keep the 4.x (N, 1, k) layout
                all_obj.append(np.asarray(obj, np.float32).reshape(-1, 1, 3))
                all_img.append(np.asarray(imgp, np.float32).reshape(-1, 1, 2))
                names.append(os.path.basename(p))
                used += 1
        else:
            print(f"  skipped ({n} corners): {os.path.basename(p)}")

    if used < 5:
        print(f"Only {used} usable images; capture more varied views.")
        return

    keep = list(range(len(all_obj)))
    rejected = []
    for attempt in range(MAX_REJECT_PASSES + 1):
        rms, K, dist, errs = solve([all_obj[i] for i in keep],
                                   [all_img[i] for i in keep], img_size)
        med = float(np.median(errs))
        limit = max(OUTLIER_FLOOR_PX, OUTLIER_FACTOR * med)
        bad = [k for k, e in zip(keep, errs) if e > limit]
        if not bad or len(keep) - len(bad) < 10 or attempt == MAX_REJECT_PASSES:
            break
        for k, e in zip(keep, errs):
            if e > limit:
                rejected.append((names[k], e))
        print(f"  pass rms {rms:.3f} px: dropping {len(bad)} outlier image(s) "
              f"(> {limit:.2f} px), re-solving")
        keep = [k for k in keep if k not in bad]

    print("\nWorst images (per-image RMS):")
    for k, e in sorted(zip(keep, errs), key=lambda t: -t[1])[:5]:
        print(f"  {names[k]}  {e:.3f} px")
    if rejected:
        print("Dropped as outliers (files left in place):")
        for n_, e in rejected:
            print(f"  {n_}  {e:.3f} px")

    print("\n=== Calibration result ===")
    print(f"Images used:        {len(keep)} of {len(paths)}")
    print(f"Image size:         {img_size}")
    print(f"RMS error:          {rms:.4f} px   (aim for < ~0.5-1.0)")
    print(f"Median image RMS:   {med:.4f} px")
    print(f"Camera matrix:\n{K}")
    print(f"Distortion coeffs:\n{dist.ravel()}")

    name = os.path.basename(os.path.normpath(image_dir))
    out = os.path.join(image_dir, f"calibration_{name}.npz")
    np.savez(out, camera_matrix=K, dist_coeffs=dist, image_size=img_size, rms=rms,
             used_images=np.array([names[k] for k in keep]))
    print(f"\nSaved to {out}")


def solve(objs, imgs, img_size):
    """Calibrate and return (rms, K, dist, per-image RMS list).

    Seeds a sane guess: with mostly straight-down, partial-board views
    OpenCV 4.x's own initialisation can converge to a nonsense camera.
    k3 stays fixed at 0: near-flat views (all a fixed-height PnP camera with a
    shallow depth of field allows) don't constrain it, and freeing it made the
    distortion estimate ~3x less repeatable on the real cam_down captures
    without lowering the RMS at all.
    """
    w, h = img_size
    K0 = np.array([[w, 0, w / 2], [0, w, h / 2], [0, 0, 1]], np.float64)
    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        objs, imgs, img_size, K0, None,
        flags=cv2.CALIB_USE_INTRINSIC_GUESS | cv2.CALIB_FIX_K3
    )
    errs = []
    for o, im, r, t in zip(objs, imgs, rvecs, tvecs):
        proj, _ = cv2.projectPoints(o, r, t, K, dist)
        errs.append(float(np.sqrt(np.mean(np.sum((proj - im) ** 2, axis=2)))))
    return rms, K, dist, errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost/webcam/?action=snapshot",
                    help="crowsnest snapshot URL (try /webcam2/ for the other cam)")
    ap.add_argument("--name", default=None,
                    help="run name (default: timestamp); re-running resumes it")
    args = ap.parse_args()

    if tuple(map(int, cv2.__version__.split(".")[:2])) < (4, 7):
        print(f"OpenCV {cv2.__version__} is < 4.7; this script uses the newer "
              "ChArUco API. Tell me your version and I'll adapt it.")
        return

    board, _ = make_board()
    detector = make_detector(board)

    run_name = args.name or time.strftime("run_%Y%m%d_%H%M%S")
    out_dir = os.path.join("captures", run_name)
    os.makedirs(out_dir, exist_ok=True)
    count = len(glob.glob(os.path.join(out_dir, "capture_*.png")))

    print(f"Run folder: {out_dir}")
    print(f"Snapshot:   {args.url}")
    print("Aim with the live stream in your browser, then here:")
    print("  <Enter> capture | k calibrate | q quit\n")

    while True:
        cmd = input(f"[{count} saved] > ").strip().lower()
        if cmd == "q":
            break
        if cmd == "k":
            calibrate(out_dir, board, detector)
            continue
        frame = grab(args.url)
        if frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cc, ci, mc, mi = detect(detector, gray)
        n = 0 if ci is None else len(ci)
        if n >= MIN_CORNERS:
            count += 1
            raw = os.path.join(out_dir, f"capture_{count:03d}.png")
            cv2.imwrite(raw, frame)
            ann_dir = os.path.join(out_dir, "annotated")
            os.makedirs(ann_dir, exist_ok=True)
            cv2.imwrite(os.path.join(ann_dir, f"capture_{count:03d}.png"),
                        annotate(frame, cc, ci, mc, mi))
            print(f"  saved {raw}  ({n} corners)")
        else:
            print(f"  not saved: only {n} corners (need {MIN_CORNERS}); "
                  "reposition / check focus / try LEGACY_BOARD")


if __name__ == "__main__":
    main()