"""Job runner: place an oshe-pnp-job/1 file on the aligned board, parts from the feeders.

Per placement:
  tip change?  -> park, ask you to fit the tip, re-centre the new tip over the up camera
  pick         -> feeder ready (servo stroke done / you advanced the manual track), lower onto the
                  part at the feeder's pick XY, vacuum, lift; start the next stroke right away
  inspect      -> up camera: empty = feed again and retry (up to `retries`); wrong size = reject
  turn         -> to job rot + board rotation (chips: shortest way mod 180; parts with a pin 1:
                  coarse turn from the feeder's tape angle, camera only fine-corrects), re-inspect
  place        -> board XY + down_cam_offset - part offset on the nozzle, Z from the tip and
                  the part height, release, slow lift
  verify       -> (optional) up camera again: the nozzle must be empty

Timing: every placement record gets "t" = machine seconds per phase (tip, feed_wait, pick,
inspect, turn, place, verify, reject); time spent waiting for you at a prompt is left out and
counted as operator time. Pass a dict as `stats` to get the job totals (seconds per placed part,
CPH, mean seconds per phase), so the first real run shows where the time goes.

Hardware is injected (callables) so the whole job runs against a simulator in the tests. All
positions are toolhead XY; board points are "down camera centred" (BoardPose), feeder pick
positions are "nozzle over the part" (taught with the nozzle; the down camera can't reach them).
"""
import time
from contextlib import contextmanager

import numpy as np

from .parts import MAX_FINE_DEG, PackageError, feeder_part_top_z, package_info, tip_for
from .rotation import rotate_xy, shortest_turn

PHASES = ("tip", "feed_wait", "pick", "inspect", "turn", "place", "verify", "reject")

# Z feedrates (mm/min) for the runner's moves; override with config.toml [run] z_feeds.
# Must stay under printer.cfg max_z_velocity (50 mm/s = F3000). The nozzle is spring-loaded,
# which is what lets the final touch be 5 mm/s instead of 1.
Z_FEEDS = {
    "approach": 1800,    # down to approach_mm above the part / board (30 mm/s)
    "touch": 300,        # the last approach_mm onto the part / board (5 mm/s)
    "release_lift": 120, # first 0.5 mm up after letting go of a part (2 mm/s)
    "lift": 2400,        # back up to safe travel Z (40 mm/s)
    "inspect": 1800,     # down to the up camera's focus height (30 mm/s)
}


class JobError(RuntimeError):
    pass


def wrap180(a):
    return (float(a) + 180.0) % 360.0 - 180.0


def plan_job(job, feeders, tips, packages=None, only=None, need_feeders=True):
    """Resolve package, tip and feeder for every placement, grouped by tip (stable, in the order
    the tips first appear, so each tip goes on once). Returns (steps, problems)."""
    steps, problems = [], []
    for p in job["placements"]:
        if p.get("skip") or (only and p["ref"] not in only):
            continue
        try:
            pkg = package_info(p["package"], packages)
        except PackageError as e:
            problems.append(f"{p['ref']}: {e}")
            continue
        tip = tip_for(p, pkg)
        fd = feeders.for_placement(p) if feeders is not None else None
        if need_feeders:
            if not tip:
                problems.append(f"{p['ref']}: no nozzle tip for package {p['package']}")
            elif tip not in tips or not {"board_touch_z", "inspect_z"} <= set(tips[tip]):
                problems.append(f"{p['ref']}: tip {tip} not measured (needs board_touch_z, inspect_z)")
            if fd is None:
                problems.append(f"{p['ref']}: no feeder holds {p['package']} {p.get('value', '')}")
            elif not pkg["symmetric"] and "tape_angle_deg" not in fd.d:
                problems.append(f"{p['ref']}: feeder {fd.id} needs tape_angle_deg ({p['package']} has a pin 1)")
        steps.append(dict(p=p, pkg=pkg, tip=tip, feeder=fd))
    order = []
    for s in steps:
        if s["tip"] not in order:
            order.append(s["tip"])
    steps.sort(key=lambda s: order.index(s["tip"]))
    return steps, problems


