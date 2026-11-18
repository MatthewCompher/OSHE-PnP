"""Acceptance numbers from the event log (pnp_events.sqlite): pick success and vision decisions.

`pnpvision report` writes, into report_<stamp>/:
  events.csv          every logged event, one row each (time, run, event, ok, data fields)
  placement_review.csv  one row per down-camera board check (`check-board`): PLACED / MISSING at
                      a footprint, its photo, `human_agrees` to fill in (spec: part on the PCB).
  vision_review.csv   one row per up-camera inspection (spec: part on the toolhead): the machine's decision (PASS = good part,
                      REJECT = a part, but wrong, EMPTY = nothing on the nozzle), why, the photo, and
                      an empty `human_agrees` column: look at each photo, write Y or N. Vision
                      accuracy = Y / (Y + N); the spec asks for >= 95 % of 100.
  sheet_<run>.jpg     contact sheet per run: each inspection photo, numbered, labelled with the
                      decision (same numbers as vision_review.csv), for quick review.
  cycles.csv          one row per part placed by run-job: phase times and cycle time (from the
                      run's results/job_<stamp>.json), plus s/part and CPH per run in summary.txt.
  summary.txt         per run and totals: picks tried / good, per package, places, rejects,
                      cycle time / CPH, placement error (mm) from check-board.

Older inspections were logged without their photo; they are matched to the run's photo folder
(job_<stamp>/upNNNN.png or place_test_<stamp>/upN.png, the n-th inspection = the n-th photo).
"""
import csv
import datetime as dt
import glob
import json
import os
import re
import sqlite3
from collections import Counter, defaultdict

ODD_FILL = 0.55           # same rule as runner.looks_empty
EMPTY_TIP_FRAC = 0.75


def load_events(db_path, since=None):
    db = sqlite3.connect(db_path)
    q = "SELECT id, ts, run_id, event, ok, data FROM events"
    args = ()
    if since:
        q += " WHERE ts >= ?"
        args = (since,)
    rows = []
    for id_, ts, run, ev, ok, data in db.execute(q + " ORDER BY ts, id", args):
        try:
            d = json.loads(data) if data else {}
        except ValueError:
            d = {"raw": data}
        rows.append({"id": id_, "ts": ts, "run": run, "event": ev, "ok": ok, "data": d})
    return rows


def decision(d, ok):
    """PASS / REJECT / EMPTY for one inspect event's data."""
    if ok:
        return "PASS"
    reason = d.get("reason", "") or ""
    if "size_mm" not in d or d.get("size_mm") is None:
        fill = d.get("fill")
        return "REJECT" if fill is not None and fill >= ODD_FILL else "EMPTY"
    m = re.search(r"expected ([\d.]+)x([\d.]+)", reason)
    if m and max(d["size_mm"]) < EMPTY_TIP_FRAC * max(float(m.group(1)), float(m.group(2))):
        return "EMPTY"                                  # the bare tip (~0.85 x 0.8 mm)
    return "REJECT"


def package_of(ref="", size=None):
    m = re.search(r"(0201|0402|0603|0805|1206)", ref or "")
    if m:
        return m.group(1)
    if size:
        L = max(size)
        for name, nominal in (("0402", 1.0), ("0603", 1.6), ("0805", 2.0), ("1206", 3.2)):
            if abs(L - nominal) < 0.3:
                return name
    return "?"


def _stamp_time(name):
    m = re.search(r"(\d{8}_\d{6})", name)
    return dt.datetime.strptime(m.group(1), "%Y%m%d_%H%M%S").timestamp() if m else None


def match_folder(first_ts, folders):
    """The photo folder created at the start of a run: latest stamp <= first event + 5 s, within 10 min."""
    best = None
    for f in folders:
        t = _stamp_time(os.path.basename(f))
        if t is None or t > first_ts + 5 or first_ts - t > 600:
            continue
        if best is None or t > best[0]:
            best = (t, f)
    return best[1] if best else None


def photo_for(folder, n):
    for name in (f"up{n:04d}.png", f"up{n}.png"):
        p = os.path.join(folder, name)
        if os.path.exists(p):
            return p
    return ""


