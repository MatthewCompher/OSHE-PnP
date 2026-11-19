"""Travel heights in Moonraker.move_abs (larger Z = nozzle LOWER on this machine).
2026-11-14: a homing sweep at Z30 hit the feeders at the front. Rules: before any X/Y move the
nozzle goes up to safe_travel_z (Z26) unless it is already higher; moves that start or end at
Y < 30 (feeders) go up to Z22 first. Nothing ever goes DOWN before an X/Y move."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pnpvision.moonraker import Moonraker, MoveRefused, lift


class FakeMR(Moonraker):
    def __init__(self, xyz):
        super().__init__(x_range=(0, 235), y_range=(0, 343), z_range=(0, 51),
                         safe_travel_z=26.0, front_zone_y=30.0, front_zone_z=22.0)
        self.xyz, self.sent = list(xyz), []

    def is_homed(self, axes="xyz"):
        return True

    def position(self):
        return tuple(self.xyz)

    def gcode(self, script):
        self.sent.append(script)
        for line in script.splitlines():
            if line.startswith("G1 "):
                for w in line.split()[1:]:
                    if w[0] in "XYZ":
                        self.xyz["XYZ".index(w[0])] = float(w[1:])


def _z_before_xy(script):
    """Z values commanded before the X/Y line of one move."""
    out = []
    for line in script.splitlines():
        if line.startswith("G1 X") or line.startswith("G1 Y"):
            return out
        if line.startswith("G1 Z"):
            out.append(float(line.split()[1][1:]))
    return out


def test_plate_move_lifts_to_26_and_never_lowers():
    m = FakeMR((100, 200, 38.0))               # nozzle down at the board
    m.move_abs(x=150, y=250)
    assert _z_before_xy(m.sent[-1]) == [26.0]
    m = FakeMR((100, 200, 5.0))                # nozzle near the top (after homing)
    m.move_abs(x=150, y=250)
    assert _z_before_xy(m.sent[-1]) == []      # stays at Z5: not lowered to Z26
    assert m.xyz[2] == 5.0


def test_front_strip_needs_z22_going_in_and_coming_out():
    m = FakeMR((100, 200, 30.0))
    m.move_abs(x=100, y=10)                    # into the feeder strip
    assert _z_before_xy(m.sent[-1]) == [22.0]
    m.xyz[2] = 38.0                            # e.g. down at a feeder pocket
    m.move_abs(x=100, y=200)                   # back out
    assert _z_before_xy(m.sent[-1]) == [22.0]
    m = FakeMR((100, 200, 26.0))
    m.move_abs(x=150, y=31)                    # both ends at Y >= 30: travel height is enough
    assert _z_before_xy(m.sent[-1]) == []


def test_lift_helper_and_stay_low_near_feeders():
    m = FakeMR((100, 200, 5.0))
    lift(m)
    assert m.sent == []                        # already higher than Z26
    m = FakeMR((100, 20, 30.0))
    with pytest.raises(MoveRefused):
        m.move_abs(x=101, y=20, stay_low=True)
