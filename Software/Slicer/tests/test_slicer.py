import json

import pytest

from pnpslice.board import load_board_text
from pnpslice.heights import parse_height, resolve_height, typical_height
from pnpslice.job import FORMAT, build_job, dumps, validate_job, write_job, JobError
from pnpslice.plate import build_plate, build_plates
from pnpslice.project import ProjectSettings, settings_path
from pnpslice.slicer import auto_number, slice_plate
from conftest import RECT_OUTLINE, make_board

# ---- heights ------------------------------------------------------------------


@pytest.mark.parametrize("text, h", [("1.75", 1.75), ("1.75mm", 1.75), (" 0,8 mm ", 0.8), ("", None),
                                     ("tall", None), ("0", None), (None, None)])
def test_parse_height(text, h):
    assert parse_height(text) == h


def test_typical_heights():
    assert typical_height("R_0603_1608Metric") == 0.45
    assert typical_height("SOIC-8_3.9x4.9mm_P1.27mm") == 1.75
    assert typical_height("SOT-23-5") == 1.1
    assert typical_height("Mystery_Part") is None


def test_height_precedence():
    props = {"Height": "2.0 mm"}
    assert resolve_height("R_0603_1608Metric", {}, {}) == (0.45, "typical")
    assert resolve_height("R_0603_1608Metric", props, {}) == (2.0, "footprint")
    assert resolve_height("R_0603_1608Metric", props, {"R_0603_1608Metric": 0.5}) == (0.5, "setting")
    assert resolve_height("Mystery", {}, {}) == (None, "missing")


# ---- project settings ------------------------------------------------------


def test_settings_round_trip(tmp_path):
    board = tmp_path / "My Board.kicad_pcb"
    assert settings_path(str(board)).endswith("My Board.pnpslice.json")
    s = ProjectSettings.load(str(board))
    assert s.heights == {} and not s.auto_number
    s.heights["R_0603_1608Metric"] = 0.5
    s.auto_number = True
    s.save()
    s2 = ProjectSettings.load(str(board))
    assert s2.heights == {"R_0603_1608Metric": 0.5} and s2.auto_number


def test_corrupt_settings_fall_back_to_defaults(tmp_path):
    board = tmp_path / "b.kicad_pcb"
    (tmp_path / "b.pnpslice.json").write_text("{not json")
    assert ProjectSettings.load(str(board)).heights == {}


# ---- slicing synthetic boards ---------------------------------------------

PART = """
  (footprint "{lib}" (layer "F.Cu") (at {x} {y} {rot})
    (property "Reference" "{ref}") (property "Value" "v") {extra}
    (attr smd)
    (pad "1" smd rect (at -0.8 0 {rot}) (size 0.8 0.9) (layers "F.Cu" "F.Mask"))
    (pad "2" smd rect (at 0.8 0 {rot}) (size 0.8 0.9) (layers "F.Cu" "F.Mask")))
"""


def part(ref, x, y, lib="Resistor_SMD:R_0603_1608Metric", rot=0, extra=""):
    return PART.format(ref=ref, x=x, y=y, lib=lib, rot=rot, extra=extra)


def board_with(*parts):
    return load_board_text(make_board(RECT_OUTLINE + "".join(parts)))


def errors(result):
    return [i.message for i in result.errors]


def test_clean_board_slices():
    b = board_with(part("R1", 20, 20), part("R2", 30, 30))
    r = slice_plate(b, build_plate(b, "top"))
    assert r.ok, errors(r)
    assert [p.ref for p in r.placements] == ["R1", "R2"] or [p.ref for p in r.placements] == ["R2", "R1"]


def test_duplicates_block_unless_auto_numbered():
    b = board_with(part("R1", 20, 20), part("R1", 30, 30), part("C?", 40, 40, "Capacitor_SMD:C_0603_1608Metric"))
    plate = build_plate(b, "top")
    r = slice_plate(b, plate)
    assert not r.ok
    assert any("share" in m for m in errors(r)) and any("Unnumbered" in m for m in errors(r))
    r = slice_plate(b, plate, ProjectSettings(auto_number=True))
    assert r.ok, errors(r)
    refs = sorted(p.ref for p in r.placements)
    assert refs == ["C_1", "R1_1", "R1_2"]


def test_auto_number_reading_order_and_no_clash():
    b = board_with(part("R1", 40, 20), part("R1", 20, 20), part("R1", 20, 40), part("R1_1", 50, 45))
    plate = build_plate(b, "top")
    new = auto_number(plate.parts)
    by_pos = {(plate.parts[i].footprint.x, plate.parts[i].footprint.y): n for i, n in new.items()}
    # KiCad y=20 is the top row (job y larger): left to right first, then the lower row
    assert by_pos[(20, 20)] == "R1_2"   # R1_1 already exists, so numbering skips it
    assert by_pos[(40, 20)] == "R1_3"
    assert by_pos[(20, 40)] == "R1_4"


def test_missing_height_is_an_error_until_set():
    b = board_with(part("U1", 20, 20, lib="Mine:Weird_Package"))
    plate = build_plate(b, "top")
    r = slice_plate(b, plate)
    assert not r.ok and "No height" in errors(r)[0]
    r = slice_plate(b, plate, ProjectSettings(heights={"Weird_Package": 1.2}))
    assert r.ok and r.placements[0].height == 1.2 and r.placements[0].height_source == "setting"


def test_outside_outline_is_an_error():
    b = board_with(part("R1", 20, 20), part("R2", 70, 20))
    r = slice_plate(b, build_plate(b, "top"))
    assert any("outside the board" in m for m in errors(r))


