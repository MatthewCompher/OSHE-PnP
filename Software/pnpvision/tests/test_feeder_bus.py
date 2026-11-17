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
