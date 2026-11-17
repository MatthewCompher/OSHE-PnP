"""Excluding parts: kept in the job with "skip": true (JOB_FORMAT.md), never placed."""

from pnpslice.board import load_board_text
from pnpslice.job import build_job, validate_job
from pnpslice.plate import build_plate, build_plates
from pnpslice.project import ProjectSettings
from pnpslice.slicer import slice_plate
from conftest import make_board

BIG = '(gr_rect (start 0 0) (end 100 80) (layer "Edge.Cuts"))'


def res(ref, x, y, uid=None, lib="Resistor_SMD:R_0603_1608Metric"):
    return f"""
  (footprint "{lib}" (layer "F.Cu") (uuid "{uid or 'u-' + ref}") (at {x} {y})
    (property "Reference" "{ref}") (attr smd)
    (pad "1" smd rect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask"))
    (pad "2" smd rect (at 0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask")))"""


def board(*parts):
    b = load_board_text(make_board(BIG + "".join(parts)))
    return b, build_plate(b, "top")


def test_excluded_part_is_kept_with_skip():
    b, plate = board(res("R1", 10, 10), res("R2", 50, 40), res("R3", 90, 70))
    r = slice_plate(b, plate, ProjectSettings(excluded={"u-R2"}))
    assert r.ok
    by_ref = {p.ref: p for p in r.placements}
    assert by_ref["R2"].skip and by_ref["R2"].excluded and by_ref["R2"].skip_reason == "excluded"
    assert not by_ref["R1"].skip
    job = build_job(b, r)
    entries = {e["ref"]: e for e in job["placements"]}
    assert entries["R2"]["skip"] is True
    assert "skip" not in entries["R1"] and "skip" not in entries["R3"]
    assert validate_job(job) == []
    assert any("excluded by you" in i.message for i in r.warnings)


def test_excluded_pads_stay_visible_for_alignment():
    b, plate = board(res("R1", 10, 10), res("R2", 50, 40))
    r = slice_plate(b, plate, ProjectSettings(excluded={"u-R2"}))
    assert all(c.covered_at is None for c in r.align_candidates if c.ref == "R2")
    assert all(c.covered_at is not None for c in r.align_candidates if c.ref == "R1")


def test_everything_excluded_is_an_error():
    b, plate = board(res("R1", 10, 10), res("R2", 50, 40))
    r = slice_plate(b, plate, ProjectSettings(excluded={"u-R1", "u-R2"}))
    assert not r.ok and "every part is excluded" in r.errors[0].message


def test_excluding_an_off_board_part_removes_the_error():
    b, plate = board(res("R1", 10, 10), res("R2", 50, 40), res("R9", 150, 40))
    assert any("outside" in i.message for i in slice_plate(b, plate).errors)
    r = slice_plate(b, plate, ProjectSettings(excluded={"u-R9"}))
    assert r.ok
    assert "R9" not in {p.ref for p in r.placements}         # every entry must be on the board
    assert any("left out" in i.message for i in r.warnings)


def test_excluded_part_with_unknown_height_is_left_out_not_an_error():
    b, plate = board(res("R1", 10, 10), res("R2", 50, 40), res("U1", 70, 40, lib="Mine:Mystery"))
    assert any("No height" in i.message for i in slice_plate(b, plate).errors)
    r = slice_plate(b, plate, ProjectSettings(excluded={"u-U1"}))
    assert r.ok and "U1" not in {p.ref for p in r.placements}


def test_exclusions_survive_reannotation_and_save(tmp_path):
    body = res("R1", 10, 10) + res("R2", 50, 40)
    s = ProjectSettings(excluded={"u-R2"}, path=str(tmp_path / "b.pnpslice.json"))
    s.save()
    loaded = ProjectSettings.load(str(tmp_path / "b.kicad_pcb"))
    assert loaded.excluded == {"u-R2"}
    b = load_board_text(make_board(BIG + body.replace('"R2"', '"R200"')))
    r = slice_plate(b, build_plate(b, "top"), loaded)
    assert {p.ref for p in r.placements if p.skip} == {"R200"}


def test_test_pcb_exclude_a_whole_package(test_board):
    top, bottom = build_plates(test_board)
    soics = {p.key for p in bottom.parts if p.package.startswith("SOIC")}
    r = slice_plate(test_board, bottom, ProjectSettings(auto_number=True, excluded=soics))
    assert r.ok
    assert sum(1 for p in r.placements if p.skip) == 6
    assert validate_job(build_job(test_board, r)) == []