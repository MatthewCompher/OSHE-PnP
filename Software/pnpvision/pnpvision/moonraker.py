"""Minimal Moonraker client: run G-code, read position, bounded moves."""
import requests


class MoveRefused(Exception):
    pass


class Moonraker:
    def __init__(self, url="http://localhost:7125", feedrate=3000,
                 x_range=(0, 300), y_range=(0, 300), z_range=(0, 60), timeout=120,
                 safe_travel_z=None, front_zone_y=None, front_zone_z=None):
        """safe_travel_z: on this machine larger Z = nozzle LOWER. Before any XY move the
        nozzle is lifted to at least this height (Z <= safe_travel_z), so it clears the
        datum, reject bin and PCB clamps. None disables the guard.
        front_zone_y / front_zone_z: the feeders at the front. An XY move that starts or ends
        at Y < front_zone_y first lifts the nozzle to at least front_zone_z (2026-11-14: Y30, Z22)."""
        self.url, self.feedrate, self.timeout = url.rstrip("/"), feedrate, timeout
        self.limits = {"x": x_range, "y": y_range, "z": z_range}
        self.safe_travel_z = safe_travel_z
        self.front_zone_y, self.front_zone_z = front_zone_y, front_zone_z
        # Streaming (run-job, feeder-cycle): moves are queued without M400, so Klipper blends
        # them instead of stopping ~0.3 s after each one (it starts every new batch of motion
        # 0.25 s in the future), and the toolhead position / homed state come from a local
        # cache instead of a 0.1-0.2 s query per move. Call wait() before anything that needs
        # the machine to BE there (a camera frame). Valve, servo and dwell commands are queued
        # in order with the moves by Klipper, so they need no wait.
        self.stream = False
        self._pos = None
        self._homed = False

    def set_stream(self, on):
        self.stream = bool(on)
        self._pos, self._homed = None, False

    # -- raw ---------------------------------------------------------------
    MOVING = ("G0", "G1", "G28", "G92", "SET_KINEMATIC_POSITION", "FORCE_MOVE")

    _own_move = False                      # set by move_abs around its own G1 lines

    def gcode(self, script):
        """Returns when Klipper has PROCESSED the script; moves have finished only if it ends with
        M400 (or another waiting command)."""
        if not self._own_move and any(m in script.upper() for m in self.MOVING):
            self._pos, self._homed = None, False          # something else moved the toolhead
        try:
            r = requests.post(f"{self.url}/printer/gcode/script",
                          json={"script": script}, timeout=self.timeout)
            r.raise_for_status()
        except Exception:
            self._pos, self._homed = None, False
            raise
        return r.json()

    def wait(self):
        """Block until every queued move has finished (streaming mode)."""
        self.gcode("M400")

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
        if self.stream and self._pos is not None:
            return self._pos
        x, y, z = self.status("toolhead")["position"][:3]
        self._pos = (x, y, z)
        return x, y, z

    def is_homed(self, axes="xyz"):
        if self.stream and self._homed:
            return True
        ok = all(a in self.status("toolhead")["homed_axes"] for a in axes)
        self._homed = ok and axes == "xyz"
        return ok

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
        travel_z = self.travel_z_for(cy, y if y is not None else cy) if xy else None
        low = xy and travel_z is not None and cz > travel_z + 1e-6
        if low and stay_low and travel_z != self.safe_travel_z:
            raise MoveRefused(f"no low X/Y moves near the feeders (Y < {self.front_zone_y}): "
                              f"the nozzle must be at Z{self.front_zone_z} or higher")
        if low and stay_low:
            d = ((x if x is not None else cx) - cx) ** 2 + ((y if y is not None else cy) - cy) ** 2
            if d ** 0.5 > self.MAX_LOW_XY_MM:
                raise MoveRefused(f"stay_low X/Y move of {d ** 0.5:.2f} mm is over the "
                                  f"{self.MAX_LOW_XY_MM} mm limit for moves below Z{self.safe_travel_z}")
        elif low:
            # nozzle is below travel height: lift straight up before moving sideways
            lines.append(f"G1 Z{travel_z:.4f} F{f:.0f}")
        if xy:
            lines.append(f"G1 {' '.join(xy)} F{f:.0f}")
        if z is not None:
            # Z last: going down only happens once the nozzle is over the target
            lines.append(f"G1 Z{z:.4f} F{f:.0f}")
        if len(lines) == 1:
            return
        self._own_move = True
        try:
            self.gcode("\n".join(lines if self.stream else lines + ["M400"]))
        finally:
            self._own_move = False
        self._pos = (x if x is not None else cx, y if y is not None else cy, z if z is not None else cz)

    def travel_z_for(self, y_from, y_to):
        """Height (Z, smaller = higher) the nozzle needs for an X/Y move between these Y values:
        the travel height, or the feeder-zone height when either end is in the front strip."""
        z = self.safe_travel_z
        if self.front_zone_y is not None and self.front_zone_z is not None                 and min(y_from, y_to) < self.front_zone_y:
            z = self.front_zone_z if z is None else min(z, self.front_zone_z)
        return z

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
