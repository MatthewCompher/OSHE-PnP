"""Minimal Moonraker client: run G-code, read position, bounded moves."""
import requests


class MoveRefused(Exception):
    pass


class Moonraker:
    def __init__(self, url="http://localhost:7125", feedrate=3000,
                 x_range=(0, 300), y_range=(0, 300), z_range=(0, 60), timeout=120):
        self.url, self.feedrate, self.timeout = url.rstrip("/"), feedrate, timeout
        self.limits = {"x": x_range, "y": y_range, "z": z_range}

    # -- raw ---------------------------------------------------------------
    def gcode(self, script):
        """Blocks until Klipper has executed the script (the endpoint returns when done)."""
        r = requests.post(f"{self.url}/printer/gcode/script",
                          json={"script": script}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def status(self, obj="toolhead"):
        r = requests.get(f"{self.url}/printer/objects/query?{obj}", timeout=10)
        r.raise_for_status()
        return r.json()["result"]["status"][obj]

    def position(self):
        x, y, z = self.status("toolhead")["position"][:3]
        return x, y, z

    def is_homed(self, axes="xyz"):
        return all(a in self.status("toolhead")["homed_axes"] for a in axes)

    # -- bounded moves -----------------------------------------------------
    def _check(self, axis, v):
        lo, hi = self.limits[axis]
        if not (lo <= v <= hi):
            raise MoveRefused(f"{axis}={v:.3f} outside software limit [{lo}, {hi}]")

    def move_abs(self, x=None, y=None, z=None, feedrate=None):
        if not self.is_homed():
            raise MoveRefused("axes not homed")
        words = []
        for axis, v in (("x", x), ("y", y), ("z", z)):
            if v is not None:
                self._check(axis, v)
                words.append(f"{axis.upper()}{v:.4f}")
        if not words:
            return
        f = feedrate or self.feedrate
        self.gcode(f"G90\nG1 {' '.join(words)} F{f:.0f}\nM400")

    def move_rel(self, dx=0.0, dy=0.0, dz=0.0, feedrate=None):
        x, y, z = self.position()
        self.move_abs(x + dx if dx else None, y + dy if dy else None,
                      z + dz if dz else None, feedrate)
