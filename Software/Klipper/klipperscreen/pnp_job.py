"""PnP job page for KlipperScreen (the machine's touchscreen).

Install (Pi): link this file into KlipperScreen's panels folder and restart KlipperScreen:
    ln -sf ~/OSHE-PnP/Software/Klipper/klipperscreen/pnp_job.py ~/KlipperScreen/panels/pnp_job.py
It is opened from the "Pick & Place" menu (KlipperScreen_pnp.conf: panel: pnp_job).

Shows the job state that run-job --hmi publishes in Klipper (gcode_macro _PNP_STATE, see
Software/Klipper/pnp_hmi.cfg): machine homing, job, part n/total, placed/failed, elapsed time,
the latest status line and the result. Idle: options + one button per job (RUN_JOB macro).
Running: Continue (answers the open question) and Stop job (two taps on the page itself, no
pop-up that a machine move could close). Job questions still open as dialogs over any page.

Layout rules (2026-11-14 screen test): status lines never wrap (they pushed the buttons off
screen), the two button sets are built once and only switched (never rebuilt), and buttons are
KlipperScreen's normal size. Light: one small Moonraker query per second, only while shown.
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
STOP_ARM_S = 5


def _elapsed(sec):
    sec = int(max(0, sec))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h} h {m:02d} min" if h else (f"{m} min {s:02d} s" if m else f"{s} s")


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
        # 2026-11-18: feeders work (F1): "No feeders" defaults off. "Align first" defaults on and
        # re-finds the board before the job (camera drives to pad A by itself; not counted in CPH);
        # untick it to skip that for a board that hasn't moved.
        self.opts = {"no_feeders": False, "align": True, "dry_run": False}

        # status: one line each (ellipsized), the status line at most two
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

        # idle: options + job buttons
        self.idle = Gtk.Grid(row_homogeneous=True, column_homogeneous=True, row_spacing=5,
                             column_spacing=5, hexpand=True, vexpand=True)
        self.opt_buttons = {}
        for col, (key, name) in enumerate((("no_feeders", "No feeders"), ("align", "Align first"),
                                           ("dry_run", "Dry run"))):
            b = self._gtk.Button("settings", name, "color4")
            self._mark(b, self.opts[key])
            b.connect("clicked", self._toggle, key)
            self.idle.attach(b, col, 0, 1, 1)
            self.opt_buttons[key] = b
        self.job_buttons = []

        # running: Continue / Stop job
        run = Gtk.Grid(column_homogeneous=True, column_spacing=10, hexpand=True, vexpand=True)
        cont = self._gtk.Button("resume", "Continue", "color3")
        cont.connect("clicked", self._send, "PNP_CONTINUE")
        self.stop_button = self._gtk.Button("stop", "Stop job", "color2")
        self.stop_button.connect("clicked", self._stop)
        run.attach(cont, 0, 0, 1, 1)
        run.attach(self.stop_button, 1, 0, 1, 1)

        self.stack = Gtk.Stack(hexpand=True, vexpand=True)
        self.stack.add_named(self.idle, "idle")
        self.stack.add_named(run, "run")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True, vexpand=True)
        box.pack_start(grid, False, False, 0)
        box.pack_start(self.stack, True, True, 0)
        self.content.add(box)
        self._fill_jobs()
        self._set_running(False)

    # -- idle side -----------------------------------------------------------------------------
    @staticmethod
    def _jobs():
        try:
            return sorted(f[:-len(".job.json")] for f in os.listdir(JOBS_DIR) if f.endswith(".job.json"))
        except OSError as e:
            logging.error(f"pnp_job: {e}")
            return []

    def _fill_jobs(self):
        names = self._jobs()
        if names == self.job_names:
            return                                   # unchanged: don't touch the buttons
        self.job_names = names
        for b in self.job_buttons:
            self.idle.remove(b)
            b.destroy()
        self.job_buttons = []
        for i, stem in enumerate(names or [None]):
            if stem is None:
                b = self._gtk.Button("info", "No jobs found", None)
            else:
                b = self._gtk.Button("print", stem, "color1")
                b.connect("clicked", self._start, stem)
            self.idle.attach(b, i % 3, 1 + i // 3, 1, 1)
            self.job_buttons.append(b)
        self.idle.show_all()

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
            text += "\nAlign first: the board is found again before placing."
        else:
            script += " ALIGN=0"
            text += "\nNo alignment: uses the last board position."
        if self.opts["dry_run"]:
            script += " DRY_RUN=1"
        else:
            text += "\nNozzle empty, up light on."
        self._screen._confirm_send_action(widget, text, "printer.gcode.script", {"script": script})

    # -- running side --------------------------------------------------------------------------
    def _send(self, widget, script):
        self._screen._ws.api.gcode_script(script)

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
        self.running = running
        if running:
            self.stop_armed = False
            _set_button_text(self.stop_button, "Stop job")
        self.stack.set_visible_child_name("run" if running else "idle")

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
        self._set_running(running)
        return False
