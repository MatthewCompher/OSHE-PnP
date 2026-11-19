"""Place-and-measure test: pick the part under the down camera, inspect it on the up camera,
place it on a target, then measure where it landed with the down camera.

You aim the picks: centre the down camera on a part (Mainsail reticle, by eye is fine), run the
command; after each part it asks you to jog onto the next one. Where it landed is measured
automatically by photographing the empty target before placing and again after: only what
changed counts, so part colour, copper pads, silkscreen and tape don't matter.

All positions are TOOLHEAD coordinates "with the down camera centred on the point" (what you
read in Mainsail when the reticle is on something). The nozzle goes over such a point at
point + down_cam_offset_mm.

Why the numbers mean something (u = up-camera offset of the part on the nozzle, e = landing
error = where it landed minus the target):
  * without --correct, pick and place both use the same down_cam_offset, so an offset error
    cancels: e is only how far off the part was picked (aim + slip), and (e - u) is the error
    a corrected job placement would have;
  * with --correct, e is that job placement error directly.
Either way, the mean of that "job error" is what down_cam_offset_mm should be reduced by.
Hardware is injected (callables), so the whole cycle runs against a simulator in the tests.
"""
import cv2
import numpy as np

from .moonraker import lift
from .detect import find_by_template, find_placed_part, outline_angle, symmetry_center
from .rotation import rotate_xy, shortest_turn


def _mean_frame(grab, n=2):
    return np.mean([grab().astype(np.float32) for _ in range(n)], axis=0).astype(np.uint8)


