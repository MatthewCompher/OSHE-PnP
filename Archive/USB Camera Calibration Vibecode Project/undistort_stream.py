#!/usr/bin/env python3
"""
Serve an undistorted copy of a crowsnest webcam stream, for viewing in Mainsail.

Reads the MJPEG stream crowsnest already serves, undistorts every frame with a
calibration .npz from calib_capture.py, and re-serves it as MJPEG:

    http://<pi>:8090/stream     live view   (Mainsail "Stream URL")
    http://<pi>:8090/snapshot   one JPEG    (Mainsail "Snapshot URL")

Both draw a reticle: a crosshair on the optical axis (the point pnpvision centres
features on; it is NOT the middle of the frame) and, given --motion, 1 mm ticks along
the machine's X and Y axes, true at the height the motion map was calibrated at.
Add ?reticle=0 for a clean view (e.g. /stream?reticle=0).

This is for humans looking at the dashboard. Vision code should read the RAW
crowsnest stream and apply the calibration itself at full resolution; don't
undistort this already-undistorted stream a second time.

Run:
    ./venv/bin/python undistort_stream.py \
        --calib captures/cam_down/calibration_cam_down.npz

It only touches the camera stream while someone is watching (or asked for a
snapshot in the last few seconds); otherwise it sleeps at ~0% CPU.

Options worth knowing:
    --scale 0.5   output size relative to the camera frame (less Pi CPU)
                  (the view always has square pixels and no black edges; same
                  geometry as pnpvision, so circles look round)
    --fps 10      cap on frames processed per second (keeps CPU free for Klipper)
    --motion F    pnpvision motion map (calibration/motion_down.json) for the mm ticks;
                  re-read automatically when calibrate-motion rewrites it
"""

import argparse
import http.server
import json
import os
import socketserver
import threading
import time
import urllib.parse
import urllib.request

import cv2
import numpy as np

BOUNDARY = b"undistortframe"


def mjpeg_frames(url):
    """Yield raw JPEG bytes from an MJPEG-over-HTTP stream, reconnecting on errors."""
    while True:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                buf = b""
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    buf += chunk
                    while True:
                        start = buf.find(b"\xff\xd8")
                        end = buf.find(b"\xff\xd9", start + 2) if start >= 0 else -1
                        if start < 0 or end < 0:
                            if start > 0:
                                buf = buf[start:]      # drop junk before next frame
                            break
                        yield buf[start:end + 2]
                        buf = buf[end + 2:]
        except Exception as e:
            print(f"source stream error: {e}; retrying in 2 s", flush=True)
            time.sleep(2)


