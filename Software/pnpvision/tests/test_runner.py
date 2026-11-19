"""Job runner against a simulated machine: servo feeders (one pocket comes up empty, one part is
the wrong size), a manual track with an EEPROM (pin 1: full 360-degree orientation), a nozzle tip
change, and the real Test PCB job. Checks every part lands on its footprint at its angle.

Simulator frame: "nozzle frame" = the toolhead XY that puts the nozzle over a point. A board
point b (down-camera-centred) is at b + OFF in that frame; feeder pick spots are taught in it."""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
from pnpvision.board import BoardPose
from pnpvision.feeders import Feeder, FeederBank, SimFeederBus
from pnpvision.parts import package_info
from pnpvision.rotation import Rotator, rotate_xy
from pnpvision.runner import JobError, dry_run, plan_job, run_job

JOB = os.path.join(HERE, "..", "jobs", "Test PCB-top.job.json")
OFF = np.array([8.385, 52.930])
UP_XY = np.array([85.841, 137.697])
POSE = BoardPose(90.766, [170.348, 246.294])
TRUE_DIR = -1.0
TIPS = {"N14": {"board_touch_z": 38.25, "inspect_z": 34.5}, "N08": {"board_touch_z": 38.05, "inspect_z": 34.3},
        "N24": {"board_touch_z": 38.4, "inspect_z": 33.5}}
BIN = np.array([60.0, 130.0])

# Rough time model for the simulated clock (NOT measured on the machine): trapezoid moves at the
# requested feedrate with this acceleration, camera frame + detection per inspection, rotation speed.
ACCEL = 2000.0          # mm/s^2 (place-test runs with --accel 2000)
INSPECT_S = 0.6         # settle_s 0.25 + up-light settle 0.2 + snapshot/detection
ROT_DEG_S = 180.0       # nozzle rotation speed


class World:
    def __init__(self, feeders):
        self.xyz = [100.0, 100.0, 30.0]
        self.safe_travel_z = 30.0
        self.motor = 0.0
        self.held = None                 # dict(u=offset from nozzle, phi=rot-0 orientation, pkg, ref)
        self.pockets = {}                # feeder id -> part waiting in the pocket (or None)
        self.feeders = feeders
        self.landed, self.binned, self.events = [], [], []
        self.rng = np.random.default_rng(3)
        self.empty_next = {"F1"}         # first stroke of F1 leaves an empty pocket
        self.bad_next = {"F2"}           # first part F2 delivers is the wrong size
        self.counts = {}
        self.t = 0.0                     # simulated clock, s
        for fd in feeders:
            self.refill(fd.id)

    # -- feeders -------------------------------------------------------------
    def refill(self, fid):
        fd = next(f for f in self.feeders if f.id == fid)
        n = self.counts[fid] = self.counts.get(fid, 0) + 1
        if fid in self.empty_next and n == 2:
            self.pockets[fid] = None
            return
        true_xy = np.asarray(fd.d["xy"], float) + [0.12, -0.08]      # taught 0.14 mm off
        jitter = self.rng.normal(0, 0.03, 2)
        phi = fd.d.get("tape_angle_deg", 90.0) + self.rng.normal(0, 3.0)
        bad = fid in self.bad_next and n == 1
        self.pockets[fid] = dict(xy=true_xy + jitter, phi=phi, pkg=fd.package, bad=bad)

    def on_feed(self, servo):
        fd = next(f for f in self.feeders if f.d.get("servo") == servo)
        self.refill(fd.id)

    def manual_advance(self, prompt):
        self.events.append(prompt)
        if "advance the tape" in prompt:
            fid = prompt.split()[1]
            if self.pockets.get(fid) is None or self.counts.get(fid, 0) > 0 and self._taken.get(fid):
                self.refill(fid)
                self._taken[fid] = False
        return ""

    _taken = {}

    # -- machine -------------------------------------------------------------
    def position(self):
        return tuple(self.xyz)

    @staticmethod
    def move_s(dist, feedrate):
        v = feedrate / 60.0
        if dist <= v * v / ACCEL:                     # never reaches full speed
            return 2.0 * np.sqrt(dist / ACCEL)
        return dist / v + v / ACCEL

    def move_abs(self, x=None, y=None, z=None, feedrate=None):
        f = feedrate or 3000.0
        if (x is not None or y is not None) and self.xyz[2] > self.safe_travel_z + 1e-6:
            self.t += self.move_s(self.xyz[2] - self.safe_travel_z, f)
            self.xyz[2] = self.safe_travel_z
        new = [v if v is not None else c for v, c in zip((x, y, z), self.xyz)]
        dxy = float(np.hypot(new[0] - self.xyz[0], new[1] - self.xyz[1]))
        self.t += self.move_s(dxy, f) + self.move_s(abs(new[2] - self.xyz[2]), f)
        self.xyz = new

    def gcode(self, script):
        nozzle = np.array(self.xyz[:2])
        for line in script.splitlines():
            if line.startswith("G4 P"):
                self.t += float(line[4:]) / 1000.0
            if line.startswith("VALVE_ON") and self.held is None and self.xyz[2] > 37.0:
                for fid, part in self.pockets.items():
                    if part is not None and np.linalg.norm(part["xy"] - nozzle) < 0.5:
                        self.held = dict(u=part["xy"] - nozzle, phi=part["phi"], pkg=part["pkg"], bad=part["bad"])
                        self.pockets[fid] = None
                        self._taken[fid] = True
                        break
            elif line.startswith("VALVE_OFF") and self.held is not None:
                if np.linalg.norm(nozzle - BIN) < 0.5:
                    self.binned.append(self.held)
                elif self.xyz[2] > 36.0:
                    self.landed.append(dict(xy=nozzle + self.held["u"], phi=self.held["phi"], pkg=self.held["pkg"]))
                self.held = None
            elif line.startswith("MANUAL_STEPPER"):
                m = float(line.split("MOVE=")[1].split()[0])
                d = TRUE_DIR * (m - self.motor)
                self.t += abs(m - self.motor) / ROT_DEG_S
                self.motor = m
                if self.held is not None:
                    self.held["u"] = rotate_xy(self.held["u"], d)
                    self.held["phi"] += d

    def up_inspect(self, body, flip_check=False):
        self.t += INSPECT_S
        if self.held is None or np.linalg.norm(np.array(self.xyz[:2]) - UP_XY) > 0.01:
            return {"ok": False, "reason": "no part found"}
        pkg = package_info(self.held["pkg"])
        size = [s * (1.6 if self.held["bad"] else 1.0) for s in pkg["body_mm"]]
        long_axis = (self.held["phi"] + pkg["axis_deg"] + 90) % 180 - 90
        res = {"ok": True, "reason": "", "offset_mm": self.held["u"].tolist(),
               "angle_deg": float(long_axis), "size_mm": size}
        if body is not None and any(abs(a - b) > 0.3 for a, b in zip(size, body)):
            res.update(ok=False, reason="size")
        return res