class PartFinder:
    """First part: wherever the down camera is centred when the test starts (you aim it).
    Next parts: found automatically from a picture of that first part (template) by searching
    the camera view from the first pick position for a shortlist, then checking candidates
    nearest first with the camera right over each one (same lighting as the template, and the
    part's height doesn't skew the scale there). A candidate that fails is not looked at again."""
    SHORTLIST = 0.55        # wide-view score to be worth a close look
    MAX_CHECKS = 8          # close looks per search (each is a short move + photo)
    SURE = 0.80             # nearest close-up this good is taken (keeps the row order;
                            # real parts 0.83-0.95 close up, pads <= 0.73 on 2026-11-11)

    def __init__(self, mr, grab, motion, principal, size_mm, k_height, origin, avoid=(),
                 threshold=0.70, say=print, save=None):
        self.save = save or (lambda name, img: None)
        self.searches = 0
        self.mr, self.grab, self.motion = mr, grab, motion
        self.principal = np.asarray(principal, float)
        self.k = k_height
        self.origin = np.asarray(origin, float)
        self.avoid = [np.asarray(p, float) for p in avoid]     # e.g. the targets (parts on tape)
        self.used = []                                          # picked or failed: skip
        self.rejected = []                                      # looked at close up: not a part
        self.threshold, self.say = threshold, say
        mpp = motion.mm_per_px
        half = int(round(0.5 * float(np.hypot(*size_mm)) * k_height / mpp * 1.1))
        img = self._look(self.origin)
        self.half_sym = half
        self.max_shift = int(1.0 / mpp)
        # You aimed by eye: find the first part's real centre as its centre of 180-degree
        # symmetry (2026-11-11: thresholding outlined only half of the part, so the first pick
        # and every template match afterwards were ~0.4 mm off).
        c, v = self._sym(img, self.principal)
        if c is not None and v >= 0.3 and np.linalg.norm(c - self.principal) * mpp < 1.0:
            self.origin = self._to_machine(self.origin, c)
            say(f"  first part centre measured at {np.round(self.origin, 3).tolist()} "
                f"({np.linalg.norm(np.asarray(origin) - self.origin):.2f} mm from where you aimed)")
        else:
            c = self.principal.copy()
            say(f"  could not measure the first part's centre (symmetry score {v:.2f}); "
                "using where you aimed - picks will correct themselves from the up camera")
        cx, cy = int(round(c[0])), int(round(c[1]))
        self.template = img[cy - half:cy + half + 1, cx - half:cx + half + 1].copy()
        # Match on the part only: a part-sized rectangle (slightly shrunk) at the angle where it
        # fits the part's edges, so the board around the first part doesn't have to match.
        lp, sp = (v * k_height / mpp for v in sorted(size_mm, reverse=True))
        ang = outline_angle(img, c, lp, sp)
        self.mask = np.zeros(self.template.shape[:2], np.uint8)
        box = cv2.boxPoints(((half + (c[0] - cx), half + (c[1] - cy)), (lp * 0.95, sp * 0.95), ang))
        cv2.fillPoly(self.mask, [np.round(box).astype(np.int32)], 255)
        self.last = self.origin
        self.first = True

    def locate_near_centre(self, img, radius_mm=2.5, min_score=0.6):
        """Backup for the landing check: the part (looks like the first one) near the image
        centre, then its symmetry centre. Pixel position or None. ~0.1 mm less precise than the
        before/after check (where both worked on real photos they agreed within 0.03-0.08 mm)."""
        r_px = radius_mm / self.motion.mm_per_px
        h = find_by_template(img, self.template, center_px=self.principal, radius_px=r_px,
                             threshold=min_score, mask=self.mask, scale=0.5)
        if not h:
            return None
        px = np.asarray(h[0][0], float)
        s = int(0.2 / self.motion.mm_per_px)
        c, v = symmetry_center(img, px, self.half_sym, int(0.5 / self.motion.mm_per_px),
                               starts=((0, 0), (s, 0), (-s, 0), (0, s), (0, -s)))
        if c is not None and v >= 0.3 and np.linalg.norm(c - px) * self.motion.mm_per_px < 0.4:
            return c
        return px

    def _sym(self, img, start):
        mpp = self.motion.mm_per_px
        s = int(0.3 / mpp)
        return symmetry_center(img, start, self.half_sym, self.max_shift,
                               starts=((0, 0), (s, 0), (-s, 0), (0, s), (0, -s)))

    def _look(self, xy):
        self.mr.move_abs(x=float(xy[0]), y=float(xy[1]))
        return _mean_frame(self.grab)

    def _to_machine(self, view_xy, px):
        return np.asarray(view_xy, float) + self.motion.offset_mm(np.asarray(px, float) - self.principal) / self.k

    def __call__(self, last):
        if last is not None:
            self.used.append(np.asarray(last, float))
            self.last = np.asarray(last, float)
        if self.first:
            self.first = False
            return self.origin
        # search outward from the part picked last: follows a row in whatever direction it runs
        view = self.last
        img = self._look(view)
        # Wide view = shortlist only. Away from the middle the down light's glare changes how a
        # part looks (2026-11-11: real parts 0.64-0.78 there, tape/silkscreen up to 0.73), so
        # every candidate is judged again with the camera right over it, lit like the template.
        hits = find_by_template(img, self.template, threshold=self.SHORTLIST, scale=0.25, mask=self.mask)
        self.searches += 1
        self.save(f"search{self.searches}_raw", img)
        vis = img.copy()
        for px, score in hits:
            cv2.circle(vis, (int(px[0]), int(px[1])), 40, (0, 200, 255), 3)
            cv2.putText(vis, f"{score:.2f}", (int(px[0]) + 45, int(px[1])), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 200, 255), 3)
        self.save(f"search{self.searches}", vis)
        cands = []
        for px, score in hits:
            p = self._to_machine(view, px)
            if any(np.linalg.norm(p - q) < 1.0 for q in self.used + self.rejected) or \
               any(np.linalg.norm(p - q) < 2.5 for q in self.avoid):
                continue
            cands.append((np.linalg.norm(p - view), p, score))
        cands.sort(key=lambda c: c[0])                     # nearest first
        r_px = 1.5 / self.motion.mm_per_px
        tried, best = [], None
        for _, p, score in cands[:self.MAX_CHECKS]:
            img = self._look(p)
            fine = find_by_template(img, self.template, center_px=self.principal, radius_px=r_px,
                                    threshold=0.0, mask=self.mask, scale=0.5)
            s = fine[0][1] if fine else 0.0
            tried.append(f"{s:.2f}")
            if not fine or s < self.threshold:
                self.rejected.append(p)
                continue
            # keep the BEST close-up, not the first that passes: on 2026-11-11 pads passed
            # at 0.67-0.72 while real parts scored 0.80-0.90
            if best is None or s > best[0]:
                best = (s, p, img, fine[0][0], score)
            if s >= self.SURE:
                break
        if best is None:
            self.say(f"  no more parts found ({len(cands)} candidate(s); close-up scores "
                     f"{', '.join(tried) or 'none'}; need {self.threshold}).")
            return None
        s, p, img, px, score = best
        q = self._to_machine(p, px)
        # final centre from symmetry (independent of the template, so a template that is a bit
        # off-centre can't push every pick off: 2026-11-11 picks grabbed part edges and dropped)
        c, v = self._sym(img, px)
        if c is not None and v >= 0.3 and np.linalg.norm(c - np.asarray(px)) * self.motion.mm_per_px < 0.8:
            q = self._to_machine(p, c)
        self.say(f"  next part at {np.round(q, 3).tolist()} (wide view {score:.2f}, close up {s:.2f}; "
                 f"checked {len(tried)})")
        return q


