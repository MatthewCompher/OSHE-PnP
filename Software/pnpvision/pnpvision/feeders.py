"""Part sources for the job runner: servo tape feeders (Klipper servos on the Arduino Uno, or the
old feeder Nano over USB serial) and a manual tape track (you advance the tape by hand when asked).

`"servo": n` in feeders.json is the feeder SLOT: Klipper [servo feeder_n], counted left to right.

The feeders sit at the front of the machine, outside the staging plate; the down camera can't
reach them. So a pick position is TAUGHT with the nozzle (jog it down onto the part in the pocket
by eye: `teach-feeder`), and refined while running from the up camera: the grab offset of every
good pick moves that feeder's pick XY toward the real pocket centre.

Pick XY here is a TOOLHEAD position with the NOZZLE over the part (no down-camera offset), and
`part_top_z` is the Z where the reference tip touches the part (see tips.py: other tips shift it).

feeders.json:
  {"feeders": [{"id": "F1", "kind": "servo", "servo": 1, "xy": [x, y], "part_top_z": 37.9,
                "package": "R_0805_2012Metric", "value": "", "tape_angle_deg": 0.0,
                "learned_xy": [dx, dy]}, ...]}
  kind "manual": no servo; the runner asks you to advance the tape before each pick.
  value "" = any value of that package. tape_angle_deg: machine-frame angle of the part's job
  rot-0 orientation as it sits in the pocket (only needed for parts with a pin 1).

Nano protocol (feeder_nano.ino): "F<n>\n" -> "OK FEED <n> QUEUED", later "OK FEED <n> DONE";
"?\n" -> "STATE ...". Strokes run one at a time (current limit of the 5 V rail).
"""
import json
import os
import time

import numpy as np


class FeederError(RuntimeError):
    pass


# -- the Nano ------------------------------------------------------------------
class SerialFeederBus:
    """Talks to the feeder Nano. feed() returns at once; wait() blocks until that stroke is done."""

    def __init__(self, port, baud=115200, timeout_s=8.0):
        import serial                      # pyserial: only needed on the machine
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.timeout_s = timeout_s
        self.pending = set()
        time.sleep(2.0)                    # the Nano resets when the port opens
        self.ser.reset_input_buffer()

    def _lines(self):
        while True:
            raw = self.ser.readline()
            if not raw:
                return
            yield raw.decode(errors="replace").strip()

    def _pump(self):
        for line in self._lines():
            if line.startswith("OK FEED") and line.endswith("DONE"):
                self.pending.discard(int(line.split()[2]))
            elif line.startswith("ERR"):
                raise FeederError(f"feeder Nano: {line}")

    def feed(self, servo):
        self.ser.write(f"F{int(servo)}\n".encode())
        self.pending.add(int(servo))

    def wait(self, servo):
        t0 = time.time()
        while int(servo) in self.pending:
            self._pump()
            if time.time() - t0 > self.timeout_s:
                raise FeederError(f"feeder servo {servo}: no DONE within {self.timeout_s} s")

    def close(self):
        self.ser.close()


# -- the Uno (Klipper) ---------------------------------------------------------
class KlipperFeederBus:
    """Feeder servos on the Arduino Uno as Klipper [servo feeder_N] (Klipper/pnp_feeders.cfg).
    feed() runs FEEDER_TOGGLE SLOT=n through Moonraker and returns when the stroke is done (the
    macro dwells with G4, so the head waits too, ~0.8 s); wait() then has nothing left to do."""

    def __init__(self, mr, macro="FEEDER_TOGGLE"):
        self.mr, self.macro = mr, macro

    def feed(self, servo):
        try:
            self.mr.gcode(f"{self.macro} SLOT={int(servo)}")
        except Exception as e:                 # Klipper's error (bad slot, no servo section) comes back here
            raise FeederError(f"feeder slot {servo}: {self.macro} failed: {e}") from e

    def wait(self, servo):
        pass

    def close(self):
        pass


