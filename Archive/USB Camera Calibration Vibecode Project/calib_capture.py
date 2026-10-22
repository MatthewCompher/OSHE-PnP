#!/usr/bin/env python3
"""
Thank you Claude

USB camera preview + checkerboard capture for OpenCV calibration.

Board: 8 x 11 squares, 15 mm each  ->  7 x 10 INNER corners.
(OpenCV counts inner corners, i.e. squares - 1 in each direction.)

Keys (click the preview window first so it has focus):
    SPACE / c : capture a frame (only saved if the checkerboard is detected)
    k         : run calibration on this run's captures (shows tracked corners)
    q / ESC   : quit

Usage:
    python calib_capture.py                 # camera 0, new timestamped run folder
    python calib_capture.py --name cam_A    # captures/cam_A/ (re-running resumes it)
    python calib_capture.py --camera 1      # a different camera
    python calib_capture.py --width 1280 --height 720 --fps 30
"""

import argparse
import glob
import os
import time

import cv2
import numpy as np

# ---- Board configuration ---------------------------------------------------
SQUARES_X, SQUARES_Y = 8, 11                       # squares on the printed board
PATTERN_SIZE = (SQUARES_X - 1, SQUARES_Y - 1)      # inner corners: (7, 10)
SQUARE_SIZE_MM = 15.0
# ----------------------------------------------------------------------------

CRITERIA = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

def find_corners(gray):
    """Detect checkerboard corners with sub-pixel refinement. Returns (found, corners)."""
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    found, corners = cv2.findChessboardCorners(gray, PATTERN_SIZE, flags)
    if found:
        corners = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), CRITERIA)
    return found, corners


def calibrate(image_dir):
    """Run cv2.calibrateCamera on all images in image_dir."""
    paths = sorted(glob.glob(os.path.join(image_dir, "*.png")))
    if len(paths) < 5:
        print(f"Need at least ~5 captures (preferably 15-25); found {len(paths)}.")
        return

    # 3D points of the board corners, in mm, Z = 0
    objp = np.zeros((PATTERN_SIZE[0] * PATTERN_SIZE[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:PATTERN_SIZE[0], 0:PATTERN_SIZE[1]].T.reshape(-1, 2)
    objp *= SQUARE_SIZE_MM

    annotated_dir = os.path.join(image_dir, "annotated")
    os.makedirs(annotated_dir, exist_ok=True)

    obj_points, img_points = [], []
    img_size = None
    for p in paths:
        img = cv2.imread(p)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img_size = gray.shape[::-1]
        found, corners = find_corners(gray)
        if found:
            obj_points.append(objp)
            img_points.append(corners)
            # Show the tracked inner corners for this image
            vis = img.copy()
            cv2.drawChessboardCorners(vis, PATTERN_SIZE, corners, found)
            cv2.putText(vis, os.path.basename(p), (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 0), 2)
            cv2.imshow("Calibration corners", vis)
            cv2.imwrite(os.path.join(annotated_dir, os.path.basename(p)), vis)
            cv2.waitKey(400)  # ~0.4 s per image; press any key to skip ahead
        else:
            print(f"  skipped (no corners): {p}")

    if len(obj_points) < 5:
        print("Too few usable images for calibration.")
        return

    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        obj_points, img_points, img_size, None, None
    )

    cv2.destroyWindow("Calibration corners")

    # Mean reprojection error
    total = 0.0
    for i in range(len(obj_points)):
        proj, _ = cv2.projectPoints(obj_points[i], rvecs[i], tvecs[i], K, dist)
        total += cv2.norm(img_points[i], proj, cv2.NORM_L2) / len(proj)
    mean_err = total / len(obj_points)

    print("\n=== Calibration result ===")
    print(f"Images used:        {len(obj_points)}")
    print(f"Image size:         {img_size}")
    print(f"RMS error:          {rms:.4f} px")
    print(f"Mean reproj. error: {mean_err:.4f} px")
    print(f"Camera matrix:\n{K}")
    print(f"Distortion coeffs:\n{dist.ravel()}")

    name = os.path.basename(os.path.normpath(image_dir))
    out = os.path.join(image_dir, f"calibration_{name}.npz")
    np.savez(out, camera_matrix=K, dist_coeffs=dist, image_size=img_size, rms=rms)
    print(f"\nSaved to {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0, help="camera index")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--name", default=None,
                    help="run name (default: timestamp). Output goes to captures/<name>/")
    args = ap.parse_args()

    run_name = args.name or time.strftime("run_%Y%m%d_%H%M%S")
    out_dir = os.path.join("captures", run_name)
    os.makedirs(out_dir, exist_ok=True)
    count = len(glob.glob(os.path.join(out_dir, "*.png")))
    print(f"Run folder: {out_dir}")

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera {args.camera}")

    actual = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    print(f"Camera resolution: {actual[0]}x{actual[1]}")
    print("SPACE/c = capture | k = calibrate | q/ESC = quit")
    print("Keep the same resolution for every capture and for later use.")

    win = "Calibration capture"
    flash_until = 0.0
    message = ""

    while True:
        ok, frame = cap.read()
        if not ok:
            print("Failed to read frame")
            break

        # Plain preview, no overlay
        display = frame.copy()
        cv2.putText(display, f"saved: {count}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 0), 2)
        if time.time() < flash_until:
            cv2.putText(display, message, (10, 65),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 200, 0), 2)

        cv2.imshow(win, display)
        key = cv2.waitKey(1) & 0xFF

        if key in (ord("q"), 27):
            break
        elif key in (ord(" "), ord("c")):
            # Only keep frames where the board is detected
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            found_full, _ = find_corners(gray)
            if found_full:
                count += 1
                path = os.path.join(out_dir, f"capture_{count:03d}.png")
                cv2.imwrite(path, frame)
                message = f"Saved {path}"
            else:
                message = "Not saved: board not found"
            print(message)
            flash_until = time.time() + 1.5
        elif key == ord("k"):
            calibrate(out_dir)

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()