def timing_summary(results, machine_s, operator_s):
    """Job totals from the per-placement "t" dicts."""
    placed = [r for r in results if r.get("status") == "placed"]
    n = len(placed)
    out = {"placed": n, "attempted": len(results), "machine_s": round(machine_s, 2),
           "operator_s": round(operator_s, 2),
           "s_per_part": round(machine_s / n, 2) if n else None,
           "cph": round(3600.0 * n / machine_s, 1) if n and machine_s > 0 else None,
           "mean_phase_s": {}}
    for ph in PHASES:
        vals = [float(r.get("t", {}).get(ph, 0.0)) for r in results]
        if any(vals):
            out["mean_phase_s"][ph] = round(sum(vals) / len(results), 2)
    return out


def format_timing(st):
    if not st.get("placed"):
        return f"timing: nothing placed ({st['machine_s']:.0f} s machine time)"
    phases = ", ".join(f"{k} {v:.1f}" for k, v in st["mean_phase_s"].items())
    return (f"timing: {st['s_per_part']:.1f} s per placed part = {st['cph']:.0f} CPH (spec 500 = 7.2 s); "
            f"machine {st['machine_s']:.0f} s, waiting for you {st['operator_s']:.0f} s\n"
            f"  mean s per part: {phases}")


def run_job(job, pose, ms, mr, up_inspect, rotator, feeders, tips, packages=None, only=None,
            current_tip=None, recentre=None, reject_xy=None, ask=input, say=print, log=None,
            pick_press=0.4, place_press=0.3, approach_mm=0.8, vac_ms=300, release_ms=500,
            retries=3, angle_tol_deg=1.0, verify_empty=True, clock=time.monotonic, stats=None,
            stop_requested=None, z_feeds=None):
    """Returns a list of per-placement result dicts. ms: machine state (down_cam_offset_mm,
    up_cam_xy_mm; recentre(tip) may update them in place). up_inspect(body_mm) -> UpCam result.
    stats: a dict, filled with timing_summary(). stop_requested(): checked before each part
    (the HMI stop button); True = stop cleanly there."""
    log = log or (lambda event, ok=None, **d: None)
    zf = {**Z_FEEDS, **(z_feeds or {})}
    steps, problems = plan_job(job, feeders, tips, packages, only)
    if problems:
        raise JobError("job can't run:\n  " + "\n  ".join(problems))
    for s in steps:
        z = tips[s["tip"]]["board_touch_z"] - s["p"]["height_mm"] + place_press
        zp = feeder_part_top_z(s["feeder"].d, s["tip"], tips) + pick_press
        for name, v in (("place", z), ("pick", zp), ("inspect", tips[s["tip"]]["inspect_z"])):
            if not (mr.safe_travel_z < v <= 40.0):
                raise JobError(f"{s['p']['ref']}: {name} Z {v:.2f} outside Z{mr.safe_travel_z}..40")

    # --- operator time: prompts (ours and the manual feeders') don't count as machine time ---
    waited = [0.0]

    def timed_prompt(f):
        def wrapped(prompt):
            t0 = clock()
            try:
                return f(prompt)
            finally:
                waited[0] += clock() - t0
        return wrapped

    user_ask = timed_prompt(ask)
    saved_asks = {}
    for s in steps:
        fd = s["feeder"]
        if id(fd) not in saved_asks:
            saved_asks[id(fd)] = (fd, fd.ask)
            fd.ask = timed_prompt(fd.ask)

    @contextmanager
    def timed(rec, name):
        t0, w0 = clock(), waited[0]
        try:
            yield
        finally:
            rec["t"][name] = rec["t"].get(name, 0.0) + (clock() - t0) - (waited[0] - w0)

    def lower_and(valve, z, wait_ms, slow_lift=False):
        mr.move_abs(z=z - approach_mm, feedrate=zf["approach"])
        mr.move_abs(z=z, feedrate=zf["touch"])
        mr.gcode(f"{valve}\nG4 P{int(wait_ms)}")
        if slow_lift:
            mr.move_abs(z=z - 0.5, feedrate=zf["release_lift"])
        mr.move_abs(z=mr.safe_travel_z, feedrate=zf["lift"])

    def look_up(tip, body):
        up = np.asarray(ms["up_cam_xy_mm"], float)
        mr.move_abs(x=float(up[0]), y=float(up[1]))
        mr.move_abs(z=tips[tip]["inspect_z"], feedrate=zf["inspect"])
        return up_inspect(body)

    def reject(rec, why):
        with timed(rec, "reject"):
            mr.move_abs(z=mr.safe_travel_z, feedrate=zf["lift"])
            if reject_xy is not None:
                mr.move_abs(x=float(reject_xy[0]), y=float(reject_xy[1]))
                mr.gcode(f"VALVE_OFF\nG4 P{int(release_ms)}")
            else:
                # don't just let go: the nozzle may be over the up camera's lens
                user_ask(f"  ({why}) no reject bin taught: hold a hand under the nozzle and press "
                         f"Enter to release the part... ")
                mr.gcode("VALVE_OFF")
        log("reject", ok=True, reason=why)

    rotator.zero()
    results = []
    t_start = clock()
    try:
        for n, s in enumerate(steps, 1):
            if stop_requested is not None and stop_requested():
                say(f"\nstop requested: stopping before part {n}/{len(steps)}")
                break
            p, pkg, tip, fd = s["p"], s["pkg"], s["tip"], s["feeder"]
            rec = {"ref": p["ref"], "package": p["package"], "tip": tip, "feeder": fd.id, "t": {}}
            results.append(rec)
            say(f"\n[{n}/{len(steps)}] {p['ref']} {p.get('value', '')} ({p['package']}) from {fd.id}, tip {tip}")
            if tip != current_tip:
                with timed(rec, "tip"):
                    mr.move_abs(z=mr.safe_travel_z, feedrate=zf["lift"])
                    user_ask(f"Fit nozzle tip {tip} (now: {current_tip or 'unknown'}), then press Enter... ")
                    if recentre is not None:
                        say(f"  re-centring tip {tip} over the up camera: {recentre(tip)}")
                current_tip = tip
            off = np.asarray(ms["down_cam_offset_mm"], float)
            pick_z = feeder_part_top_z(fd.d, tip, tips) + pick_press
            ins = None
            for attempt in range(1, retries + 1):
                with timed(rec, "feed_wait"):
                    fd.ready()
                with timed(rec, "pick"):
                    xy = fd.pick_xy()
                    mr.move_abs(x=float(xy[0]), y=float(xy[1]))
                    lower_and("VALVE_ON", pick_z, vac_ms)
                    fd.after_pick()
                with timed(rec, "inspect"):
                    ins = look_up(tip, pkg["body_mm"])
                if "offset_mm" not in ins:
                    say(f"  pick {attempt}: nozzle empty ({ins.get('reason')})")
                    with timed(rec, "pick"):
                        mr.move_abs(z=mr.safe_travel_z, feedrate=zf["lift"])
                        mr.gcode("VALVE_OFF")
                    log("pick", ok=False, ref=p["ref"], feeder=fd.id, attempt=attempt)
                    ins = None
                    continue
                if not ins["ok"]:
                    say(f"  pick {attempt}: {ins['reason']} -> reject")
                    reject(rec, ins["reason"])
                    ins = None
                    continue
                fd.learn(ins["offset_mm"])
                log("pick", ok=True, ref=p["ref"], feeder=fd.id, attempt=attempt, offset_mm=ins["offset_mm"])
                rec["attempts"] = attempt
                break
            if ins is None:
                rec["status"] = f"no good part after {retries} picks"
                mr.move_abs(z=mr.safe_travel_z, feedrate=zf["lift"])
                a = user_ask(f"  {p['ref']}: feeder {fd.id} gave no good part {retries} times. Fix it and "
                             f"press Enter to go on with the next part, or type q to stop: ")
                if str(a).strip().lower() == "q":
                    rec["status"] += " (stopped)"
                    break
                continue
            u = np.asarray(ins["offset_mm"], float)
            say(f"  on nozzle: offset {np.round(u, 3).tolist()} mm, angle {ins['angle_deg']:.1f}")
            # turn
            target = pose.part_angle(p["rot"]) + pkg["axis_deg"]        # long-axis machine angle
            rec["target_angle_deg"] = target
            lost = False
            with timed(rec, "turn"):
                if not pkg["symmetric"]:
                    coarse = wrap180(pose.part_angle(p["rot"]) - fd.d["tape_angle_deg"])
                    rotator.turn_part(coarse)
                    u = rotate_xy(u, coarse)
                    ins = look_up(tip, pkg["body_mm"])
                    if "offset_mm" not in ins:
                        rec["status"] = "part lost while turning"
                    else:
                        fine = shortest_turn(target, ins["angle_deg"], 180.0)
                        if abs(fine) > MAX_FINE_DEG:
                            rec["status"] = f"part sits {fine:.0f} deg off its tape angle -> rejected"
                            say("  " + rec["status"])
                        else:
                            u = np.asarray(ins["offset_mm"], float)
                if "status" not in rec:
                    rec["turns"] = 0
                    for _ in range(2):
                        d = shortest_turn(target, ins["angle_deg"], 180.0)
                        if abs(d) <= angle_tol_deg:
                            break
                        rotator.turn_part(d)
                        rec["turns"] += 1
                        ins = look_up(tip, pkg["body_mm"])
                        if "offset_mm" not in ins:
                            lost = True
                            break
                        u = np.asarray(ins["offset_mm"], float)
            if lost:
                rec["status"] = "part lost while turning"
            if "status" in rec:
                reject(rec, rec["status"])
                continue
            rec["placed_angle_deg"] = ins["angle_deg"]
            # place
            b = pose.to_machine([p["x"], p["y"]])
            nz = b + off - u
            place_z = tips[tip]["board_touch_z"] - p["height_mm"] + place_press
            with timed(rec, "place"):
                mr.move_abs(z=mr.safe_travel_z, feedrate=zf["lift"])
                mr.move_abs(x=float(nz[0]), y=float(nz[1]))
                lower_and("VALVE_OFF", place_z, release_ms, slow_lift=True)
            rec.update(status="placed", board_xy=b.tolist(), nozzle_xy=nz.tolist(), part_offset_mm=u.tolist(),
                       place_z=place_z)
            log("place", ok=True, ref=p["ref"], xy=b.tolist(), angle=rec["placed_angle_deg"])
            say(f"  placed at {np.round(b, 3).tolist()}, angle {rec['placed_angle_deg']:.1f} (target "
                f"{target % 180:.1f} mod 180)")
            if verify_empty:
                with timed(rec, "verify"):
                    # look for THIS part's size: with no size the 6 mm search found the round
                    # 7.4 mm tip collar (a circle fills 0.785 of its box) and called it a part (2026-11-14)
                    chk = look_up(tip, pkg["body_mm"])
                    mr.move_abs(z=mr.safe_travel_z, feedrate=zf["lift"])
                if chk.get("ok") or "offset_mm" in chk:
                    rec["status"] = "still on the nozzle after placing"
                    say(f"  {p['ref']}: part came back on the nozzle!")
                    reject(rec, rec["status"])
            rec["t"] = {k: round(v, 3) for k, v in rec["t"].items()}
            rec["cycle_s"] = round(sum(rec["t"].values()), 3)
            say(f"  cycle {rec['cycle_s']:.1f} s (" +
                ", ".join(f"{k} {v:.1f}" for k, v in rec["t"].items()) + ")")
    finally:
        for fd, f in saved_asks.values():
            fd.ask = f
    done = sum(r.get("status") == "placed" for r in results)
    mr.move_abs(z=mr.safe_travel_z, feedrate=zf["lift"])
    total = clock() - t_start
    st = timing_summary(results, total - waited[0], waited[0])
    if stats is not None:
        stats.update(st)
    say(f"\njob done: {done}/{len(steps)} placed in {total:.0f} s\n" + format_timing(st))
    return results


def dry_run(job, pose, look, packages=None, only=None, say=print):
    """No parts: centre the down camera over every placement (look(xy, name) takes a photo)."""
    steps, _ = plan_job(job, None, {}, packages, only, need_feeders=False)
    for n, s in enumerate(steps, 1):
        p = s["p"]
        xy = pose.to_machine([p["x"], p["y"]])
        say(f"[{n}/{len(steps)}] {p['ref']} ({p['package']}, rot {p['rot']}, tip {s['tip']}): "
            f"{np.round(xy, 3).tolist()}, machine angle {pose.part_angle(p['rot']):.1f}")
        look(xy, f"{n:03d}_{p['ref']}")
    return steps
