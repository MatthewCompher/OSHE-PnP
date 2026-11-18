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

    def __getattr__(self, name):                 # get_style_context, set_lines, ... : no-ops
        return mock.MagicMock()


def _load(tmp_jobs):
    gtk = mock.MagicMock()
    gtk.Label = _Label
    gtk.Container = type("Container", (), {})          # isinstance() needs real classes
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


def test_list_detail_and_start_script(tmp_path):
    mod, p, screen = _panel(tmp_path)
    assert p.running is False and p.view == "list"
    assert mod.Panel._jobs() == ["Test PCB-top"]
    p._open_job(mock.MagicMock(), "Test PCB-top")
    assert p.view == "detail" and p.selected == "Test PCB-top"
    p._toggle(mock.MagicMock(), "dry_run")
    p._start(mock.MagicMock(), p.selected)
    args = screen._confirm_send_action.call_args[0]
    assert args[2] == "printer.gcode.script"
    assert args[3] == {"script": "RUN_JOB JOB=Test_PCB-top ALIGN=1 DRY_RUN=1"}, args[3]
    assert "Dry run" in args[1]
    p._toggle(mock.MagicMock(), "align")                   # untick: skip the alignment
    p._toggle(mock.MagicMock(), "dry_run")
    p._start(mock.MagicMock(), p.selected)
    assert screen._confirm_send_action.call_args[0][3] == {"script": "RUN_JOB JOB=Test_PCB-top ALIGN=0"}
    p._back()
    assert p.view == "list"


def test_running_page_shows_state_and_buttons(tmp_path):
    mod, p, screen = _panel(tmp_path)
    st = {"vision_homed": 1, "job_running": 1, "job": "Test PCB-top", "part": 3, "total": 12,
          "ref": "R0805_18", "placed": 2, "failed": 0, "t_start": time.time() - 75, "t_end": 0.0,
          "msg": "on nozzle: offset [0.1, 0.2] mm", "result": ""}
    p._show(st, "xyz")
    assert p.running is True and p.view == "status"          # a job started: the page follows it
    assert p.info["machine"].text == "Vision homed"
    assert "running Test PCB-top" in p.list_status.text
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


def test_stop_needs_two_taps_and_page_is_not_rebuilt(tmp_path):
    mod, p, screen = _panel(tmp_path)
    run = {"vision_homed": 1, "job_running": 1, "job": "j", "t_start": time.time()}
    p._show(run, "xyz")
    stop = p.stop_button
    p._stop(stop)                                          # first tap: only arms
    assert not screen._ws.api.gcode_script.called
    stop.set_label.assert_called_with("Tap again to stop")
    p._show(run, "xyz")                                    # status updates don't touch the buttons
    assert p.stop_button is stop and p.stop_armed
    p._stop(stop)                                          # second tap: stop
    screen._ws.api.gcode_script.assert_called_with("PNP_STOP")
    stop.set_label.assert_called_with("Stopping after this part")
    p._stop(stop)                                          # a later single tap arms again
    assert screen._ws.api.gcode_script.call_count == 1
    p._disarm()
    stop.set_label.assert_called_with("Stop job")


def test_job_buttons_only_rebuilt_when_the_list_changes(tmp_path):
    mod, p, screen = _panel(tmp_path)
    first = list(p.job_buttons)
    p.activate()
    assert p.job_buttons == first
    (tmp_path / "jobs" / "Other-top.job.json").write_text("{}")
    p.activate()
    assert len(p.job_buttons) == 2


def test_finished_job_keeps_its_result_then_back_to_list(tmp_path):
    mod, p, screen = _panel(tmp_path)
    p._show({"job_running": 1, "job": "j", "t_start": time.time()}, "xyz")
    p._show({"job_running": 0, "job": "j", "result": "Done: 23/23 placed, 527 CPH",
             "t_start": time.time() - 160, "t_end": time.time()}, "xyz")
    assert p.running is False and p.view == "status"
    assert p.info["msg"].text.startswith("Done")
    p._back()
    assert p.view == "list" and "Done: 23/23" in p.list_status.text


def test_job_summary(tmp_path):
    import json
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    pl = ([{"ref": f"R0603_{i}", "package": "R_0603_1608Metric"} for i in range(23)]
          + [{"ref": f"R0805_{i}", "package": "R_0805_2012Metric"} for i in range(23)]
          + [{"ref": "U1", "package": "SOIC-8_3.9x4.9mm_P1.27mm", "skip": True}])
    (jobs / "B-top.job.json").write_text(json.dumps({"board": {"name": "B", "side": "top"}, "placements": pl}))
    feeders = tmp_path / "feeders.json"
    feeders.write_text(json.dumps({"feeders": [{"id": "F1", "package": "R_0603_1608Metric"}]}))
    res = tmp_path / "results"
    res.mkdir()
    (res / "job_20261118_133934.json").write_text(json.dumps(
        {"job": "/home/pnp/x/jobs/B-top.job.json", "timing": {"placed": 23, "attempted": 23, "cph": 527.1,
                                                            "s_per_part": 6.83}}))
    mod = _load(str(jobs))
    s = mod.job_summary("B-top", str(jobs), str(feeders), str(res))
    assert s["to_place"] == 46 and s["skipped"] == 1
    assert s["covered"] == [("R_0603_1608Metric", 23, "F1")]
    assert s["missing"] == [("R_0805_2012Metric", 23)]
    assert s["last"]["cph"] == 527.1 and s["last"]["when"] == "11-18 13:39"
    assert abs(s["estimate_s"] - 23 * 6.83) < 1e-6
    assert not mod.job_summary("nope", str(jobs), str(feeders), str(res))["ok"]


def test_usb_import_button_and_list_refresh(tmp_path):
    mod, p, screen = _panel(tmp_path)
    p._import(None)
    screen._ws.api.gcode_script.assert_called_with("PNP_IMPORT_JOBS")
    (tmp_path / "jobs" / "New board-top.job.json").write_text('{"placements": []}')
    p._poll()                                              # list view: picks up the new file
    assert p.job_names == ["New board-top", "Test PCB-top"]
    p._show({"vision_homed": 1, "job_running": 0, "import_msg": "USB: loaded 1 job (New board-top)"}, "xyz")
    assert p.list_status.text.startswith("USB: loaded 1 job")


def test_emergency_stop_and_live_banner(tmp_path):
    mod, p, screen = _panel(tmp_path)
    p.live_banner = mock.MagicMock()
    p._show({"vision_homed": 1, "job_running": 1, "job": "j", "t_start": time.time()}, "xyz")
    p.live_banner.show.assert_called()                     # red "JOB RUNNING" line while live
    p._estop(None)                                         # one tap, no confirm
    screen._ws.send_method.assert_called_with("printer.emergency_stop", {})
    p._show({"vision_homed": 1, "job_running": 0, "job": "j", "result": "Done"}, "xyz")
    p.live_banner.hide.assert_called()
