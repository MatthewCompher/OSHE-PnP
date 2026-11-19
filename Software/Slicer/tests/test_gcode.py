"""Dry-run G-code export (pnpslice/gcode.py)."""
from pnpslice.gcode import dryrun_gcode, dryrun_path, write_dryrun_gcode

JOB = {"format": "oshe-pnp-job/1",
       "source": {"generator": "pnpslice 0.1.0", "inputs": ["Test PCB.kicad_pcb"], "date": "2026-11-18"},
       "board": {"name": "Test PCB", "side": "top"},
       "placements": [{"ref": "R1", "package": "R_0603", "x": 1.5, "y": 38.5, "rot": 90},
                      {"ref": "R2", "package": "R_0201", "x": 2, "y": 3, "rot": 0, "skip": True},
                      {"ref": "R3", "package": "R_0603", "x": 10.25, "y": 4.125, "rot": 0}]}


def test_dryrun_gcode_lists_parts_in_order_without_skipped():
    text = dryrun_gcode(JOB)
    moves = [ln for ln in text.splitlines() if ln.startswith("PNP_BOARD_MOVE")]
    assert moves == ["PNP_BOARD_MOVE X=1.5000 Y=38.5000 N=1 REF=R1",
                     "PNP_BOARD_MOVE X=10.2500 Y=4.1250 N=2 REF=R3"]
    code = [ln for ln in text.splitlines() if ln and not ln.startswith(";")]
    assert code[0] == 'PNP_DRYRUN_START JOB="Test PCB-top" PARTS=2'   # first command: safety checks
    assert code[-1] == "PNP_DRYRUN_END"
    assert not any(ln.startswith(("G0", "G1")) for ln in code)        # no raw machine moves


def test_paths_and_file(tmp_path):
    assert dryrun_path("/a/Test PCB-top.job.json") == "/a/Test PCB-top_dryrun.gcode"
    p = write_dryrun_gcode(str(tmp_path / "Test PCB-top.job.json"), JOB)
    assert p.endswith("Test PCB-top_dryrun.gcode")
    assert open(p, encoding="utf-8").read() == dryrun_gcode(JOB)
