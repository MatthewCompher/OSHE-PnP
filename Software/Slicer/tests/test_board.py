from collections import Counter

import pytest

from pnpslice.board import BoardError, load_board, load_board_text
from pnpslice.cli import main
from pnpslice.crosscheck import check_against_gerbers
from conftest import RECT_OUTLINE, make_board

TWO_PAD = """
  (footprint "Resistor_SMD:R_0603_1608Metric" (layer "{layer}") (at {x} {y} {rot})
    (property "Reference" "{ref}") (property "Value" "10k")
    (attr smd {extra})
    (pad "1" smd roundrect (at -0.825 0 {rot}) (size 0.8 0.95) (layers "{cu}" "{mask}") (roundrect_rratio 0.25))
    (pad "2" smd roundrect (at 0.825 0 {rot}) (size 0.8 0.95) (layers "{cu}" "{mask}") (roundrect_rratio 0.25))
    (pad "" smd roundrect (at 0 0 {rot}) (size 0.2 0.2) (layers "{paste}")))
"""


def fp(ref="R1", x=30, y=30, rot=0, side="top", extra=""):
    p = "F" if side == "top" else "B"
    return TWO_PAD.format(ref=ref, x=x, y=y, rot=rot, extra=extra, layer=f"{p}.Cu",
                          cu=f"{p}.Cu", mask=f"{p}.Mask", paste=f"{p}.Paste")


def test_footprint_fields():
    b = load_board_text(make_board(RECT_OUTLINE + fp()))
    (f,) = b.footprints
    assert (f.ref, f.value, f.package, f.side, f.mount) == ("R1", "10k", "R_0603_1608Metric", "top", "smd")
    assert len(f.pads) == 3 and len(f.copper_pads) == 2
    assert f.pad_center() == pytest.approx((30, 30))


@pytest.mark.parametrize("rot, expect_pad1", [
    (0, (29.175, 30)),
    (90, (30, 30.825)),      # CCW on screen: local -X swings to screen-down (+Y in KiCad)
    (180, (30.825, 30)),
    (-90, (30, 29.175)),
])
def test_pad_rotation_matches_kicad(rot, expect_pad1):
    (f,) = load_board_text(make_board(RECT_OUTLINE + fp(rot=rot))).footprints
    p1 = f.pads[0]
    assert (p1.x, p1.y) == pytest.approx(expect_pad1)
    assert p1.angle == rot


def test_flags_in_attr_and_as_nodes():
    body = RECT_OUTLINE + fp("R1", extra="exclude_from_pos_files dnp") + fp("R2", x=40)
    b = load_board_text(make_board(body + """
      (footprint "X:Y" (layer "F.Cu") (at 20 20) (property "Reference" "R3") (attr smd) (dnp yes))"""))
    flags = {f.ref: (f.dnp, f.exclude_from_pos) for f in b.footprints}
    assert flags == {"R1": (True, True), "R2": (False, False), "R3": (True, False)}


def test_wildcard_layers_expand():
    body = RECT_OUTLINE + """
      (footprint "Conn:Pin" (layer "F.Cu") (at 20 20) (property "Reference" "J1") (attr through_hole)
        (pad "1" thru_hole circle (at 0 0) (size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask")))"""
    (f,) = load_board_text(make_board(body)).footprints
    assert f.mount == "through_hole"
    assert f.pads[0].copper_sides == ("top", "bottom")


def test_duplicate_and_unannotated_refs():
    body = RECT_OUTLINE + fp("R1") + fp("R1", x=40) + fp("R?", x=50)
    b = load_board_text(make_board(body))
    assert b.duplicate_refs() == {"R1": 2}
    assert b.unannotated_refs() == ["R?"]


def test_old_kicad_rejected():
    with pytest.raises(BoardError, match="KiCad 5"):
        load_board_text(make_board(RECT_OUTLINE, version=20171130))


def test_not_a_board():
    with pytest.raises(BoardError, match="not a KiCad board"):
        load_board_text("(kicad_sch (version 20250114))")


def test_newer_format_warns():
    b = load_board_text(make_board(RECT_OUTLINE, version=20990101))
    assert any("newer than tested" in w for w in b.warnings)


def test_missing_file():
    with pytest.raises(BoardError, match="can't open"):
        load_board("does/not/exist.kicad_pcb")


# ---- the real test board -----------------------------------------------------

def test_test_pcb_contents(test_board):
    assert test_board.generator_version == "10.0"
    sides = Counter(f.side for f in test_board.footprints)
    assert sides == {"top": 92, "bottom": 64}
    assert all(f.mount == "smd" for f in test_board.footprints)
    pkgs = Counter((f.side, f.package) for f in test_board.footprints)
    assert pkgs[("bottom", "SOIC-8_3.9x4.9mm_P1.27mm")] == 6
    assert pkgs[("bottom", "R_1206_3216Metric")] == 30
    assert test_board.duplicate_refs() == {"R0201": 30, "R0402": 30, "R0603": 30,
                                           "R0805": 30, "R1206": 30, "SOIC8": 6}


def test_test_pcb_pads_match_gerbers_both_sides(test_board, test_gerber_dir):
    """Independent proof of rotation + bottom-side handling: every SMD pad we
    compute sits exactly on a pad flash in KiCad's own copper Gerbers."""
    results = check_against_gerbers(test_board, test_gerber_dir)
    by_side = {r.side: r for r in results}
    assert by_side["top"].ok and by_side["top"].matched == 184
    assert by_side["bottom"].ok and by_side["bottom"].matched == 164
    assert max(r.max_error for r in results) < 1e-4


def test_cli_info_flags_duplicates(capsys, test_pcb_path):
    assert main(["info", test_pcb_path]) == 1
    out = capsys.readouterr().out
    assert "Plate 1 - top: 92 parts" in out
    assert "Plate 2 - bottom: 64 parts" in out
    assert "156 parts share 6 reference(s)" in out


def test_cli_check_gerbers(capsys, test_pcb_path, test_gerber_dir):
    assert main(["check-gerbers", test_pcb_path, test_gerber_dir]) == 0