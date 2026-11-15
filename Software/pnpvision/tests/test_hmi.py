"""run-job's touchscreen dialogs against a fake Klipper: what is sent, and how button presses
(PNP_ANSWER / PNP_STOP macros) come back."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pnpvision.hmi import Hmi


class FakeKlipper:
    """Runs the pnp_hmi.cfg macros' effect on their variables; `presses` = button values the
    operator taps, one per dialog, after `delay` polls."""

    def __init__(self, presses=(), delay=2):
        self.vars = {"value": 1, "seq": 0, "stop": 0}
        self.sent, self.presses, self.delay = [], list(presses), delay
        self.polls = 0
        self.dialog_open = False

    def gcode(self, script):
        self.sent.append(script)
        if "action:prompt_show" in script:
            self.dialog_open, self.polls = True, 0
        elif "action:prompt_end" in script:
            self.dialog_open = False
        elif script.startswith("SET_GCODE_VARIABLE MACRO=PNP_ANSWER VARIABLE=stop VALUE=0"):
            self.vars["stop"] = 0

    def press(self, value):                  # PNP_ANSWER VALUE=value
        self.vars["value"] = value
        self.vars["seq"] += 1

    def press_stop(self):                    # PNP_STOP
        self.vars["stop"] = 1
        self.press(0)

    def query(self, obj):
        assert obj == "gcode_macro PNP_ANSWER"
        if self.dialog_open:
            self.polls += 1
            if self.polls == self.delay and self.presses:
                v = self.presses.pop(0)
                self.press_stop() if v == "stop" else self.press(v)
        return dict(self.vars)


def _hmi(k):
    return Hmi(k, sleep=lambda s: None, echo=lambda *a: None)


def test_continue_dialog():
    k = FakeKlipper(presses=[1])
    h = _hmi(k)
    h.start()
    assert h.ask("Fit nozzle tip N08 (now: N14), then press Enter... ") == ""
    cmds = [s for s in k.sent if "action:" in s]
    assert cmds[0].endswith('action:prompt_begin PnP job"')
    assert any("tap Continue" in c for c in cmds), cmds
    assert any("prompt_footer_button Continue|PNP_ANSWER VALUE=1|primary" in c for c in cmds), cmds
    assert not any("VALUE=0" in c for c in cmds), cmds            # nothing to stop here
    assert cmds[-1].endswith('action:prompt_end"') and not k.dialog_open


def test_yes_no_and_stop_choice():
    k = FakeKlipper(presses=[0, 1, 0])
    h = _hmi(k)
    assert h.ask("Start? [y/N] ") == "n"
    assert h.ask("Start? [y/N] ") == "y"
    q = "  R1: feeder F1 gave no good part 3 times. Fix it and press Enter to go on with the next part, or type q to stop: "
    assert h.ask(q) == "q"
    assert any("prompt_footer_button Stop|PNP_ANSWER VALUE=0|error" in s for s in k.sent)


def test_stop_button_and_quotes():
    k = FakeKlipper(presses=["stop"])
    h = _hmi(k)
    h.start()
    assert not h.stop_requested()
    h.ask("Feeder F3 (SOIC): advance the tape one part by hand, then press Enter... ")
    assert h.stop_requested()
    h.start()                                                      # next job clears it
    assert not h.stop_requested()
    h.say('part "U1" placed\nsecond line')
    msgs = [s for s in k.sent if s.startswith("RESPOND TYPE=command MSG=")]     # console only, no pop-up
    assert (msgs[-2] == "RESPOND TYPE=command MSG=\"part 'U1' placed\""
            and msgs[-1] == 'RESPOND TYPE=command MSG="second line"'), msgs
    h.say("job result", popup=True)
    assert k.sent[-1] == 'RESPOND MSG="job result"'                              # echo: pops up


def test_missing_macros_reported():
    class NoMacro(FakeKlipper):
        def query(self, obj):
            return {}
    try:
        _hmi(NoMacro()).start()
    except RuntimeError as e:
        assert "pnp_hmi.cfg" in str(e)
    else:
        raise AssertionError("expected an error")


def test_run_job_with_hmi():
    """The simulated job from test_runner, answered through the dialogs; stop after 2 parts."""
    import numpy as np
    import test_runner as T
    from pnpvision.feeders import SimFeederBus
    from pnpvision.rotation import Rotator
    from pnpvision.runner import run_job
    job = T._job()
    holder = {}
    k = FakeKlipper(presses=[1] * 20)
    h = _hmi(k)
    h.start()
    bank = T._bank(SimFeederBus(on_feed=lambda s: holder["w"].on_feed(s)), h.ask)
    w = holder["w"] = T.World(bank.feeders)
    parts = []

    def stop():
        if len(parts) == 2:
            k.press_stop()
        parts.append(1)
        return h.stop_requested()
    res = run_job(job, T.POSE, {"down_cam_offset_mm": T.OFF.tolist(), "up_cam_xy_mm": T.UP_XY.tolist()}, w,
                  w.up_inspect, Rotator(w.gcode, direction=T.TRUE_DIR), bank, T.TIPS, only=set(T.ONLY),
                  current_tip="N14", reject_xy=T.BIN, ask=h.ask, say=h.say, stop_requested=stop)
    assert [r["status"] for r in res] == ["placed", "placed"], res
    assert any("Fit nozzle tip N08" in s for s in k.sent)
    assert any("job done: 2/6 placed" in s for s in k.sent), [s for s in k.sent if "job done" in s]


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(__file__))
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("PASS", n)


class FakeState:
    """Klipper objects for the job page / homing checks."""

    def __init__(self, homed="xyz", vision_homed=1, print_state="paused"):
        self.homed, self.vh, self.ps = homed, vision_homed, print_state
        self.sent = []

    def gcode(self, script):
        self.sent.append(script)

    def is_homed(self, axes="xyz"):
        return all(a in self.homed for a in axes)

    def query(self, obj):
        if obj == "gcode_macro _PNP_STATE":
            return {"vision_homed": self.vh, "job_running": 1}
        if obj == "print_stats":
            return {"state": self.ps}
        return {}


def test_progress_sets_layer_and_status_line():
    k = FakeState()
    _hmi(k).progress(3, 12, "R0805_18", placed=2)
    assert "SET_PRINT_STATS_INFO TOTAL_LAYER=12 CURRENT_LAYER=3" in k.sent
    assert any(s.startswith("M117 Part 3/12: R0805_18, 2 placed") for s in k.sent), k.sent


def test_end_job_completes_paused_launcher_without_moving():
    k = FakeState(print_state="paused")
    _hmi(k).end_job(True, "Job done")
    assert k.sent[0] == "SET_GCODE_VARIABLE MACRO=_PNP_STATE VARIABLE=job_running VALUE=0"
    assert "SAVE_GCODE_STATE NAME=PAUSE_STATE\nRESUME_BASE" in k.sent      # re-save first: no move back
    k = FakeState(print_state="paused")
    _hmi(k).end_job(False)
    assert "CANCEL_PRINT_BASE" in k.sent and not any("RESUME" in s for s in k.sent)
    k = FakeState(print_state="standby")                                   # started from the console
    _hmi(k).end_job(True)
    assert not any("RESUME" in s or "CANCEL" in s for s in k.sent)


def test_homing_problem():
    from pnpvision.hmi import homing_problem
    assert homing_problem(FakeState()) is None
    hard, text = homing_problem(FakeState(homed=""))
    assert hard and "not homed" in text
    hard, text = homing_problem(FakeState(vision_homed=0))
    assert not hard and "Vision home" in text
