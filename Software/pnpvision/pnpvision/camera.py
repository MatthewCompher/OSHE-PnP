"""Threaded V4L2 capture that always holds the newest frame.

Why threaded: OpenCV/V4L2 buffers frames, so a plain cap.read() right after a
move can return a stale image. A background thread drains the buffer, and
fresh() waits for a frame that arrived *after* the machine settled.
"""
import threading
import time

import cv2


class Camera:
    def __init__(self, device, width=1280, height=720, fps=30,
                 fourcc="MJPG", exposure=0, name="cam"):
        self.device, self.width, self.height = device, width, height
        self.fps, self.fourcc, self.exposure, self.name = fps, fourcc, exposure, name
        self._cap = None
        self._frame = None
        self._t = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
        if not cap.isOpened():
            raise RuntimeError(f"{self.name}: cannot open {self.device} "
                               "(is crowsnest already using it?)")
        # MJPG first: YUYV at 720p is only 5 fps on these modules.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        cap.set(cv2.CAP_PROP_FPS, self.fps)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if self.exposure:
            cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)   # 1 = manual on V4L2
            cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure)
        got = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
        if got != (self.width, self.height):
            cap.release()
            raise RuntimeError(f"{self.name}: asked {self.width}x{self.height}, got {got}. "
                               "Calibration is only valid at its own resolution.")
        self._cap = cap
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.fresh(settle_s=0.0, timeout=3.0)   # block until first frame
        return self

    def _loop(self):
        while not self._stop.is_set():
            ok, frame = self._cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            with self._lock:
                self._frame, self._t = frame, time.monotonic()

    def latest(self):
        with self._lock:
            return (None if self._frame is None else self._frame.copy()), self._t

    def fresh(self, settle_s=0.15, timeout=2.0):
        """Return a frame captured at least `settle_s` from now (covers USB/driver latency)."""
        deadline_t = time.monotonic() + settle_s
        t_end = time.monotonic() + settle_s + timeout
        while time.monotonic() < t_end:
            frame, t = self.latest()
            if frame is not None and t > deadline_t:
                return frame
            time.sleep(0.005)
        raise TimeoutError(f"{self.name}: no fresh frame")

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._cap:
            self._cap.release()

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.stop()


class SnapshotCamera:
    """Frames from crowsnest/ustreamer's snapshot URL, so crowsnest (and the Mainsail
    views) keep running while vision works. Same interface as Camera.

    Freshness: ustreamer caches its newest frame, so one fetch right after a move can
    return a frame exposed while the toolhead was still moving. fresh() waits settle_s,
    fetches once, then keeps fetching until ustreamer's X-Timestamp changes: that next
    frame was captured after the request, i.e. after the machine settled.
    """

    def __init__(self, url, width, height, name="cam", timeout=5.0):
        self.url, self.width, self.height, self.name = url, width, height, name
        self.timeout = timeout
        self._frame, self._t = None, 0.0

    def _fetch(self):
        import urllib.request
        import numpy as np
        with urllib.request.urlopen(self.url, timeout=self.timeout) as r:
            data, ts = r.read(), r.headers.get("X-Timestamp")
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            raise RuntimeError(f"{self.name}: snapshot from {self.url} is not an image "
                               "(is crowsnest running? try it in a browser)")
        return frame, ts

    def start(self):
        frame, _ = self._fetch()
        h, w = frame.shape[:2]
        if (w, h) != (self.width, self.height):
            raise RuntimeError(f"{self.name}: snapshot is {w}x{h}, config says "
                               f"{self.width}x{self.height}. Fix crowsnest.conf or config.toml; "
                               "the calibration is only valid at its own resolution.")
        self._frame, self._t = frame, time.monotonic()
        return self

    def latest(self):
        return (None if self._frame is None else self._frame.copy()), self._t

    def fresh(self, settle_s=0.15, timeout=2.0):
        time.sleep(settle_s)
        _, ts0 = self._fetch()
        t_end = time.monotonic() + timeout
        while True:
            frame, ts = self._fetch()
            if ts is None:                        # no timestamp header: just skip a frame
                time.sleep(0.15)
                frame, _ = self._fetch()
                break
            if ts != ts0:
                break
            if time.monotonic() > t_end:
                raise TimeoutError(f"{self.name}: snapshot frame never updated "
                                   "(is the camera stream frozen?)")
            time.sleep(0.01)
        self._frame, self._t = frame, time.monotonic()
        return frame.copy()

    def stop(self):
        pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.stop()
