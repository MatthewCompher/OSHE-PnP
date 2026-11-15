"""Empty-nozzle check after placing (real up-camera photos, 2026-11-14, 400x400 crops around the
nozzle axis). With no expected size the 6 mm search found the round 7.4 mm tip collar (fill 0.785,
a circle in its box) and reported "part came back on the nozzle"; the runner now passes the
placed part's body size."""
import os

import cv2
import numpy as np

from pnpvision.motion import MotionMap
from pnpvision.upcam import UpCam

HERE = os.path.dirname(__file__)
NOZZLE_PX = (199.73, 199.64)
BODY_0805 = (2.0, 1.25)


class _Lens:
    newK = np.array([[1.0, 0, NOZZLE_PX[0]], [0, 1.0, NOZZLE_PX[1]], [0, 0, 1.0]])


def _upcam():
    motion = MotionMap.load(os.path.join(HERE, "..", "calibration", "motion_up.json"))
    return UpCam(None, _Lens(), None, motion, nozzle_px=NOZZLE_PX, search_radius_mm=6.0)


def _img(name):
    return cv2.imread(os.path.join(HERE, "data", name))


def test_empty_nozzle_with_body_size_is_empty():
    res = _upcam().inspect(BODY_0805, 0.3, img=_img("up_empty_collar_20261114.png"))
    assert not res["ok"] and "offset_mm" not in res


def test_empty_nozzle_without_size_finds_the_collar():
    # the old behaviour, kept as a warning: never verify an empty nozzle without a size
    res = _upcam().inspect(None, 0.3, img=_img("up_empty_collar_20261114.png"))
    assert res["ok"] and res["size_mm"][0] > 7


def test_part_on_nozzle_found():
    res = _upcam().inspect(BODY_0805, 0.3, img=_img("up_part_20261114.png"))
    assert res["ok"]
    assert abs(res["size_mm"][0] - 2.13) < 0.1 and abs(res["size_mm"][1] - 1.32) < 0.1
