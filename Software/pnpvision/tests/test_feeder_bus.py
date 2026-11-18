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