def _job():
    job = json.load(open(JOB, encoding="utf-8"))
    job["placements"].append({"ref": "U1", "value": "AT24C02", "package": "SOIC-8_3.9x4.9mm_P1.27mm",
                              "x": 12.0, "y": 10.0, "rot": 90.0, "height_mm": 1.75})
    return job


def _bank(bus, ask):
    ds = [{"id": "F1", "kind": "servo", "servo": 1, "xy": [60.0, 20.0], "part_top_z": 37.4, "teach_tip": "N14",
           "package": "R_0805_2012Metric"},
          {"id": "F2", "kind": "servo", "servo": 2, "xy": [77.0, 20.0], "part_top_z": 37.6, "teach_tip": "N14",
           "package": "R_0402_1005Metric"},
          {"id": "F3", "kind": "manual", "xy": [94.0, 20.0], "part_top_z": 36.6, "teach_tip": "N14",
           "package": "SOIC-8_3.9x4.9mm_P1.27mm", "tape_angle_deg": 180.0}]
    return FeederBank([Feeder(d, bus, ask) for d in ds])


ONLY = ["R0805_18", "R0805_21", "R0402_1", "R0805_1", "R0402_5", "U1"]


def _run():
    job = _job()
    holder = {}
    bus = SimFeederBus(on_feed=lambda s: holder["w"].on_feed(s))
    asks = []

    def ask(prompt):
        asks.append(prompt)
        return holder["w"].manual_advance(prompt)

    bank = _bank(bus, ask)
    w = holder["w"] = World(bank.feeders)
    ms = {"down_cam_offset_mm": OFF.tolist(), "up_cam_xy_mm": UP_XY.tolist()}
    recentred = []
    stats = {}
    res = run_job(job, POSE, ms, w, w.up_inspect, Rotator(w.gcode, direction=TRUE_DIR), bank, TIPS,
                  only=set(ONLY), current_tip="N14", recentre=lambda t: recentred.append(t) or "ok",
                  reject_xy=BIN, ask=ask, say=lambda *a: None, clock=lambda: w.t, stats=stats)
    w.stats = stats
    return job, w, res, asks, recentred, bank


def test_plan_groups_by_tip_and_reports_problems():
    job = _job()
    bank = _bank(None, lambda p: "")
    steps, problems = plan_job(job, bank, TIPS, only=set(ONLY))
    tips = [s["tip"] for s in steps]
    assert tips == sorted(tips, key=lambda t: tips.index(t)), tips          # grouped
    assert tips == ["N08"] * 5 + ["N24"] and not problems, (tips, problems)
    _, problems = plan_job(job, bank, {"N08": TIPS["N08"]}, only=set(ONLY))
    assert any("N24 not measured" in p for p in problems), problems
    _, problems = plan_job(job, FeederBank([]), TIPS, only={"R0805_18"})
    assert any("no feeder" in p for p in problems), problems