def build(rows, base_dir="."):
    folders = [f for f in glob.glob(os.path.join(base_dir, "job_*")) + glob.glob(os.path.join(base_dir, "place_test_*"))
               if os.path.isdir(f)]
    runs = defaultdict(list)
    for r in rows:
        runs[r["run"]].append(r)
    vision, summary, placement, cycles = [], [], [], []
    for run, evs in sorted(runs.items(), key=lambda kv: kv[1][0]["ts"]):
        folder = match_folder(evs[0]["ts"], folders)
        n_inspect = 0
        last_ref = ""
        picks = Counter()
        for e in evs:
            d = e["data"]
            if e["event"] == "pick":
                last_ref = d.get("ref", last_ref)
                picks[(package_of(last_ref), bool(e["ok"]))] += 1
            if e["event"] == "board_check":
                placement.append({
                    "run": run, "n": sum(1 for x in placement if x["run"] == run) + 1,
                    "time": dt.datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d %H:%M:%S"),
                    "ref": d.get("ref", ""), "decision": "PLACED" if e["ok"] else "MISSING",
                    "green": d.get("green", ""), "dx_mm": d.get("dx_mm", ""), "dy_mm": d.get("dy_mm", ""),
                    "err_mm": d.get("err_mm", ""), "angle_err_deg": d.get("angle_err_deg", ""),
                    "photo": d.get("part_id", ""), "human_agrees": ""})
                continue
            if e["event"] != "inspect":
                continue
            n_inspect += 1
            photo = d.get("part_id") or (photo_for(folder, n_inspect) if folder else "")
            vision.append({
                "run": run, "n": n_inspect,
                "time": dt.datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d %H:%M:%S"),
                "decision": decision(d, e["ok"]), "reason": d.get("reason", ""),
                "size_mm": "x".join(f"{v:.2f}" for v in d["size_mm"]) if d.get("size_mm") else "",
                "fill": f"{d['fill']:.2f}" if d.get("fill") is not None else "",
                "angle_deg": f"{d['angle_deg']:.1f}" if d.get("angle_deg") is not None else "",
                "package": package_of(last_ref, d.get("size_mm")),
                "photo": photo, "human_agrees": ""})
        kinds = Counter(e["event"] for e in evs)
        timing = None
        if folder:
            rj = os.path.join(base_dir, "results", os.path.basename(folder) + ".json")
            if os.path.exists(rj):
                try:
                    with open(rj, encoding="utf-8") as f:
                        jr = json.load(f)
                    timing = jr.get("timing")
                    for r in jr.get("results", []):
                        cycles.append({"run": run, "ref": r.get("ref", ""), "status": r.get("status", ""),
                                       "attempts": r.get("attempts", ""), "cycle_s": r.get("cycle_s", ""),
                                       **{f"t_{k}": v for k, v in (r.get("t") or {}).items()}})
                except (OSError, ValueError):
                    pass
        if kinds["board_check"] and not kinds["inspect"]:
            summary.append({"run": run, "start": dt.datetime.fromtimestamp(evs[0]["ts"]).strftime("%Y-%m-%d %H:%M"),
                            "type": "check-board", "picks": Counter(), "places": 0, "rejects": 0,
                            "decisions": Counter(x["decision"] for x in placement if x["run"] == run),
                            "folder": os.path.dirname(placement[-1]["photo"]) if placement else ""})
            continue
        dec = Counter(v["decision"] for v in vision if v["run"] == run)
        summary.append({
            "run": run, "start": dt.datetime.fromtimestamp(evs[0]["ts"]).strftime("%Y-%m-%d %H:%M"),
            "type": "run-job" if kinds["pick"] else ("place-test/inspect" if kinds["inspect"] else "other"),
            "picks": picks, "places": sum(1 for e in evs if e["event"] == "place" and e["ok"]),
            "rejects": kinds["reject"], "decisions": dec, "folder": folder or "", "timing": timing})
    return vision, summary, placement, cycles


def summary_text(summary, vision, placement=()):
    out = ["Per run (pick success = picks that came up with a good part / all picks):"]
    tot = Counter()
    for s in summary:
        good = sum(n for (pkg, ok), n in s["picks"].items() if ok)
        allp = sum(s["picks"].values())
        tot.update(s["picks"])
        rate = f"{100.0 * good / allp:.0f} %" if allp else "-"
        pk = ", ".join(f"{pkg}: {s['picks'][(pkg, True)]}/{s['picks'][(pkg, True)] + s['picks'][(pkg, False)]}"
                       for pkg in sorted({p for p, _ in s["picks"]}))
        d = s["decisions"]
        if s["type"] == "check-board":
            errs = [float(x["err_mm"]) for x in placement if x["run"] == s["run"] and x["err_mm"] not in ("", None)]
            e = (f"  placement error {len(errs)} parts: mean {sum(errs) / len(errs):.3f} mm, worst {max(errs):.3f} mm"
                 if errs else "")
            out.append(f"  {s['start']}  run {s['run']}  check-board        PLACED {d['PLACED']}  MISSING {d['MISSING']}"
                       f"{e}  photos {s['folder'] or 'not found'}")
            continue
        t = s.get("timing") or {}
        cyc = (f"  {t['s_per_part']:.1f} s/part = {t['cph']:.0f} CPH" if t.get("s_per_part") and t.get("cph") else "")
        out.append(f"  {s['start']}  run {s['run']}  {s['type']:18s} picks {good}/{allp} ({rate}){' [' + pk + ']' if pk else ''}"
                   f"  placed {s['places']}{cyc}  rejects {s['rejects']}  vision PASS {d['PASS']} REJECT {d['REJECT']} "
                   f"EMPTY {d['EMPTY']}  photos {s['folder'] or 'not found'}")
    out.append("")
    out.append("Totals, run-job picks per package (good / tried):")
    for pkg in sorted({p for p, _ in tot}):
        g, b = tot[(pkg, True)], tot[(pkg, False)]
        out.append(f"  {pkg}: {g}/{g + b} = {100.0 * g / max(g + b, 1):.1f} %")
    dec = Counter(v["decision"] for v in vision)
    with_photo = sum(1 for v in vision if v["photo"])
    out.append("")
    out.append(f"Vision: {len(vision)} inspections (PASS {dec['PASS']}, REJECT {dec['REJECT']}, EMPTY {dec['EMPTY']}), "
               f"{with_photo} with a photo. Fill human_agrees (Y/N) in vision_review.csv; accuracy = Y / (Y + N).")
    pdec = Counter(x["decision"] for x in placement)
    out.append(f"Placement (down camera): {len(placement)} footprint checks (PLACED {pdec['PLACED']}, "
               f"MISSING {pdec['MISSING']}). Fill human_agrees in placement_review.csv.")
    out.append("Note: place-test runs (e.g. the 0805 sweep) log inspections but not picks: there, each PASS is a "
               "good pick and EMPTY / REJECT a failed one.")
    return "\n".join(out)


