"""Nozzle bore over the up camera with a glint/speck notching its edge (real photo, 2026-11-14,
undistorted, 200x200 crop centred near the bore). The default 0.80 circularity rejected it."""
import os

import cv2

from pnpvision.cli import bore_locator
from pnpvision.detect import find_circle

IMG = os.path.join(os.path.dirname(__file__), "data", "up_bore_speck_20261114.png")


def test_bore_with_speck_found():
    img = cv2.imread(IMG)
    assert find_circle(img, 8, 30, polarity="dark", threshold=40) is None   # the old behaviour
    c = bore_locator({})(img)
    assert c is not None
    assert abs(c.center_px[0] - 99.6) < 1.0 and abs(c.center_px[1] - 99.6) < 1.0
    assert 13 < c.radius_px < 17