def square_new_K(K, dist, in_size, out_size, centered=False):
    """Camera matrix for the undistorted image: SQUARE pixels (fx == fy) and as wide a view
    as possible with only valid pixels (no black edges). The optical axis sits where
    getOptimalNewCameraMatrix(alpha=0) puts it (off-centre on these lenses); centered=True
    moves it to the frame centre instead, which costs ~17% of the down camera's view.

    cv2.getOptimalNewCameraMatrix(alpha=0) fills the frame by scaling X and Y differently
    (on these wide lenses fy/fx came out 1.24 down, 1.17 up), which stretches circles into
    ovals and makes px->mm differ per axis. Keep this function identical to the copy in
    Software/pnpvision/pnpvision/lens.py so the Mainsail
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


class Undistorter:
    def __init__(self, calib_path, scale):
        d = np.load(calib_path)
        self.K = d["camera_matrix"]
        self.dist = d["dist_coeffs"]
        self.calib_size = tuple(int(v) for v in d["image_size"])
        self.scale = scale
        self.maps, self.size = None, None

    def _build(self, w, h):
        K = self.K.copy()
        if (w, h) != self.calib_size:
            # Same camera mode at a different resolution: scale the intrinsics.
            print(f"WARNING: stream is {w}x{h} but calibration was {self.calib_size[0]}x"
                  f"{self.calib_size[1]}; scaling it. Recalibrate if the aspect "
                  "ratio differs (a different sensor crop).", flush=True)
            K[0] *= w / self.calib_size[0]
            K[1] *= h / self.calib_size[1]
        out = (max(1, round(w * self.scale)), max(1, round(h * self.scale)))
        newK = square_new_K(K, self.dist, (w, h), out)
        self.maps = cv2.initUndistortRectifyMap(K, self.dist, None, newK, out, cv2.CV_16SC2)
        self.size = (w, h)
        self.center = (float(newK[0, 2]), float(newK[1, 2]))   # optical axis, output px
        self.px_scale = out[0] / self.calib_size[0]   # output px per calibration-size px
        print(f"undistorting {w}x{h} -> {out[0]}x{out[1]} (f={newK[0, 0]:.1f} px, centre {newK[0, 2]:.1f},{newK[1, 2]:.1f})", flush=True)

    def __call__(self, frame):
        h, w = frame.shape[:2]
        if self.size != (w, h):
            self._build(w, h)
        return cv2.remap(frame, *self.maps, cv2.INTER_LINEAR)


class Reticle:
    """Crosshair on the optical axis + mm ticks along the machine axes, from a pnpvision
    motion map (M maps a toolhead move in mm to the feature's shift in undistorted
    calibration-size pixels). Without a motion map: crosshair only."""

    # BGR yellow on a black outline: bright enough to survive JPEG (a 1 px pure-red line
    # loses its colour to chroma subsampling and turns dark).
    COLOR, SHADOW = (0, 230, 255), (0, 0, 0)

    def __init__(self, motion_path=None):
        self.path, self.mtime, self.axes = motion_path, None, None

    def _reload(self):
        if not self.path:
            return
        try:
            mt = os.stat(self.path).st_mtime
        except OSError:
            if self.mtime != "missing":
                print(f"reticle: {self.path} not found; crosshair only", flush=True)
            self.mtime, self.axes = "missing", None
            return
        if mt == self.mtime:
            return
        self.mtime = mt
        try:
            with open(self.path) as f:
                d = json.load(f)
            M = np.asarray(d["M"], float)
            # Where a point 1 mm away along machine +X / +Y appears, relative to the axis.
            # Camera on the head (down cam): opposite to the shift seen when the camera moves.
            sign = -1.0 if d.get("moving", "camera") == "camera" else 1.0
            self.axes = (sign * M[:, 0], sign * M[:, 1])
            print(f"reticle: loaded {self.path} ({np.linalg.norm(M[:, 0]):.1f} X, "
                  f"{np.linalg.norm(M[:, 1]):.1f} Y px/mm)", flush=True)
        except Exception as e:
            print(f"reticle: could not read {self.path}: {e}; crosshair only", flush=True)
            self.axes = None

    def _line(self, img, p, q):
        p = (int(round(p[0])), int(round(p[1])))
        q = (int(round(q[0])), int(round(q[1])))
        cv2.line(img, p, q, self.SHADOW, 3, cv2.LINE_8)
        cv2.line(img, p, q, self.COLOR, 1, cv2.LINE_8)

    def _text(self, img, s, p, size):
        p = (int(round(p[0])), int(round(p[1])))
        for dx in (-1, 0, 1):                     # outline by offsetting: a thicker stroke
            for dy in (-1, 0, 1):                 # would also widen the letter spacing
                if dx or dy:
                    cv2.putText(img, s, (p[0] + dx, p[1] + dy), cv2.FONT_HERSHEY_SIMPLEX, size,
                                self.SHADOW, 1, cv2.LINE_AA)
        cv2.putText(img, s, p, cv2.FONT_HERSHEY_SIMPLEX, size, self.COLOR, 1, cv2.LINE_AA)

    def _text_centered(self, img, s, p, size):
        (tw, th), _ = cv2.getTextSize(s, cv2.FONT_HERSHEY_SIMPLEX, size, 1)
        self._text(img, s, (p[0] - tw / 2, p[1] + th / 2), size)

    def draw(self, img, center, px_scale):
        self._reload()
        h, w = img.shape[:2]
        c = np.asarray(center, float)
        reach = float(np.hypot(w, h))
        font = max(0.5, h / 1100)
        if self.axes is None:                     # crosshair along the image axes
            self._line(img, (0, c[1]), (w, c[1]))
            self._line(img, (c[0], 0), (c[0], h))
            return img
        ax = [np.asarray(a) * px_scale for a in self.axes]   # output px per mm, machine X, Y
        for i, name in enumerate(("X", "Y")):
            a = ax[i]
            ppm = float(np.linalg.norm(a))
            u = a / ppm                            # image direction of machine +axis
            perp = ax[1 - i] / np.linalg.norm(ax[1 - i])   # ticks run along the other axis
            self._line(img, c - u * reach, c + u * reach)
            for n in range(1, int(reach / ppm) + 1):
                major = n % 5 == 0
                L = ppm * (0.35 if major else 0.15)
                for sgn in (1, -1):
                    p = c + sgn * n * a
                    if not (0 <= p[0] <= w and 0 <= p[1] <= h):
                        continue
                    self._line(img, p - perp * L, p + perp * L)
                    if major:
                        self._text_centered(img, f"{sgn * n:d}", p + perp * (L + 0.45 * ppm), font)
            # "+X" / "+Y" near where that axis leaves the frame on its positive side
            m = 40.0
            ts = []
            if abs(u[0]) > 1e-6:
                ts.append(((w - m if u[0] > 0 else m) - c[0]) / u[0])
            if abs(u[1]) > 1e-6:
                ts.append(((h - m if u[1] > 0 else m) - c[1]) / u[1])
            t = min([v for v in ts if v > 0] or [0.0])
            self._text_centered(img, "+" + name, c + u * t - perp * 0.7 * ppm, font * 1.2)
        self._text(img, "mm @ calibration height", (8, h - 10), font)
        return img


class Latest:
    """Newest encoded frame, plus who currently wants frames.

    The worker only pulls and processes the camera stream while someone is
    watching /stream or asked for /snapshot in the last IDLE_AFTER seconds,
    so the service costs ~nothing while the dashboard isn't open.
    """

    IDLE_AFTER = 5.0

    # Each frame comes in two variants, True = with reticle and False = clean; a variant
    # is only drawn and encoded while someone wants it.

    def __init__(self):
        self.jpg, self.seq = {True: None, False: None}, 0
        self.viewers = {True: 0, False: 0}
        self.last_demand = {True: -1e9, False: -1e9}
        self.cond = threading.Condition()

    def put(self, jpgs):
        with self.cond:
            self.jpg, self.seq = jpgs, self.seq + 1
            self.cond.notify_all()

    def wait_newer(self, seq, variant, timeout=5.0):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != seq, timeout=timeout)
            return self.jpg.get(variant), self.seq

    def _variants(self):
        now = time.monotonic()
        return {v for v in (True, False)
                if self.viewers[v] > 0 or now - self.last_demand[v] < self.IDLE_AFTER}

    def _wanted(self):
        return bool(self._variants())

    def demand(self, variant, viewer_delta=0):
        with self.cond:
            self.viewers[variant] += viewer_delta
            self.last_demand[variant] = time.monotonic()
            self.cond.notify_all()

    def wanted(self):
        with self.cond:
            return self._variants()

    def wait_until_wanted(self):
        with self.cond:
            self.cond.wait_for(self._wanted)


def worker(args, latest):
    und = Undistorter(args.calib, args.scale)
    reticle = Reticle(args.motion)
    min_dt = 1.0 / args.fps if args.fps > 0 else 0.0
    while True:
        latest.wait_until_wanted()           # sleep (0% CPU) until someone watches
        print("viewer connected: processing frames", flush=True)
        frames = mjpeg_frames(args.source)
        last = 0.0
        try:
            for raw in frames:
                variants = latest.wanted()
                if not variants:
                    break                    # nobody watching: disconnect and idle
                now = time.monotonic()
                if now - last < min_dt:
                    continue                 # skipped before decoding, so ~free
                last = now
                frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                img = und(frame)
                jpgs = {True: None, False: None}
                for v in sorted(variants):   # False (clean) first, before drawing on img
                    if v:
                        reticle.draw(img, und.center, und.px_scale)
                    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, args.quality])
                    if ok:
                        jpgs[v] = jpg.tobytes()
                latest.put(jpgs)
        finally:
            frames.close()                   # closes the connection to crowsnest
        print("no viewers: idle", flush=True)


def make_handler(latest):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path, _, query = self.path.partition("?")
            path = path.rstrip("/")
            # ?reticle=0 / off / false / no -> clean view; other parameters are ignored
            r = urllib.parse.parse_qs(query).get("reticle", ["1"])[-1].strip().lower()
            v = r not in ("0", "off", "false", "no")
            if path in ("", "/stream"):
                self.send_response(200)
                self.send_header("Content-Type",
                                 "multipart/x-mixed-replace; boundary=" + BOUNDARY.decode())
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                seq = latest.seq             # don't replay a stale frame from before
                latest.demand(v, +1)
                try:
                    while True:
                        jpg, new = latest.wait_newer(seq, v)
                        if new == seq or jpg is None:
                            continue         # timed out waiting; keep the connection
                        seq = new
                        self.wfile.write(b"--" + BOUNDARY + b"\r\nContent-Type: image/jpeg\r\n"
                                         + f"Content-Length: {len(jpg)}\r\n\r\n".encode()
                                         + jpg + b"\r\n")
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass                     # viewer closed the page
                finally:
                    latest.demand(v, -1)
            elif path == "/snapshot":
                seq = latest.seq
                latest.demand(v)             # wake the worker if it was idle
                jpg, new = latest.wait_newer(seq, v)  # a fresh frame, not a stale one
                if jpg is None and new != seq:        # variant just requested: next frame has it
                    jpg, new = latest.wait_newer(new, v)
                if jpg is None:
                    jpg = latest.jpg.get(v)  # timed out: fall back to the last frame
                if jpg is None:
                    self.send_error(503, "no frame yet")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpg)))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(jpg)
            else:
                self.send_error(404)

        def log_message(self, *a):
            pass

    return Handler


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--calib", required=True, help="calibration .npz from calib_capture.py")
    ap.add_argument("--source", default="http://localhost/webcam/?action=stream",
                    help="crowsnest MJPEG stream (use /webcam2/ for the second camera)")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--quality", type=int, default=80)
    ap.add_argument("--motion", help="pnpvision motion map .json for the reticle's mm ticks")
    args = ap.parse_args()

    latest = Latest()
    threading.Thread(target=worker, args=(args, latest), daemon=True).start()
    srv = Server(("0.0.0.0", args.port), make_handler(latest))
    print(f"serving http://0.0.0.0:{args.port}/stream  and  /snapshot", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
