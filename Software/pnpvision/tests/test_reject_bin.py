"""Factory reject-bin position from the plate layout (config [layout]) and the up-camera centre."""
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
from pnpvision.cli import default_reject_bin_xy, reject_bin_xy

CFG = {"layout": {"insert_pitch_mm": 30.0, "insert_origin_mm": [10.0, 10.0],
                  "reject_bin_inserts": [[1, 4], [2, 4]], "up_cam_insert": [3, 1]}}
MS = {"up_cam_xy_mm": [85.841, 137.697]}


def test_default_from_layout():
    x, y = default_reject_bin_xy(CFG, MS)
    # bin middle (55, 130) minus up camera (100, 40) on the plate = (-45, +90)
    assert abs(x - 40.841) < 1e-9 and abs(y - 227.697) < 1e-9


def test_taught_overrides_default_and_null_falls_back():
    assert reject_bin_xy(CFG, {**MS, "reject_bin_xy": [41.0, 229.0]}) == ([41.0, 229.0], "taught")
    xy, src = reject_bin_xy(CFG, {**MS, "reject_bin_xy": None})
    assert src.startswith("default") and abs(xy[0] - 40.841) < 1e-9
    assert reject_bin_xy({"layout": {}}, MS) == (None, "none")