class SimFeederBus:
    """For tests and dry runs: strokes finish instantly; on_feed(servo) lets a simulator react."""

    def __init__(self, on_feed=None):
        self.on_feed = on_feed or (lambda servo: None)
        self.strokes = []

    def feed(self, servo):
        self.strokes.append(int(servo))
        self.on_feed(int(servo))

    def wait(self, servo):
        pass

    def close(self):
        pass


# -- feeders -------------------------------------------------------------------
class Feeder:
    LEARN_GAIN = 0.5           # share of each good pick's grab offset folded into learned_xy
    LEARN_LIMIT_MM = 0.6       # a grab offset this big is a bad pick, not a pocket position

    def __init__(self, d, bus=None, ask=input):
        self.d, self.bus, self.ask = d, bus, ask
        self.d.setdefault("learned_xy", [0.0, 0.0])
        self.by_hand = False       # run-job --no-feeders: you put each part in the pocket

    id = property(lambda s: s.d["id"])
    kind = property(lambda s: s.d.get("kind", "servo"))
    package = property(lambda s: s.d.get("package", ""))
    value = property(lambda s: s.d.get("value", ""))

    def pick_xy(self):
        return np.asarray(self.d["xy"], float) + np.asarray(self.d["learned_xy"], float)

    def ready(self):
        """Make sure a part is in the pocket before picking."""
        if self.kind == "manual" or self.by_hand:
            self.ask(f"Feeder {self.id} ({self.package}): advance the tape one part by hand, "
                     f"then press Enter... ")
        elif self.bus is not None:
            self.bus.wait(self.d["servo"])

    def after_pick(self):
        """Start the next stroke right away: it runs while the head inspects and places."""
        if self.kind == "servo" and self.bus is not None and not self.by_hand:
            self.bus.feed(self.d["servo"])

    def learn(self, grab_offset_mm):
        """Up camera: the part sat at grab_offset (part centre minus nozzle axis), so the pocket
        is that far from where we picked."""
        g = np.asarray(grab_offset_mm, float)
        if np.linalg.norm(g) > self.LEARN_LIMIT_MM:
            return
        self.d["learned_xy"] = (np.asarray(self.d["learned_xy"], float) + self.LEARN_GAIN * g).tolist()


class FeederBank:
    def __init__(self, feeders):
        self.feeders = list(feeders)

    @classmethod
    def load(cls, path, bus=None, ask=input):
        if not os.path.exists(path):
            return cls([])
        with open(path, encoding="utf-8") as f:
            return cls([Feeder(d, bus, ask) for d in json.load(f).get("feeders", [])])

    def save(self, path):
        from .machine_state import write_json_atomic
        write_json_atomic(path, {"feeders": [fd.d for fd in self.feeders]})

    def get(self, fid):
        for fd in self.feeders:
            if fd.id == fid:
                return fd
        return None

    def for_placement(self, p):
        """The job's `feeder` field if given, else the first feeder holding that package (and value,
        if the feeder names one)."""
        if p.get("feeder"):
            fd = self.get(p["feeder"])
            if fd is None:
                raise FeederError(f"{p['ref']}: job names feeder {p['feeder']}, not in feeders.json")
            return fd
        for fd in self.feeders:
            if fd.package == p["package"] and (not fd.value or fd.value == p.get("value", "")):
                return fd
        return None

    def check_spacing(self, expected_mm=(14.0, 22.0)):
        """Feeders sit in one row at a uniform pitch: report taught positions that don't fit."""
        xs = sorted((fd.d["xy"][0], fd.id) for fd in self.feeders)
        out = []
        for (x0, a), (x1, b) in zip(xs, xs[1:]):
            if not (expected_mm[0] <= x1 - x0 <= expected_mm[1]):
                out.append(f"{a} -> {b}: {x1 - x0:.1f} mm apart (expected {expected_mm[0]}-{expected_mm[1]})")
        return out
