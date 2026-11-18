"""report: pick success per package and vision decisions, matched to photos."""
import csv
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pnpvision.eventlog import EventLog
from pnpvision.report import decision, write_report


def test_decisions():
    assert decision({"size_mm": [1.66, 0.9]}, 1) == "PASS"
    assert decision({"reason": "no part found"}, 0) == "EMPTY"
    assert decision({"reason": "no part found (best blob fill 0.40 is not a rectangle)", "fill": 0.40}, 0) == "EMPTY"
    assert decision({"reason": "no part found (best blob fill 0.71 is not a rectangle)", "fill": 0.71}, 0) == "REJECT"
    assert decision({"size_mm": [0.84, 0.82], "reason": "size 0.84x0.82 mm vs expected 1.60x0.80"}, 0) == "EMPTY"
    assert decision({"size_mm": [1.82, 0.59], "reason": "too narrow: 0.59 mm wide vs 0.80 expected (on its side?)"}, 0) == "REJECT"


def test_report_from_a_logged_run(tmp_path):
    import cv2
    db = str(tmp_path / "ev.sqlite")
    t0 = time.time() - 60
    folder = tmp_path / time.strftime("job_%Y%m%d_%H%M%S", time.localtime(t0 - 1))
    folder.mkdir()
    for n in (1, 2, 3):
        cv2.imwrite(str(folder / f"up{n:04d}.png"), np.full((120, 160, 3), 80, np.uint8))
    log = EventLog(db, run_id="r1")
    log.log("inspect", ok=False, ts=t0, reason="no part found")                         # old: no part_id
    log.log("pick", ok=False, ts=t0 + 1, ref="R0603_1", attempt=1)
    log.log("inspect", ok=True, ts=t0 + 2, size_mm=[1.66, 0.9], fill=0.93, angle_deg=0.4)
    log.log("pick", ok=True, ts=t0 + 3, ref="R0603_1", attempt=2)
    log.log("place", ok=True, ts=t0 + 4, ref="R0603_1")
    log.log("inspect", ok=True, ts=t0 + 5, size_mm=[1.65, 0.88], fill=0.95, angle_deg=0.4)
    log.log("pick", ok=True, ts=t0 + 6, ref="R0603_9", attempt=1)
    log.log("place", ok=True, ts=t0 + 7, ref="R0603_9")
    out = tmp_path / "rep"
    text = write_report(db, str(out), base_dir=str(tmp_path))
    assert "0603: 2/3 = 66.7 %" in text
    rows = list(csv.DictReader(open(out / "vision_review.csv", encoding="utf-8")))
    assert [r["decision"] for r in rows] == ["EMPTY", "PASS", "PASS"]
    assert all(r["photo"].endswith(f"up{i + 1:04d}.png") for i, r in enumerate(rows))
    assert (out / "events.csv").exists() and (out / "sheet_r1.jpg").exists()


def test_board_checks_in_the_report(tmp_path):
    import cv2
    from pnpvision.boardcheck import check_footprint
    db = str(tmp_path / "ev.sqlite")
    img = np.zeros((200, 200, 3), np.uint8)
    img[:] = (60, 140, 20)                      # BGR solder-mask green
    assert not check_footprint(img, (100, 100), 59.0)["placed"]
    img[85:115, 75:125] = (30, 30, 30)          # a dark chip over the centre
    assert check_footprint(img, (100, 100), 59.0)["placed"]
    photo = str(tmp_path / "fp.png")
    cv2.imwrite(photo, img)
    log = EventLog(db, run_id="b1")
    log.log("board_check", ok=True, ref="R0603_1", green=0.0, part_id=photo)
    log.log("board_check", ok=False, ref="R0805_1", green=0.98, part_id=photo)
    out = tmp_path / "rep"
    text = write_report(db, str(out), base_dir=str(tmp_path))
    assert "PLACED 1, MISSING 1" in text
    rows = list(csv.DictReader(open(out / "placement_review.csv", encoding="utf-8")))
    assert [r["decision"] for r in rows] == ["PLACED", "MISSING"]
    assert (out / "sheet_board_b1.jpg").exists()