def contact_sheet(vision_rows, path, cell=220, cols=8, crop_frac=0.25):
    """Grid of inspection photos (centre crop), each labelled with its number and decision."""
    import cv2
    import numpy as np
    rows = [v for v in vision_rows if v["photo"] and os.path.exists(v["photo"])]
    if not rows:
        return False
    tiles = []
    colour = {"PASS": (0, 170, 0), "REJECT": (0, 0, 220), "EMPTY": (200, 120, 0),
              "PLACED": (0, 170, 0), "MISSING": (0, 0, 220)}
    for v in rows:
        img = cv2.imread(v["photo"])
        if img is None:
            continue
        h, w = img.shape[:2]
        s = max(int(min(h, w) * crop_frac), 8)
        cy, cx = h // 2, w // 2
        crop = img[max(cy - s, 0):cy + s, max(cx - s, 0):cx + s]
        t = cv2.resize(crop, (cell, cell))
        cv2.rectangle(t, (0, 0), (cell - 1, 24), (0, 0, 0), -1)
        cv2.putText(t, f"{v['n']} {v.get('ref', '')} {v['decision']}".replace("  ", " "), (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    colour.get(v["decision"], (255, 255, 255)), 2)
        tiles.append(t)
    while len(tiles) % cols:
        tiles.append(np.zeros((cell, cell, 3), np.uint8))
    grid = np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)])
    cv2.imwrite(path, grid, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return True


def write_report(db_path, out_dir, since=None, base_dir=".", sheets=True):
    rows = load_events(db_path, since)
    vision, summary, placement, cycles = build(rows, base_dir)
    os.makedirs(out_dir, exist_ok=True)
    keys = sorted({k for r in rows for k in r["data"]})
    with open(os.path.join(out_dir, "events.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time", "run", "event", "ok"] + keys)
        for r in rows:
            w.writerow([dt.datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], r["run"],
                        r["event"], "" if r["ok"] is None else r["ok"]]
                       + [json.dumps(r["data"][k]) if isinstance(r["data"].get(k), (list, dict))
                          else r["data"].get(k, "") for k in keys])
    fields = ["run", "n", "time", "package", "decision", "reason", "size_mm", "fill", "angle_deg", "photo", "human_agrees"]
    with open(os.path.join(out_dir, "vision_review.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(vision)
    if cycles:
        cf = ["run", "ref", "status", "attempts", "cycle_s"] + sorted({k for c in cycles for k in c if k.startswith("t_")})
        with open(os.path.join(out_dir, "cycles.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cf, extrasaction="ignore")
            w.writeheader()
            w.writerows(cycles)
    pf = ["run", "n", "time", "ref", "decision", "green", "dx_mm", "dy_mm", "err_mm", "angle_err_deg",
          "photo", "human_agrees"]
    with open(os.path.join(out_dir, "placement_review.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=pf)
        w.writeheader()
        w.writerows(placement)
    text = summary_text(summary, vision, placement)
    with open(os.path.join(out_dir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    if sheets:
        for s in summary:
            if s["type"] == "check-board":
                contact_sheet([v for v in placement if v["run"] == s["run"]],
                              os.path.join(out_dir, f"sheet_board_{s['run']}.jpg"), crop_frac=0.17)
            else:
                contact_sheet([v for v in vision if v["run"] == s["run"]], os.path.join(out_dir, f"sheet_{s['run']}.jpg"))
    return text