def place_test(mr, down_grab, down_motion, down_principal, up_inspect, ms, next_pick, targets,
               size_mm=(2.0, 1.25), thickness_mm=0.85, working_distance_mm=11.5,
               pick_z=37.8, place_z=37.7, inspect_z=34.5, approach_mm=0.8, vac_ms=300,
               release_ms=500, correct=False, say=print, save=None, rotator=None, rotate_to=None,
               angle_tol_deg=1.0):
    backup = getattr(next_pick, "locate_near_centre", None)      # PartFinder provides it
    """Fill `targets` one by one. next_pick(last_pick_xy or None) -> XY of the next part (down
    camera centred on it) or None to stop. Returns a list of per-attempt dicts."""
    off = np.array(ms["down_cam_offset_mm"], float)
    up_xy = np.array(ms["up_cam_xy_mm"], float)
    mpp = down_motion.mm_per_px
    exp_px = tuple(v / mpp for v in sorted(size_mm, reverse=True))
    # A part's top is closer to the camera than the board the motion map was made at, so an
    # off-centre offset reads too far out by this factor.
    k_height = working_distance_mm / (working_distance_mm - thickness_mm)
    save = save or (lambda name, img: None)

    def look(xy):
        mr.move_abs(x=float(xy[0]), y=float(xy[1]))
        return _mean_frame(down_grab)

    def lower_and(valve, z, ms_wait, slow_lift=False):
        mr.move_abs(z=z - approach_mm, feedrate=300)
        mr.move_abs(z=z, feedrate=60)
        mr.gcode(f"{valve}\nG4 P{int(ms_wait)}")
        if slow_lift:
            mr.move_abs(z=z - 0.5, feedrate=60)
        lift(mr, feedrate=600)

    results = []
    t_idx = 0
    part = None
    # Where on the part the nozzle grabbed, from the up camera (good picks only): later picks
    # are shifted by the average, so they converge on centred grabs (an off-centre grab tilts
    # the part and it drops). The accuracy numbers don't depend on it: (e - u) cancels it.
    grabs = []
    fails_in_row = 0
    while t_idx < len(targets):
        if fails_in_row >= 3:
            say("\nStopping: 3 failed picks in a row (out of parts, or picking something that isn't one).")
            break
        if len(results) >= 2 * len(targets) + 2:
            say("\nStopping: too many attempts for the number of targets.")
            break
        part = next_pick(part)
        if part is None:
            break
        part = np.asarray(part, float)
        target = np.asarray(targets[t_idx], float)
        rec = {"attempt": len(results) + 1, "picked_from": part.tolist(), "target": target.tolist()}
        results.append(rec)
        say(f"\n--- part {len(results)}: from {np.round(part, 3).tolist()} -> target {t_idx + 1}/"
            f"{len(targets)} {np.round(target, 3).tolist()} ---")
        # pick (shifted by the average grab offset so far)
        grab_fix = np.mean(grabs[-3:], axis=0) if grabs else np.zeros(2)
        rec["grab_fix_mm"] = grab_fix.tolist()
        n = part + off + grab_fix
        mr.move_abs(x=float(n[0]), y=float(n[1]))
        lower_and("VALVE_ON", pick_z, vac_ms)
        # inspect
        mr.move_abs(x=float(up_xy[0]), y=float(up_xy[1]))
        mr.move_abs(z=inspect_z, feedrate=300)
        ins = up_inspect(size_mm)
        rec["inspect"] = ins
        lift(mr, feedrate=600)
        if "offset_mm" not in ins:
            rec["status"] = "pick failed (nozzle empty)"
            say(f"  nozzle empty after the pick ({ins.get('reason')}).")
            mr.gcode("VALVE_OFF")
            fails_in_row += 1
            continue
        u = np.array(ins["offset_mm"], float)
        say(f"  on nozzle: offset {np.round(u, 3).tolist()} mm, angle {ins['angle_deg']:.1f} deg, "
            f"size {np.round(ins['size_mm'], 2).tolist()} mm")
        if not ins["ok"]:
            # held, but not the part we expect (on its side, two parts, ...): put it back
            rec["status"] = f"bad part ({ins['reason']}), put back"
            say(f"  {ins['reason']} -> putting it back where it came from")
            n = part + off + grab_fix
            mr.move_abs(x=float(n[0]), y=float(n[1]))
            lower_and("VALVE_OFF", pick_z - 0.1, release_ms)
            fails_in_row += 1
            continue
        fails_in_row = 0
        grabs.append(grab_fix + u)       # grab error of an uncorrected pick at this part
        want = None
        if rotate_to is not None:     # one angle, or a list used in turn (target i -> list[i % n])
            want = float(rotate_to[t_idx % len(rotate_to)]) if np.ndim(rotate_to) else float(rotate_to)
            rec["target_angle_deg"] = want
        if want is not None:
            # turn to the target angle (shortest way, mod 180), then look again: the offset
            # turns with the part. Up to 2 turns if the first one lands more than angle_tol off.
            mr.move_abs(z=inspect_z, feedrate=300)
            turns, lost = [], False
            for _ in range(2):
                d = rotator.turn_to(want, ins["angle_deg"])
                predicted = rotate_xy(u, d)
                ins = up_inspect(size_mm)
                if "offset_mm" not in ins:
                    lost = True
                    break
                u_new = np.array(ins["offset_mm"], float)
                turns.append({"turn_deg": d, "motor_deg": rotator.motor,
                              "predicted_offset_mm": predicted.tolist(), "inspect": ins})
                say(f"  turned {d:+.1f} deg (motor {rotator.motor:.1f}): now angle {ins['angle_deg']:.1f}, "
                    f"offset {np.round(u_new, 3).tolist()} (predicted {np.round(predicted, 3).tolist()})")
                u = u_new
                if abs(shortest_turn(want, ins["angle_deg"], rotator.symmetry)) <= angle_tol_deg:
                    break
            lift(mr, feedrate=600)
            rec["turns"] = turns
            if lost:
                rec["status"] = "part lost while turning"
                say("  part not seen after turning (dropped?) - skipping it")
                mr.gcode("VALVE_OFF")
                fails_in_row += 1
                continue
        rec["place_offset_mm"] = u.tolist()
        rec["place_angle_deg"] = ins["angle_deg"]
        # photo of the empty target, place, photo again
        ref_t = look(target)
        n = target + off - (u if correct else 0.0)       # u: part relative to the nozzle
        mr.move_abs(x=float(n[0]), y=float(n[1]))
        lower_and("VALVE_OFF", place_z, release_ms, slow_lift=True)
        t_idx += 1
        after = look(target)
        save(f"target{t_idx}_empty", ref_t)
        save(f"target{t_idx}_after", after)
        found = find_placed_part(ref_t, after, down_principal, 2.5 / mpp,
                                 tuple(v * k_height for v in exp_px))
        status = "ok"
        px = None if found is None else np.asarray(found.center_px)
        if px is None and backup is not None:
            px = backup(after)
            status = "ok (backup)"
        if px is None:
            rec["status"] = "placed part not found at the target (still on the nozzle?)"
            say("  NOT found at the target after placing - check the nozzle and the tape.")
            continue
        landed = target + down_motion.offset_mm(px - down_principal) / k_height
        e = landed - target
        job = e if correct else e - u
        rec.update(status=status, landed=landed.tolist(), error_mm=e.tolist(), job_error_mm=job.tolist())
        if found is not None:
            rec["landed_angle_deg"] = float(down_motion.direction_mm(found.angle_px_deg))
            if want is not None:
                rec["angle_error_deg"] = -shortest_turn(want, rec["landed_angle_deg"], 180.0)
                say(f"  landed at {rec['landed_angle_deg']:.1f} deg: angle error {rec['angle_error_deg']:+.2f} deg")
        if status != "ok":
            say("  (before/after check unsure; measured by finding the part itself, ~0.1 mm less "
                "precise, left out of the offset average)")
        say(f"  landed {np.round(landed, 3).tolist()}: error {np.round(e, 3).tolist()} mm "
            f"(|e| {np.linalg.norm(e):.3f}); job error {np.round(job, 3).tolist()} mm")
    return results


