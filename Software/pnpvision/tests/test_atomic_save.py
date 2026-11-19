"""Calibration files are written to a temp file and renamed (no half-written machine.json)."""
import json

from pnpvision import machine_state as MS


def test_save_is_atomic_and_keeps_old_on_failure(tmp_path, monkeypatch):
    p = tmp_path / "machine.json"
    MS.save(p, down_cam_offset_mm=[1.0, 2.0])
    assert json.loads(p.read_text())["down_cam_offset_mm"] == [1.0, 2.0]
    assert not (tmp_path / "machine.json.tmp").exists()

    def boom(*a, **k):
        raise OSError("power cut")
    monkeypatch.setattr(MS.os, "replace", boom)
    try:
        MS.save(p, down_cam_offset_mm=[9.0, 9.0])
    except OSError:
        pass
    assert json.loads(p.read_text())["down_cam_offset_mm"] == [1.0, 2.0]   # old file intact
