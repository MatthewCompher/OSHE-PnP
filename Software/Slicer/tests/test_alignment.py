import math

import pytest

from pnpslice.alignment import auto_pick, candidates, name_picks, spread
from pnpslice.board import load_board_text
from pnpslice.job import build_job, validate_job
from pnpslice.plate import build_plate, build_plates
from pnpslice.project import ProjectSettings
from pnpslice.slicer import slice_plate
from conftest import make_board

BIG = """
  (gr_rect (start 0 0) (end 100 80) (layer "Edge.Cuts"))
"""


def res(ref, x, y, side="F", rot=0, uid=None):
    uid = uid or f"uuid-{ref}"
    return f"""
  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "{side}.Cu") (uuid "{uid}") (at {x} {y} {rot})
    (property "Reference" "{ref}") (attr smd)
    (pad "1" smd rect (at -0.825 0 {rot}) (size 0.8 0.95) (layers "{side}.Cu" "{side}.Mask"))
    (pad "2" smd rect (at 0.825 0 {rot}) (size 0.8 0.95) (layers "{side}.Cu" "{side}.Mask")))"""


def fid(ref, x, y):
    return f"""
  (footprint "Fiducial:Fiducial_1mm_Mask2mm" (layer "F.Cu") (uuid "uuid-{ref}") (at {x} {y})
    (property "Reference" "{ref}") (attr smd exclude_from_pos_files exclude_from_bom)
    (pad "" smd circle (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask")))"""


def tht(ref, x, y):
    return f"""
  (footprint "Connector:Pin" (layer "F.Cu") (uuid "uuid-{ref}") (at {x} {y})
    (property "Reference" "{ref}") (attr through_hole)
    (pad "1" thru_hole circle (at 0 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask")))"""


def grid_of_resistors(n=4):
    return "".join(res(f"R{i * n + j + 1}", 10 + 25 * i, 10 + 20 * j) for i in range(n) for j in range(n))


def run(body, side="top", **kw):
    b = load_board_text(make_board(body))
    plate = build_plate(b, side)
    return b, plate, slice_plate(b, plate, ProjectSettings(**kw))


def test_fiducials_preferred_and_spread():
    body = BIG + grid_of_resistors() + fid("FID1", 3, 77) + fid("FID2", 97, 77) + fid("FID3", 97, 3)
    b, plate, r = run(body)
    assert r.ok
    assert sorted(a.cand.ref for a in r.alignment) == ["FID1", "FID2", "FID3"]
    assert not any("covered" in i.message for i in r.issues)   # fiducials are never covered
    assert [a.name for a in r.alignment] == ["A", "B", "C"]
    # A is the one nearest the origin: KiCad (3, 77) -> job (3, 80 - 77) = (3, 3)
    a = r.alignment[0].cand
    assert (a.ref, round(a.x), round(a.y)) == ("FID1", 3, 3)


def test_lookalike_pads_not_distinct_at_spec_clearance():
    body = BIG + grid_of_resistors()
    b, plate, r = run(body)          # 0603 twins are 1.65 mm apart < 3 mm (JOB_FORMAT.md)
    assert r.ok
    assert any("look-alike" in i.message for i in r.warnings)
    b, plate, r = run(body, align_clearance=1.5)   # 1.65 >= 1.5
    assert not any("look-alike" in i.message for i in r.warnings)


def test_through_hole_pads_count_on_both_sides_and_stay_visible():
    body = BIG + res("R1", 50, 40, side="B") + tht("J1", 5, 5) + tht("J2", 95, 75) + tht("J3", 95, 5)
    b, plate, r = run(body, side="bottom")
    refs = {a.cand.ref for a in r.alignment}
    assert {"J1", "J2", "J3"} <= refs | {"R1"} and len(refs & {"J1", "J2", "J3"}) >= 2
    assert all(a.cand.covered_at is None for a in r.alignment if a.cand.ref.startswith("J"))


def test_mask_needed_and_side_respected():
    covered = """
  (footprint "X:Y" (layer "F.Cu") (uuid "u-x") (at 50 40) (property "Reference" "TP1") (attr smd)
    (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")))"""
    body = BIG + res("R1", 20, 20) + covered
    b = load_board_text(make_board(body))
    keys = {c.ref for c in candidates(b, build_plate(b, "top"))}
    assert keys == {"R1"}                                    # TP1 has no mask opening
    assert candidates(b, build_plate(b, "bottom")) == []     # nothing exposed on the bottom


