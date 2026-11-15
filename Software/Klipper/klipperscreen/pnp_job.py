"""PnP job page for KlipperScreen (the machine's touchscreen).

Install (Pi): link this file into KlipperScreen's panels folder and restart KlipperScreen:
    ln -sf ~/OSHE-PnP/Software/Klipper/klipperscreen/pnp_job.py ~/KlipperScreen/panels/pnp_job.py
It is opened from the "Pick & Place" menu (KlipperScreen_pnp.conf: panel: pnp_job).

Shows the job state that run-job --hmi publishes in Klipper (gcode_macro _PNP_STATE, see
Software/Klipper/pnp_hmi.cfg): machine homing, job, part n/total, placed/failed, elapsed time,
the latest status line and the result. Idle: start a job (RUN_JOB macro). Running: Continue
(answers the open question) and Stop job. Job questions still open as dialogs over any page.
Light: polls one small Moonraker query per second, only while this page is on screen.
"""
import logging
import os
import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk, Pango

from ks_includes.screen_panel import ScreenPanel

JOBS_DIR = os.path.expanduser("~/OSHE-PnP/Software/pnpvision/jobs")
STATE = "gcode_macro _PNP_STATE"


def _elapsed(sec):
    sec = int(max(0, sec))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h} h {m:02d} min" if h else (f"{m} min {s:02d} s" if m else f"{s} s")


def _label(text="-", **kw):
    return Gtk.Label(label=text, xalign=0, wrap=True, wrap_mode=Pango.WrapMode.WORD_CHAR, **kw)


class Panel(ScreenPanel):
    def __init__(self, screen, title):
        super().__init__(screen, title or "PnP Job")
        self.timer = None
        self.running = None                      # what the bottom area shows now
        self.opts = {"no_feeders": True, "align": False, "dry_run": False}

        grid = Gtk.Grid(column_spacing=15, row_spacing=4, hexpand=True)
        self.info = {}
        rows = (("machine", "Machine"), ("job", "Job"), ("part", "Part"), ("count", "Placed"),
                ("time", "Elapsed"), ("msg", "Status"))
        for i, (key, name) in enumerate(rows):
            grid.attach(_label(f"<b>{name}</b>", use_markup=True, valign=Gtk.Align.START), 0, i, 1, 1)
            self.info[key] = _label(hexpand=True)
            grid.attach(self.info[key], 1, i, 1, 1)

        self.bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, vexpand=True, spacing=5)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True, vexpand=True)
        box.pack_start(grid, False, False, 0)
        box.pack_start(self.bottom, True, True, 0)
        self.content.add(box)
        self._build_bottom(False)

    # -- the lower half: job list (idle) or Continue / Stop (running) ------------------------
    def _clear_bottom(self):
        for child in self.bottom.get_children():
            self.bottom.remove(child)
            child.destroy()

    def _build_bottom(self, running):
        self.running = running
        self._clear_bottom()
        if running:
            row = Gtk.Box(spacing=10, hexpand=True, vexpand=True)
            cont = self._gtk.Button("resume", "Continue", "color3")
            cont.connect("clicked", self._send, "PNP_CONTINUE")
            stop = self._gtk.Button("stop", "Stop job", "color2")
            stop.connect("clicked", self._confirm, "Stop the job after the current part?", "PNP_STOP")
            row.pack_start(cont, True, True, 0)
            row.pack_start(stop, True, True, 0)
            self.bottom.pack_start(row, True, True, 0)
        else:
            opts = Gtk.Box(spacing=5, hexpand=True, vexpand=False)
            for key, name in (("no_feeders", "No feeders"), ("align", "Align first"), ("dry_run", "Dry run")):
                b = self._gtk.Button(None, name, None, self.bts, Gtk.PositionType.LEFT, 1)
                b.get_style_context().add_class("buttons_slim")
                self._mark(b, self.opts[key])
                b.connect("clicked", self._toggle, key)
                opts.pack_start(b, True, True, 0)
            self.bottom.pack_start(opts, False, False, 0)
            jobs = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            names = self._jobs()
            if not names:
                jobs.add(_label(f"No jobs in {JOBS_DIR}"))
            for stem in names:
                b = self._gtk.Button("resume", stem, "color1", self.bts, Gtk.PositionType.LEFT, 1)
                b.connect("clicked", self._start, stem)
                jobs.add(b)
            sw = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
            sw.add(jobs)
            self.bottom.pack_start(sw, True, True, 0)
        self.bottom.show_all()

    @staticmethod
    def _jobs():
        try:
            return sorted(f[:-len(".job.json")] for f in os.listdir(JOBS_DIR) if f.endswith(".job.json"))
        except OSError as e:
            logging.error(f"pnp_job: {e}")
            return []

    @staticmethod
    def _mark(button, on):
        ctx = button.get_style_context()
        (ctx.add_class if on else ctx.remove_class)("button_active")

    def _toggle(self, widget, key):
        self.opts[key] = not self.opts[key]
        self._mark(widget, self.opts[key])

    def _start(self, widget, stem):
        script = f"RUN_JOB JOB={stem.replace(' ', '_')}"
        what = "Dry run (camera only)" if self.opts["dry_run"] else "Start job"
        text = f"{what}: {stem}?"
        if self.opts["no_feeders"]:
            script += " NO_FEEDERS=1"
            text += "\nNo feeders: you load each part when asked."
        if self.opts["align"]:
            script += " ALIGN=1"
            text += "\nAlign first: the down camera must be on alignment pad A."
        if self.opts["dry_run"]:
            script += " DRY_RUN=1"
        else:
            text += "\nNozzle empty, up light on."
        self._confirm(widget, text, script)

    def _send(self, widget, script):
        self._screen._ws.api.gcode_script(script)

    def _confirm(self, widget, text, script):
        self._screen._confirm_send_action(widget, text, "printer.gcode.script", {"script": script})

    # -- status, once a second while the page is shown ---------------------------------------
    def activate(self):
        if self.running is False:
            self._build_bottom(False)            # re-read the job list
        self._poll()
        if self.timer is None:
            self.timer = GLib.timeout_add_seconds(1, self._poll)

    def deactivate(self):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None

    def _poll(self):
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
        if running != self.running:
            self._build_bottom(running)
        return False