def test_run_job_simulated():
    job, w, res, asks, recentred, bank = _run()
    assert [r["status"] for r in res] == ["placed"] * len(ONLY), res
    assert recentred == ["N08", "N24"], recentred                            # each tip once
    assert len(w.binned) == 1 and w.binned[0]["bad"], w.binned               # wrong-size part rejected
    assert len(w.landed) == len(ONLY), w.landed
    by_ref = {p["ref"]: p for p in job["placements"]}
    for r, land in zip(res, w.landed):
        p = by_ref[r["ref"]]
        target = POSE.to_machine([p["x"], p["y"]]) + OFF                     # nozzle frame
        assert np.linalg.norm(land["xy"] - target) < 0.01, (r["ref"], land["xy"], target)
        want = POSE.part_angle(p["rot"])
        sym = 180.0 if package_info(p["package"])["symmetric"] else 360.0
        err = (land["phi"] - want + sym / 2) % sym - sym / 2
        assert abs(err) < 1.5, (r["ref"], land["phi"], want)
    # F1's first stroke left the pocket empty: one retry; the learned pick spot moved toward the truth
    learned = np.asarray(bank.get("F1").d["learned_xy"])
    assert np.linalg.norm(learned - [0.12, -0.08]) < 0.08, learned
    assert any("F3" in a and "advance the tape" in a for a in asks), asks   # manual track prompt
    assert any("Fit nozzle tip N08" in a for a in asks), asks


def test_timing_and_stop():
    job, w, res, asks, recentred, bank = _run()
    st = w.stats
    assert st["placed"] == len(ONLY) and st["cph"] > 0, st
    assert all(r["cycle_s"] > 0 and {"pick", "inspect", "place"} <= set(r["t"]) for r in res), res
    # phases add up to the machine time (prompts excluded; the 'job done' lift is outside any phase)
    assert abs(sum(r["cycle_s"] for r in res) - st["machine_s"]) < 1.0, st
    print("  sim estimate (time model, not measured):", st["s_per_part"], "s/part,", st["cph"], "CPH,",
          st["mean_phase_s"])
    # HMI stop button: stops cleanly before the 3rd part
    job = _job()
    holder = {}
    bank = _bank(SimFeederBus(on_feed=lambda s: holder["w"].on_feed(s)), lambda p: holder["w"].manual_advance(p))
    w = holder["w"] = World(bank.feeders)
    calls = []
    res = run_job(job, POSE, {"down_cam_offset_mm": OFF.tolist(), "up_cam_xy_mm": UP_XY.tolist()}, w,
                  w.up_inspect, Rotator(w.gcode, direction=TRUE_DIR), bank, TIPS, only=set(ONLY),
                  current_tip="N08", reject_xy=BIN, ask=lambda p: "", say=lambda *a: None,
                  stop_requested=lambda: calls.append(1) or len(calls) > 2)
    assert len(res) == 2 and all(r["status"] == "placed" for r in res), res


def test_unsafe_z_refused():
    job = _job()
    bank = _bank(None, lambda p: "")
    bad_tips = dict(TIPS, N08={"board_touch_z": 41.0, "inspect_z": 34.5})
    w = World(bank.feeders)
    try:
        run_job(job, POSE, {"down_cam_offset_mm": OFF.tolist(), "up_cam_xy_mm": UP_XY.tolist()}, w,
                w.up_inspect, Rotator(w.gcode), bank, bad_tips, only={"R0805_18"}, say=lambda *a: None)
    except JobError as e:
        assert "Z" in str(e)
    else:
        raise AssertionError("expected a Z refusal")


def test_dry_run_visits_every_part():
    seen = []
    steps = dry_run(_job(), POSE, lambda xy, name: seen.append(name), say=lambda *a: None)
    assert len(seen) == len(steps) == 93


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS", n)


def test_show_pick_parks_down_camera_over_manual_pick_spot():
    """--show-pick (debug): at each manual feed prompt the DOWN camera is over the pick spot
    (nozzle pick XY minus the camera offset), and the job still places everything."""
    job = _job()
    holder = {}
    seen = []

    def ask(prompt):
        if "advance the tape" in prompt and prompt.split()[1] == "F3":
            seen.append(np.array(holder["w"].xyz[:2]))
        return holder["w"].manual_advance(prompt)

    bus = SimFeederBus(on_feed=lambda s: holder["w"].on_feed(s))
    bank = _bank(bus, ask)
    w = holder["w"] = World(bank.feeders)
    ms = {"down_cam_offset_mm": OFF.tolist(), "up_cam_xy_mm": UP_XY.tolist()}
    res = run_job(job, POSE, ms, w, w.up_inspect, Rotator(w.gcode, direction=TRUE_DIR), bank, TIPS,
                  only={"U1"}, current_tip="N24", reject_xy=BIN, ask=ask, say=lambda *a: None,
                  clock=lambda: w.t, show_pick=True)
    f3 = next(f for f in bank.feeders if f.id == "F3")
    assert seen, "no manual feed prompt"
    assert np.allclose(seen[0], np.asarray(f3.d["xy"], float) - OFF, atol=1e-6), seen[0]
    assert [r["status"] for r in res] == ["placed"]