def test_order_lowest_first_and_grouped_by_package():
    b = board_with(
        part("U1", 15, 15, lib="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"),
        part("R1", 50, 40), part("C1", 20, 20, lib="Capacitor_SMD:C_0805_2012Metric"),
        part("R2", 20, 40), part("R3", 45, 40),
    )
    r = slice_plate(b, build_plate(b, "top"))
    assert r.ok, errors(r)
    pk = [p.part.package for p in r.placements]
    heights = [p.height for p in r.placements]
    assert heights == sorted(heights)
    assert pk[0:3] == ["R_0603_1608Metric"] * 3
    assert pk[-1].startswith("SOIC-8")
    # nearest-neighbour inside the resistor group: from origin -> R2 (nearest), then R3, then R1
    assert [p.ref for p in r.placements[:3]] == ["R2", "R3", "R1"]


def test_no_parts_is_an_error():
    b = board_with(part("R1", 20, 20))
    r = slice_plate(b, build_plate(b, "bottom"))
    assert not r.ok and "no SMD parts" in errors(r)[0]


# ---- job files ---------------------------------------------------------------


def test_job_matches_format_and_validates(tmp_path):
    b = board_with(part("R1", 20, 20, rot=90), part("R2", 30, 30))
    r = slice_plate(b, build_plate(b, "top"))
    job = build_job(b, r)
    assert job["format"] == FORMAT
    assert job["board"]["side"] == "top" and set(job["board"]) == {"name", "side", "outline_mm", "thickness_mm"}
    assert job["source"]["generator"].startswith("pnpslice") and job["source"]["inputs"]
    assert job["board"]["outline_mm"][0] == [0.0, 0.0]
    assert "feeder" not in job["placements"][0] and "nozzle" not in job["placements"][0]
    assert validate_job(job) == []
    assert 2 <= len(job["alignment"]) <= 4
    path = tmp_path / "out.job.json"
    write_job(str(path), job)
    assert json.loads(path.read_text()) == job
    r1 = next(p for p in job["placements"] if p["ref"] == "R1")
    assert (r1["x"], r1["y"], r1["rot"], r1["height_mm"]) == (10.0, 30.0, 90.0, 0.45)


def test_build_job_refuses_errors():
    b = board_with(part("R1", 20, 20), part("R1", 30, 30))
    with pytest.raises(JobError, match="share"):
        build_job(b, slice_plate(b, build_plate(b, "top")))


def test_validator_catches_problems():
    bad = {"format": "x", "board": {"side": "left", "outline_mm": [[1, 1], [2, 2]]},
           "alignment": [{"name": "A", "x": 1, "y": 1, "shape": "hexagon"}], "placements": [
               {"ref": "R1", "value": "v", "package": "p", "x": 1, "y": 1, "rot": 270, "height_mm": 0},
               {"ref": "R1", "x": "a", "y": 1, "rot": 0, "height_mm": 1, "skip": "yes"}]}
    errs = "\n".join(validate_job(bad))
    for frag in ("format", "board.name", "board.side", "outline_mm", "thickness_mm", "rot: must be in",
                 "height_mm", "used more than once", "x: must be a number", "value: must be a string",
                 "shape: must be one of", "needs 2 to 4", "skip: must be"):
        assert frag in errs, frag


def test_spec_example_validates():
    """The example from JOB_FORMAT.md must pass our validator unchanged."""
    example = {
        "format": "oshe-pnp-job/1",
        "source": {"generator": "example", "inputs": ["Test PCB-all-pos.csv", "Test PCB.kicad_pcb"]},
        "board": {"name": "Test PCB", "side": "top",
                  "outline_mm": [[0, 0], [45.0, 0], [45.0, 45.0], [0, 45.0]], "thickness_mm": 1.6},
        "alignment": [
            {"name": "A", "x": 2.50, "y": 3.10, "shape": "rect", "w": 1.0, "h": 1.3, "rot": 0,
             "ref": "J1", "pad": "1"},
            {"name": "B", "x": 41.80, "y": 40.20, "shape": "circle", "d": 1.2},
            {"name": "C", "x": 40.90, "y": 4.00, "shape": "rect", "w": 0.6, "h": 0.9, "rot": 90}],
        "placements": [
            {"ref": "R1", "value": "10k", "package": "R_0603_1608Metric",
             "x": 12.535, "y": 20.000, "rot": 90.0, "height_mm": 0.45, "feeder": "F3"},
            {"ref": "U1", "value": "NE555", "package": "SOIC-8_3.9x4.9mm_P1.27mm",
             "x": 30.000, "y": 15.500, "rot": -90.0, "height_mm": 1.75}],
    }
    assert validate_job(example) == []


# ---- the test board ------------------------------------------------------------


def test_test_pcb_slices_with_auto_number(test_board):
    for plate in build_plates(test_board):
        r = slice_plate(test_board, plate)
        assert not r.ok  # duplicate references
        r = slice_plate(test_board, plate, ProjectSettings(auto_number=True))
        assert r.ok, errors(r)
        job = build_job(test_board, r)
        assert validate_job(job) == []
        assert len(job["placements"]) == len(plate.parts)
        assert len({p["ref"] for p in job["placements"]}) == len(plate.parts)
        hs = [p["height_mm"] for p in job["placements"]]
        assert hs == sorted(hs)
        json.loads(dumps(job))
    bottom = slice_plate(test_board, build_plates(test_board)[1], ProjectSettings(auto_number=True))
    assert bottom.placements[-1].part.package.startswith("SOIC-8")  # tallest last