"""PnP job page for KlipperScreen (the machine's touchscreen).

Install (Pi): link this file into KlipperScreen's panels folder and restart KlipperScreen:
    ln -sf ~/OSHE-PnP/Software/Klipper/klipperscreen/pnp_job.py ~/KlipperScreen/panels/pnp_job.py
It is opened from the "Pick & Place" menu (KlipperScreen_pnp.conf: panel: pnp_job).

Three views (2026-11-18 rework):
  list    one scrolling row per job file (any number of jobs), a one-line machine status, and
          "Running: <job>" at the top while a job runs (back to the status view), and
          "Load jobs from SD card / USB stick" (PNP_IMPORT_JOBS; the list refreshes itself).
  detail  tap a job: board, parts to place, packages, which feeders hold them, the last run's
          result and CPH, estimated time; options No feeders / Align first / Dry run; Start
          (with a confirm) and Back to jobs.
  status  shown while a job runs: machine homing, job, part n/total, placed/failed, elapsed,
          the latest status line; Continue (answers the open question) and Stop job (two taps on
          the page itself, no pop-up that a machine move could close). After the job: its result
          stays shown, with Back to jobs. Job questions still open as dialogs over any page.

Job state comes from Klipper (gcode_macro _PNP_STATE, published by run-job --hmi, see
Software/Klipper/pnp_hmi.cfg). Layout rules (2026-11-14 screen test): status lines never wrap
(they pushed the buttons off screen), button sets are built once and only switched, buttons are
KlipperScreen's normal size. Light: one small Moonraker query per second, only while shown.
"""
import glob
import json
import logging
import os
import time
from collections import Counter

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel

PNP_DIR = os.path.expanduser("~/OSHE-PnP/Software/pnpvision")
JOBS_DIR = os.path.join(PNP_DIR, "jobs")
FEEDERS_JSON = os.path.join(PNP_DIR, "calibration", "feeders.json")
RESULTS_DIR = os.path.join(PNP_DIR, "results")
STATE = "gcode_macro _PNP_STATE"
STOP_ARM_S = 5
DEFAULT_S_PER_PART = 7.0          # for the time estimate before a job has been run
LIVE_MARKUP = ("<span size='large' weight='bold' foreground='#ff4040'>"
               "JOB RUNNING: the machine moves on its own. Hands clear.</span>")


def _elapsed(sec):
    sec = int(max(0, sec))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h} h {m:02d} min" if h else (f"{m} min {s:02d} s" if m else f"{s} s")


def _short_pkg(name):
    """'R_0603_1608Metric' -> 'R 0603' (short enough for the screen)."""
    parts = name.split("_")
    return f"{parts[0]} {parts[1]}" if len(parts) >= 2 and parts[1].isdigit() else name


def job_summary(stem, jobs_dir=None, feeders_json=None, results_dir=None, with_last=True):
    """Everything the detail view shows about one job file, as plain values (no GTK).
    with_last=False skips the search of past results (the list view: dozens of jobs)."""
    jobs_dir = jobs_dir or JOBS_DIR
    path = os.path.join(jobs_dir, stem + ".job.json")
    out = {"stem": stem, "ok": False}
    try:
        with open(path, encoding="utf-8") as f:
            job = json.load(f)
    except (OSError, ValueError) as e:
        out["error"] = f"can't read the job file: {e}"
        return out
    board = job.get("board", {}) or {}
    pl = job.get("placements", []) or []
    todo = [p for p in pl if not p.get("skip")]
    pk = Counter(p.get("package", "?") for p in todo)
    out.update(ok=True, board=board.get("name", "?"), side=board.get("side", "?"),
               total=len(pl), to_place=len(todo), skipped=len(pl) - len(todo),
               packages=sorted(pk.items(), key=lambda kv: -kv[1]))
    # feeders: which packages are loaded
    held = {}
    try:
        with open(feeders_json or FEEDERS_JSON, encoding="utf-8") as f:
            for fd in json.load(f).get("feeders", []):
                held.setdefault(fd.get("package", ""), fd.get("id", "?"))
    except (OSError, ValueError):
        pass
    out["covered"] = [(p, n, held[p]) for p, n in out["packages"] if p in held]
    out["missing"] = [(p, n) for p, n in out["packages"] if p not in held]
    # the last run of this job file
    last = None
    for f in [] if not with_last else sorted(glob.glob(os.path.join(results_dir or RESULTS_DIR, "job_*.json")), reverse=True):
        try:
            with open(f, encoding="utf-8") as fh:
                r = json.load(fh)
        except (OSError, ValueError):
            continue
        if os.path.basename(str(r.get("job", ""))) == os.path.basename(path):
            t = r.get("timing") or {}
            stamp = os.path.basename(f)[4:-5]                    # YYYYmmdd_HHMMSS
            when = f"{stamp[4:6]}-{stamp[6:8]} {stamp[9:11]}:{stamp[11:13]}" if len(stamp) >= 13 else stamp
            last = {"when": when, "placed": t.get("placed", 0), "attempted": t.get("attempted", 0),
                    "cph": t.get("cph"), "s_per_part": t.get("s_per_part")}
            break
    out["last"] = last
    spp = (last or {}).get("s_per_part") or DEFAULT_S_PER_PART
    out["estimate_s"] = sum(n for _, n, _ in out["covered"]) * spp     # only parts a feeder holds
    return out


