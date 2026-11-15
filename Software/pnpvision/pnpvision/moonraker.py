"""Minimal Moonraker client: run G-code, read position, bounded moves."""
import requests


class MoveRefused(Exception):
    pass


class Moonraker:
    def __init__(self, url="http://localhost:7125", feedrate=3000,
                 x_range=(0, 300), y_range=(0, 300), z_range=(0, 60), timeout=120,
                 safe_travel_z=None):
        """safe_travel_z: on this machine larger Z = nozzle LOWER. Before any XY move the
        nozzle is lifted to at least this height (Z <= safe_travel_z), so it clears the
        datum, reject bin and PCB clamps. None disables the guard."""
        self.url, self.feedrate, self.timeout = url.rstrip("/"), feedrate, timeout
        self.limits = {"x": x_range, "y": y_range, "z": z_range}
        self.safe_travel_z = safe_travel_z

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

    def objects(self):
        """Names of all Klipper objects and loaded config sections, e.g. 'gcode_macro VALVE_ON'.
        objects/list only has objects with a status (it leaves out [manual_stepper ...]), so the
        section names from configfile.settings are added."""
        r = requests.get(f"{self.url}/printer/objects/list", timeout=10)
        r.raise_for_status()
        names = list(r.json()["result"]["objects"])
        try:
            settings = self.query("configfile").get("settings", {})
        except requests.RequestException:
            settings = {}
        return names + [k for k in settings if k not in names]

    def query(self, obj):
        """One object's status; for names with spaces, e.g. 'gcode_macro PNP_ANSWER'."""
        r = requests.get(f"{self.url}/printer/objects/query", params={obj: ""}, timeout=10)
        r.raise_for_status()
        return r.json()["result"]["status"].get(obj, {})

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

    # Largest X/Y move allowed with stay_low=True (nozzle left below safe_travel_z).
    MAX_LOW_XY_MM = 3.0

    def move_abs(self, x=None, y=None, z=None, feedrate=None, stay_low=False):
        """stay_low: small X/Y jogs (<= MAX_LOW_XY_MM) at the CURRENT height, without the
        safety lift. For centring the nozzle over the up camera at its focus height."""
        if not self.is_homed():
            raise MoveRefused("axes not homed")
        for axis, v in (("x", x), ("y", y), ("z", z)):
            if v is not None:
                self._check(axis, v)
        f = feedrate or self.feedrate
        cx, cy, cz = self.position()
        xy = [f"{a.upper()}{v:.4f}" for a, v, c in (("x", x, cx), ("y", y, cy))
              if v is not None and abs(v - c) > 1e-6]
        lines = ["G90"]
        low = xy and self.safe_travel_z is not None and cz > self.safe_travel_z + 1e-6
        if low and stay_low:
            d = ((x if x is not None else cx) - cx) ** 2 + ((y if y is not None else cy) - cy) ** 2
            if d ** 0.5 > self.MAX_LOW_XY_MM:
                raise MoveRefused(f"stay_low X/Y move of {d ** 0.5:.2f} mm is over the "
                                  f"{self.MAX_LOW_XY_MM} mm limit for moves below Z{self.safe_travel_z}")
        elif low:
            # nozzle is below travel height: lift straight up before moving sideways
            lines.append(f"G1 Z{self.safe_travel_z:.4f} F{f:.0f}")
        if xy:
            lines.append(f"G1 {' '.join(xy)} F{f:.0f}")
        if z is not None:
            # Z last: going down only happens once the nozzle is over the target
            lines.append(f"G1 Z{z:.4f} F{f:.0f}")
        if len(lines) == 1:
            return
        self.gcode("\n".join(lines + ["M400"]))

    def move_rel(self, dx=0.0, dy=0.0, dz=0.0, feedrate=None, stay_low=False):
        x, y, z = self.position()
        self.move_abs(x + dx if dx else None, y + dy if dy else None,
                      z + dz if dz else None, feedrate, stay_low=stay_low)


def lift(mr, feedrate=None):
    """Raise the nozzle to travel height if it is below it; never lower it (larger Z = lower on this
    machine, so a nozzle at e.g. Z5 after homing stays there). Works with any object that has
    position(), move_abs() and safe_travel_z (also the test fakes)."""
    if mr.safe_travel_z is not None and mr.position()[2] > mr.safe_travel_z + 1e-6:
        mr.move_abs(z=mr.safe_travel_z, feedrate=feedrate)
