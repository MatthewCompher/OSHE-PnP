"""KlipperFeederBus: a feed is FEEDER_TOGGLE SLOT=n through Moonraker; Klipper errors become FeederError."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pnpvision.feeders import FeederError, KlipperFeederBus


class FakeMR:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def gcode(self, script):
        if self.fail:
            raise RuntimeError("400 Bad Request: FEEDER_TOGGLE: SLOT must be 1, 2 or 3")
        self.sent.append(script)


def test_feed_sends_feeder_toggle_with_slot():
    mr = FakeMR()
    bus = KlipperFeederBus(mr)
    bus.feed(3)
    bus.wait(3)
    assert mr.sent == ["FEEDER_TOGGLE SLOT=3"]


def test_klipper_error_is_a_feeder_error():
    with pytest.raises(FeederError, match="slot 7"):
        KlipperFeederBus(FakeMR(fail=True)).feed(7)


def test_cli_defaults_to_the_klipper_bus(monkeypatch):
    from pnpvision import cli
    monkeypatch.setattr(cli, "make_mr", lambda cfg: FakeMR())
    assert isinstance(cli._feeder_bus({"feeders": {}}), KlipperFeederBus)
    assert isinstance(cli._feeder_bus({"feeders": {"bus": "klipper"}}), KlipperFeederBus)


def test_bare_tip_blob_counts_as_empty():
    from pnpvision.runner import looks_empty
    tip = {"ok": False, "offset_mm": [0.0, 0.0], "size_mm": [0.87, 0.79], "reason": "size 0.87x0.79 mm vs expected"}
    assert looks_empty(tip, (1.6, 0.8)) and looks_empty(tip, (2.0, 1.25))
    assert looks_empty({"ok": False, "reason": "no part found"}, (1.6, 0.8))
    assert not looks_empty({"ok": True, "offset_mm": [0, 0], "size_mm": [1.6, 0.8]}, (1.6, 0.8))
    tilted = {"ok": False, "offset_mm": [0, 0], "size_mm": [1.9, 0.8]}       # a real part, wrong size
    assert not looks_empty(tilted, (1.6, 0.8))


def test_feeder_cycle_picks_feeds_and_drops(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    from pnpvision import cli
    from pnpvision import machine_state as MS

    class Machine:
        safe_travel_z, feedrate = 26.0, 3000

        def __init__(self):
            self.pos, self.log = [0.0, 0.0, 5.0], []

        def position(self):
            return tuple(self.pos)

        def move_abs(self, x=None, y=None, z=None, feedrate=None, stay_low=False):
            for i, v in enumerate((x, y, z)):
                if v is not None:
                    self.pos[i] = v
            self.log.append(("move", x, y, z))

        def gcode(self, script):
            self.log.append(("gcode", script))

    m = Machine()
    feeders = tmp_path / "feeders.json"
    feeders.write_text(json.dumps({"feeders": [{"id": "F1", "kind": "servo", "servo": 1, "xy": [34.7, 26.7],
                                                "part_top_z": 32.7, "teach_tip": "N08", "package": "R_0603_1608Metric"}]}))
    monkeypatch.setattr(cli, "make_mr", lambda cfg: m)
    monkeypatch.setattr(cli, "_feeders_path", lambda cfg: str(feeders))
    monkeypatch.setattr(cli, "_feeder_bus", lambda cfg: KlipperFeederBus(m))
    monkeypatch.setattr(cli, "reject_bin_xy", lambda cfg, ms: ([60.0, 130.0], "taught"))
    monkeypatch.setattr(cli.C, "rel", lambda cfg, path: path)
    monkeypatch.setattr(MS, "load", lambda path: {"current_tip": "N08", "tips": {"N08": {"board_touch_z": 39.5}}})
    cli.cmd_feeder_cycle({"run": {}}, SimpleNamespace(feeder="F1", n=2, tip=None, yes=True))
    g = [e[1] for e in m.log if e[0] == "gcode"]
    assert g.count("FEEDER_TOGGLE SLOT=1") == 2
    assert sum(s.startswith("VALVE_ON") for s in g) == 2 and sum(s.startswith("VALVE_OFF") for s in g) >= 2
    assert ("move", None, None, 33.1) in m.log                # part top 32.7 + 0.4 pick press
    assert ("move", 60.0, 130.0, None) in m.log
