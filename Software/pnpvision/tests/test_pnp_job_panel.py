"""The KlipperScreen PnP job page (Software/Klipper/klipperscreen/pnp_job.py) with GTK and
KlipperScreen stubbed out: what it shows for a given _PNP_STATE and what G-code its buttons send.
Catches Python mistakes before the page is tried on the touchscreen (GTK layout is not checked)."""
import importlib.util
import os
import sys
import time
import types
from unittest import mock

HERE = os.path.dirname(__file__)
PANEL = os.path.join(HERE, "..", "..", "Klipper", "klipperscreen", "pnp_job.py")


class _Label:
    def __init__(self, label="", **kw):
        self.text = label

    def set_text(self, t):
        self.text = t


def _load(tmp_jobs):
    gtk = mock.MagicMock()
    gtk.Label = _Label
    glib = mock.MagicMock()
    glib.idle_add = lambda f, *a: f(*a)
    repo = types.SimpleNamespace(Gtk=gtk, GLib=glib, Pango=mock.MagicMock())
    gi = types.SimpleNamespace(require_version=lambda *a: None, repository=repo)

    class ScreenPanel:
        def __init__(self, screen, title, **kw):
            self._screen = screen
            self._gtk = mock.MagicMock()
            self.content = mock.MagicMock()
            self.bts = 1.0
            self.title = title

    ks = types.ModuleType("ks_includes")
    sp = types.ModuleType("ks_includes.screen_panel")
    sp.ScreenPanel = ScreenPanel
    with mock.patch.dict(sys.modules, {"gi": gi, "gi.repository": repo, "ks_includes": ks,
                                       "ks_includes.screen_panel": sp}):
        spec = importlib.util.spec_from_file_location("pnp_job_under_test", PANEL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    mod.JOBS_DIR = tmp_jobs
    return mod


def _panel(tmp_path):
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    (jobs / "Test PCB-top.job.json").write_text("{}")
    mod = _load(str(jobs))
    screen = mock.MagicMock()
    p = mod.Panel(screen, None)
    return mod, p, screen


def test_idle_page_and_start_script(tmp_path):
    mod, p, screen = _panel(tmp_path)
    assert p.running is False
    assert mod.Panel._jobs() == ["Test PCB-top"]
    p._toggle(mock.MagicMock(), "dry_run")
    p._start(mock.MagicMock(), "Test PCB-top")
    args = screen._confirm_send_action.call_args[0]
    assert args[2] == "printer.gcode.script"
    assert args[3] == {"script": "RUN_JOB JOB=Test_PCB-top NO_FEEDERS=1 DRY_RUN=1"}, args[3]
    assert "Dry run" in args[1]


def test_running_page_shows_state_and_buttons(tmp_path):
    mod, p, screen = _panel(tmp_path)
    st = {"vision_homed": 1, "job_running": 1, "job": "Test PCB-top", "part": 3, "total": 12,
          "ref": "R0805_18", "placed": 2, "failed": 0, "t_start": time.time() - 75, "t_end": 0.0,
          "msg": "on nozzle: offset [0.1, 0.2] mm", "result": ""}
    p._show(st, "xyz")
    assert p.running is True
    assert p.info["machine"].text == "Vision homed"
    assert p.info["part"].text.startswith("3 / 12") and "R0805_18" in p.info["part"].text
    assert p.info["count"].text == "2 placed, 0 failed"
    assert p.info["time"].text.startswith("1 min 1")
    assert p.info["msg"].text.startswith("on nozzle")
    p._send(None, "PNP_CONTINUE")
    screen._ws.api.gcode_script.assert_called_with("PNP_CONTINUE")


def test_finished_and_not_homed(tmp_path):
    mod, p, screen = _panel(tmp_path)
    t0 = time.time() - 300
    st = {"vision_homed": 0, "job_running": 0, "job": "Test PCB-top", "part": 12, "total": 12,
          "ref": "R0805_9", "placed": 12, "failed": 0, "t_start": t0, "t_end": t0 + 120,
          "msg": "timing: ...", "result": "Done: 12/12 placed, 90 CPH"}
    p._show(st, "")
    assert p.running is False
    assert p.info["machine"].text.startswith("Not homed")
    assert p.info["job"].text == "Test PCB-top (finished)"
    assert p.info["time"].text == "2 min 00 s"
    assert p.info["msg"].text == "Done: 12/12 placed, 90 CPH"
    p._show(None, "")                                     # pnp_hmi.cfg missing: no crash
    assert "not loaded" in p.info["machine"].text


def test_poll_callback(tmp_path):
    mod, p, screen = _panel(tmp_path)
    p._poll()
    method, params, cb = screen._ws.send_method.call_args[0]
    assert method == "printer.objects.query" and "gcode_macro _PNP_STATE" in params["objects"]
    cb({"result": {"status": {"gcode_macro _PNP_STATE": {"job_running": 1, "job": "x"},
                              "toolhead": {"homed_axes": "xyz"}}}}, method, params)
    assert p.running is True
    cb({"error": "klippy not ready"}, method, params)     # ignored