def summarize(results, off, correct):
    ok = [r for r in results if r.get("status") == "ok"]
    backup = [r for r in results if r.get("status") == "ok (backup)"]
    out = {"attempts": len(results), "ok": len(ok), "ok_backup": len(backup), "correct": correct,
           "failed": [r["status"] for r in results if not str(r.get("status", "")).startswith("ok")]}
    if backup:
        out["backup_job_errors_mm"] = [np.round(r["job_error_mm"], 3).tolist() for r in backup]
    if ok:
        job = np.array([r["job_error_mm"] for r in ok])
        e = np.array([r["error_mm"] for r in ok])
        out.update(mean_job_error_mm=job.mean(0).round(4).tolist(),
                   std_job_error_mm=(job.std(0, ddof=1).round(4).tolist() if len(ok) > 1 else None),
                   mean_landing_error_mm=e.mean(0).round(4).tolist(),
                   max_landing_error_mm=float(np.linalg.norm(e, axis=1).max().round(4)),
                   suggested_down_cam_offset_mm=(np.asarray(off) - job.mean(0)).round(4).tolist())
    ang = [r["angle_error_deg"] for r in results if "angle_error_deg" in r]
    if ang:
        out.update(angle_targets_deg=[r["target_angle_deg"] for r in results if "angle_error_deg" in r],
                   angle_errors_deg=np.round(ang, 2).tolist(),
                   mean_angle_error_deg=round(float(np.mean(ang)), 2),
                   max_abs_angle_error_deg=round(float(np.max(np.abs(ang))), 2))
    return out