def _set_button_text(button, text):
    """KlipperScreen buttons hold their text in a Gtk.Label somewhere inside."""
    stack = [button]
    while stack:
        w = stack.pop()
        if isinstance(w, Gtk.Label):
            w.set_text(text)
            return
        if isinstance(w, Gtk.Container):
            stack.extend(w.get_children())
    button.set_label(text)


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or "PnP Job")
        self.timer = None
        self.running = None
        self.stop_armed = False
        self.job_names = None
        self.selected = None
        self.view = None
        # "No feeders" off (F1 works), "Align first" on: the board is found again before the job
        # (the camera drives to pad A by itself; not counted in CPH). Untick to skip.
        self.opts = {"no_feeders": False, "align": True, "dry_run": False}

        self.stack = Gtk.Stack(hexpand=True, vexpand=True)
        self.stack.add_named(self._build_list(), "list")
        self.stack.add_named(self._build_detail(), "detail")
        self.stack.add_named(self._build_status(), "status")
        self.content.add(self.stack)
        self._fill_jobs()
        self._set_running(False)
        self._view("list")

    def _view(self, name):
        self.view = name
        self.stack.set_visible_child_name(name)

    # -- list view -------------------------------------------------------------------------------
    def _build_list(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True, vexpand=True)
        self.list_status = Gtk.Label(label="-", xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        self.list_status.get_style_context().add_class("description")
        box.pack_start(self.list_status, False, False, 0)
        self.running_button = self._gtk.Button("print", "Running", "color3")
        self.running_button.connect("clicked", self._show_status)
        self.running_button.set_no_show_all(True)              # only while a job runs (_show)
        box.pack_start(self.running_button, False, False, 0)
        # SD card (USB reader) / USB stick -> jobs/ (PNP_IMPORT_JOBS, pnpvision import-jobs); the
        # list refreshes itself (_poll) once the files are there.
        self.import_button = self._gtk.Button("sd", "Load jobs from SD card / USB stick", "color2")
        self.import_button.connect("clicked", self._import)
        self.import_button.set_vexpand(False)
        self.import_button.set_size_request(-1, self._row_height())
        box.pack_start(self.import_button, False, False, 0)
        try:
            scroll = self._gtk.ScrolledWindow()               # KlipperScreen's touch-friendly one
        except Exception:
            scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.job_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True,
                               vexpand=False, valign=Gtk.Align.START)
        scroll.add(self.job_box)
        box.pack_start(scroll, True, True, 0)
        self.job_buttons = []
        return box

    def _row_height(self):
        """One list row: about 3 lines of KlipperScreen's font (fits ~5 rows on the 7 inch screen)."""
        try:
            return int(self._gtk.font_size * 3.2)
        except (AttributeError, TypeError, ValueError):
            return 64

    @staticmethod
    def _jobs():
        try:
            return sorted(f[:-len(".job.json")] for f in os.listdir(JOBS_DIR) if f.endswith(".job.json"))
        except OSError as e:
            logging.error(f"pnp_job: {e}")
            return []

    def _import(self, widget):
        """Nothing moves and nothing on the Pi is overwritten: no confirm needed."""
        self.list_status.set_text("USB: looking for the card...")
        self._send(widget, "PNP_IMPORT_JOBS")

    def _fill_jobs(self):
        names = self._jobs()
        if names == self.job_names:
            return                                   # unchanged: don't touch the buttons
        self.job_names = names
        for b in self.job_buttons:
            self.job_box.remove(b)
            b.destroy()
        self.job_buttons = []
        for stem in names or [None]:
            if stem is None:
                b = self._gtk.Button("info", "No jobs found (Software/pnpvision/jobs)", None)
            else:
                s = job_summary(stem, with_last=False)
                sub = (f"{s['to_place']} parts, {s['board']} {s['side']}" if s.get("ok") else "unreadable")
                b = self._gtk.Button("print", f"{stem}   ({sub})", "color1")
                b.connect("clicked", self._open_job, stem)
            # KlipperScreen buttons expand to fill all space: with few jobs one button filled the
            # whole list and its label sat mid-screen (2026-11-18). Fixed-height rows from the top.
            b.set_hexpand(True)
            b.set_vexpand(False)
            b.set_valign(Gtk.Align.START)
            b.set_size_request(-1, self._row_height())
            self.job_box.pack_start(b, False, False, 0)
            self.job_buttons.append(b)
        self.job_box.show_all()

    # -- detail view -----------------------------------------------------------------------------
    def _build_detail(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True, vexpand=True)
        grid = Gtk.Grid(column_spacing=15, row_spacing=2, hexpand=True)
        self.detail = {}
        rows = (("name", "Job"), ("board", "Board"), ("parts", "Parts"), ("packages", "Packages"),
                ("feeders", "Feeders"), ("last", "Last run"), ("estimate", "Estimate"))
        for i, (key, name) in enumerate(rows):
            head = Gtk.Label(label=name, xalign=0)
            head.get_style_context().add_class("description")
            grid.attach(head, 0, i, 1, 1)
            lab = Gtk.Label(label="-", xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
            grid.attach(lab, 1, i, 1, 1)
            self.detail[key] = lab
        box.pack_start(grid, False, False, 0)

        opts = Gtk.Grid(column_homogeneous=True, column_spacing=5, hexpand=True, vexpand=True)
        self.opt_buttons = {}
        for col, (key, name) in enumerate((("no_feeders", "No feeders"), ("align", "Align first"),
                                           ("dry_run", "Dry run"))):
            b = self._gtk.Button("settings", name, "color4")
            self._mark(b, self.opts[key])
            b.connect("clicked", self._toggle, key)
            opts.attach(b, col, 0, 1, 1)
            self.opt_buttons[key] = b
        box.pack_start(opts, True, True, 0)

        act = Gtk.Grid(column_homogeneous=True, column_spacing=5, hexpand=True, vexpand=True)
        back = self._gtk.Button("arrow-left", "Back to jobs", "color2")
        back.connect("clicked", self._back)
        self.start_button = self._gtk.Button("print", "Start", "color3")
        self.start_button.connect("clicked", lambda w: self._start(w, self.selected))
        act.attach(back, 0, 0, 1, 1)
        act.attach(self.start_button, 1, 0, 2, 1)
        box.pack_start(act, True, True, 0)
        return box

    def _open_job(self, widget, stem):
        self.selected = stem
        s = job_summary(stem)
        d = self.detail
        d["name"].set_text(stem)
        if not s.get("ok"):
            for k in ("board", "parts", "packages", "feeders", "last", "estimate"):
                d[k].set_text("-")
            d["board"].set_text(s.get("error", "unreadable"))
        else:
            d["board"].set_text(f"{s['board']}, {s['side']} side")
            d["parts"].set_text(f"{s['to_place']} to place" + (f", {s['skipped']} skipped" if s["skipped"] else ""))
            d["packages"].set_text(", ".join(f"{_short_pkg(p)} x{n}" for p, n in s["packages"]) or "-")
            have = ", ".join(f"{fid}: {_short_pkg(p)} x{n}" for p, n, fid in s["covered"])
            miss = ", ".join(f"{_short_pkg(p)} x{n}" for p, n in s["missing"])
            d["feeders"].set_text((have or "none loaded") + (f"   NO FEEDER: {miss}" if miss else ""))
            last = s["last"]
            d["last"].set_text(f"{last['when']}: {last['placed']}/{last['attempted']} placed"
                               + (f", {last['cph']:.0f} CPH" if last.get("cph") else "") if last else "never run")
            d["estimate"].set_text(_elapsed(s["estimate_s"]) + " (parts with a feeder)" if s["covered"] else "-")
        self._view("detail")

    def _back(self, widget=None):
        self._fill_jobs()
        self._view("list")

    @staticmethod
    def _mark(button, on):
        ctx = button.get_style_context()
        (ctx.add_class if on else ctx.remove_class)("button_active")

    def _toggle(self, widget, key):
        self.opts[key] = not self.opts[key]
        self._mark(widget, self.opts[key])

    def _start(self, widget, stem):
        if not stem:
            return
        script = f"RUN_JOB JOB={stem.replace(' ', '_')}"
        what = "Dry run (camera only)" if self.opts["dry_run"] else "Start job"
        text = f"{what}: {stem}?"
        if self.opts["no_feeders"]:
            script += " NO_FEEDERS=1"
            text += "\nNo feeders: you load each part when asked."
        if self.opts["align"]:
            script += " ALIGN=1"
            text += "\nAlign first: the board is found again before placing."
        else:
            script += " ALIGN=0"
            text += "\nNo alignment: uses the last board position."
        if self.opts["dry_run"]:
            script += " DRY_RUN=1"
        else:
            text += "\nNozzle empty, up light on."
        self._screen._confirm_send_action(widget, text, "printer.gcode.script", {"script": script})

    # -- status view -----------------------------------------------------------------------------
    def _build_status(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True, vexpand=True)
        # while a job runs: a red line at the top, so nobody mistakes the machine for idle
        self.live_banner = Gtk.Label(label="", xalign=0.5, hexpand=True)
        self.live_banner.set_markup(LIVE_MARKUP)
        self.live_banner.set_no_show_all(True)
        box.pack_start(self.live_banner, False, False, 0)
        grid = Gtk.Grid(column_spacing=15, row_spacing=2, hexpand=True)
        self.info = {}
        rows = (("machine", "Machine"), ("job", "Job"), ("part", "Part"), ("count", "Placed"),
                ("time", "Elapsed"), ("msg", "Status"))
        for i, (key, name) in enumerate(rows):
            head = Gtk.Label(label=name, xalign=0)
            head.get_style_context().add_class("description")
            grid.attach(head, 0, i, 1, 1)
            lab = Gtk.Label(label="-", xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
            if key == "msg":
                lab.set_line_wrap(True)
                lab.set_lines(2)
            grid.attach(lab, 1, i, 1, 1)
            self.info[key] = lab
        box.pack_start(grid, False, False, 0)

        # running: Continue / Stop job; finished: Back to jobs
        run = Gtk.Grid(column_homogeneous=True, column_spacing=10, hexpand=True, vexpand=True)
        cont = self._gtk.Button("resume", "Continue", "color3")
        cont.connect("clicked", self._send, "PNP_CONTINUE")
        self.stop_button = self._gtk.Button("stop", "Stop job", "color2")
        self.stop_button.connect("clicked", self._stop)
        estop = self._gtk.Button("emergency", "EMERGENCY STOP", "color2")
        estop.connect("clicked", self._estop)
        run.attach(cont, 0, 0, 1, 1)
        run.attach(self.stop_button, 1, 0, 1, 1)
        run.attach(estop, 2, 0, 1, 1)
        done = Gtk.Grid(column_homogeneous=True, hexpand=True, vexpand=True)
        to_list = self._gtk.Button("arrow-left", "Back to jobs", "color1")
        to_list.connect("clicked", self._back)
        done.attach(to_list, 0, 0, 1, 1)
        self.run_buttons = Gtk.Stack(hexpand=True, vexpand=True)
        self.run_buttons.add_named(run, "run")
        self.run_buttons.add_named(done, "done")
        box.pack_start(self.run_buttons, True, True, 0)
        return box

    def _show_status(self, widget=None):
        self._view("status")

    def _send(self, widget, script):
        self._screen._ws.api.gcode_script(script)

    def _estop(self, widget=None):
        """One tap, no confirm: Klipper's emergency stop (M112). All motors and outputs stop at
        once (vacuum off, part drops); afterwards FIRMWARE_RESTART, then Vision home."""
        try:
            self._screen._ws.send_method("printer.emergency_stop", {})
        except Exception as e:
            logging.error(f"pnp_job estop: {e}")
            self._send(widget, "M112")

    def _stop(self, widget):
        """Two taps on the page: no confirm pop-up for a machine move to close."""
        if not self.stop_armed:
            self.stop_armed = True
            _set_button_text(self.stop_button, "Tap again to stop")
            GLib.timeout_add_seconds(STOP_ARM_S, self._disarm)
            return
        self.stop_armed = False
        self._send(widget, "PNP_STOP")
        _set_button_text(self.stop_button, "Stopping after this part")

    def _disarm(self):
        if self.stop_armed:
            self.stop_armed = False
            _set_button_text(self.stop_button, "Stop job")
        return False

    def _set_running(self, running):
        if running == self.running:
            return
        was = self.running
        self.running = running
        self.run_buttons.set_visible_child_name("run" if running else "done")
        (self.live_banner.show if running else self.live_banner.hide)()
        if running:
            self.stop_armed = False
            _set_button_text(self.stop_button, "Stop job")
            self._view("status")                                 # a job started: follow it
        elif was:
            self._view("status")                                 # just finished: keep the result shown

    # -- status, once a second while the page is shown ---------------------------------------
    def activate(self):
        if not self.running:
            self._fill_jobs()
        self._poll()
        if self.timer is None:
            self.timer = GLib.timeout_add_seconds(1, self._poll)

    def deactivate(self):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None

    def _poll(self):
        if self.view == "list" and not self.running:
            self._fill_jobs()                  # new files (SD/USB import): one listdir, rebuilt only if changed
        try:
            self._screen._ws.send_method(
                "printer.objects.query", {"objects": {STATE: None, "toolhead": ["homed_axes"]}}, self._on_status)
        except Exception as e:
            logging.error(f"pnp_job poll: {e}")
        return True

    def _on_status(self, result, method, params):
        try:
            status = result["result"]["status"]
        except (KeyError, TypeError):
            return
        GLib.idle_add(self._show, status.get(STATE), status.get("toolhead", {}).get("homed_axes", ""))

    def _show(self, st, homed):
        if st is None:
            self.info["machine"].set_text("pnp_hmi.cfg is not loaded in Klipper")
            self.list_status.set_text("pnp_hmi.cfg is not loaded in Klipper")
            return False
        if all(a in homed for a in "xyz"):
            m = "Vision homed" if int(st.get("vision_homed", 0)) else "Homed, not vision homed"
        else:
            m = "Not homed"
        if m != "Vision homed":
            m += " (a job runs Vision home first)"
        self.info["machine"].set_text(m)
        running = bool(int(st.get("job_running", 0)))
        job = st.get("job") or ""
        self.info["job"].set_text((job if running else f"{job} (finished)") if job else "No job yet")
        total = int(st.get("total", 0))
        self.info["part"].set_text(f"{st.get('part', 0)} / {total}   {st.get('ref', '')}" if total else "-")
        self.info["count"].set_text(f"{st.get('placed', 0)} placed, {st.get('failed', 0)} failed" if job else "-")
        t0, t1 = float(st.get("t_start", 0)), float(st.get("t_end", 0))
        self.info["time"].set_text(_elapsed((time.time() if running or t1 < t0 else t1) - t0) if t0 else "-")
        result = st.get("result") or ""
        self.info["msg"].set_text(result if result and not running else (st.get("msg") or "-"))
        # list view: one line, plus the "Running" shortcut while a job runs
        if running:
            self.list_status.set_text(f"{m}   |   running {job}: part {st.get('part', 0)} / {total}")
            _set_button_text(self.running_button, f"Running: {job}  (show status)")
            self.running_button.show()
        else:
            last = f"   |   last: {job}, {result}" if job and result else ""
            usb = st.get("import_msg") or ""
            self.list_status.set_text(f"{usb}   |   {m}{last}" if usb else m + last)
            self.running_button.hide()
        self._set_running(running)
        return False