def test_too_few_pads_is_an_error():
    body = BIG + """
  (footprint "X:Y" (layer "F.Cu") (uuid "u1") (at 50 40) (property "Reference" "U1") (attr smd)
    (property "Height" "1")
    (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu" "F.Mask")))"""
    b, plate, r = run(body)
    assert not r.ok and any("Fewer than 2" in m.message for m in r.errors)


def test_avoids_collinear_sets():
    # pads along one line plus one off it: a 3-pad set must use the off-line pad
    body = BIG + "".join(res(f"R{i}", 10 + 20 * i, 40) for i in range(5)) + res("R9", 50, 75)
    b, plate, r = run(body, align_count=3)
    assert "R9" in {a.cand.ref for a in r.alignment}
    assert spread([(a.cand.x, a.cand.y) for a in r.alignment], plate.width, plate.height) > 0.08


def test_count_setting():
    body = BIG + grid_of_resistors()
    for n in (2, 3, 4):
        b, plate, r = run(body, align_count=n, align_clearance=1.5)
        assert len(r.alignment) == n
    # spec shape names
    assert {a.cand.job_shape for a in r.alignment} <= {"rect", "roundrect", "oval", "circle"}


def test_manual_picks_used_and_survive_reannotation():
    body = BIG + grid_of_resistors()
    b, plate, r = run(body, align_clearance=1.5)
    keys = [c.key for c in r.align_candidates if c.ref in ("R1", "R16")]
    keys = [k for k in keys if k.endswith("/1")]
    settings = ProjectSettings(align_clearance=1.5, alignment={"top": keys})
    r2 = slice_plate(b, plate, settings)
    assert r2.align_manual and {a.cand.ref for a in r2.alignment} == {"R1", "R16"}
    # rename every part: keys use the footprint uuid, so picks still resolve
    b2 = load_board_text(make_board(body.replace('"R1"', '"R101"').replace('"R16"', '"R116"')))
    r3 = slice_plate(b2, build_plate(b2, "top"), settings)
    assert r3.align_manual and {a.cand.ref for a in r3.alignment} == {"R101", "R116"}


def test_stale_manual_picks_fall_back_to_auto():
    body = BIG + grid_of_resistors()
    b, plate, r = run(body, alignment={"top": ["gone/1", "missing/2"]})
    assert not r.align_manual and len(r.alignment) == 3
    assert any("aren't on the board" in i.message for i in r.warnings)


def test_dnp_parts_skip_and_keep_pads_visible():
    dnp = """
  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "F.Cu") (uuid "u-dnp") (at 90 70)
    (property "Reference" "R99") (attr smd dnp)
    (pad "1" smd rect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask"))
    (pad "2" smd rect (at 0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask")))"""
    b, plate, r = run(BIG + res("R1", 10, 10) + res("R2", 50, 40) + dnp)
    assert r.ok
    by_ref = {p.ref: p for p in r.placements}
    assert by_ref["R99"].skip and not by_ref["R1"].skip
    job = build_job(b, r)
    r99 = next(p for p in job["placements"] if p["ref"] == "R99")
    assert r99["skip"] is True and "skip" not in job["placements"][0] or job["placements"][0]["ref"] == "R99"
    # a DNP part never covers its pads
    assert all(c.covered_at is None for c in r.align_candidates if c.ref == "R99")
    assert validate_job(job) == []


def test_job_alignment_entries():
    body = BIG + grid_of_resistors() + fid("FID1", 3, 77) + fid("FID2", 97, 77) + fid("FID3", 97, 3)
    b, plate, r = run(body)
    job = build_job(b, r)
    assert validate_job(job) == []
    for a in job["alignment"]:
        assert a["shape"] == "circle" and a["d"] == 1.0 and a["ref"].startswith("FID")


def test_test_pcb_alignment(test_board):
    top, bottom = build_plates(test_board)
    r = slice_plate(test_board, bottom, ProjectSettings(auto_number=True))
    assert len(r.alignment) == 3
    # 1206 pads have their twin 2.92 mm away: just under the spec's 3 mm, so a warning
    assert not any(a.cand.distinct(3.0) for a in r.alignment)
    assert any("look-alike" in i.message for i in r.warnings)
    assert spread([(a.cand.x, a.cand.y) for a in r.alignment], bottom.width, bottom.height) > 0.4
    assert all(a.cand.ref.startswith("R1206_") for a in r.alignment)   # job names, not KiCad's
    r = slice_plate(test_board, top, ProjectSettings(auto_number=True))
    assert len(r.alignment) == 3 and any("look-alike" in i.message for i in r.warnings)