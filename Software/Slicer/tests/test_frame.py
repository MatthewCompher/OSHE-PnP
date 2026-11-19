import math

import pytest

from pnpslice.board import load_board_text
from pnpslice.frame import Frame, normalize_angle
from pnpslice.plate import build_plate, build_plates
from conftest import RECT_OUTLINE, make_board


@pytest.mark.parametrize("a, expect", [(0, 0), (180, 180), (-180, 180), (270, -90), (-90, -90),
                                       (360, 0), (450, 90), (-0.0, 0), (179.9999999, 180)])
def test_normalize_angle(a, expect):
    assert normalize_angle(a) == pytest.approx(expect)


def _board():
    # Outline (10,10)-(60,50) in KiCad coordinates
    return load_board_text(make_board(RECT_OUTLINE))


def test_top_frame_corners():
    f = Frame.for_board(_board(), "top")
    assert f.point(10, 50) == (0, 0)          # KiCad bottom-left (Y down) = job origin
    assert f.point(60, 10) == (50, 40)        # top-right
    assert f.point(10, 10) == (0, 40)         # top-left stays on the left
    assert f.origin_kicad == (10, 50)


def test_bottom_frame_is_mirrored():
    f = Frame.for_board(_board(), "bottom")
    assert f.point(60, 50) == (0, 0)          # seen from below, KiCad's right edge is on the left
    assert f.point(10, 10) == (50, 40)
    assert f.point(10, 50) == (50, 0)
    assert f.origin_kicad == (60, 50)


@pytest.mark.parametrize("side", ["top", "bottom"])
def test_round_trip(side):
    f = Frame.for_board(_board(), side)
    for p in [(10, 10), (23.4, 41.7), (60, 50)]:
        assert f.to_kicad(*f.point(*p)) == pytest.approx(p)


def test_angles():
    top = Frame.for_board(_board(), "top")
    bot = Frame.for_board(_board(), "bottom")
    assert [top.angle(a) for a in (0, 90, -90, 180)] == [0, 90, -90, 180]
    assert [bot.angle(a) for a in (0, 90, -90, 180, 30)] == [180, 90, -90, 0, 150]


def _rot(x, y, deg):
    a = math.radians(deg)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def test_every_pad_on_test_pcb_matches_rotated_library_footprint(test_board):
    """The real check of position + rotation, both sides.

    Take each pad's position in the *library* footprint (as you'd see it looking
    at the part, +Y up), rotate it by the job angle and add the job position:
    that must land exactly on the pad's job-frame position. On B.Cu KiCad stores
    local coordinates mirrored in Y, so the library position is (lx, -ly) there.
    """
    checked = 0
    for plate in build_plates(test_board):
        for part in plate.parts:
            fp = part.footprint
            copper = fp.copper_pads
            assert len(copper) == len(part.pads)
            for pad, jp in zip(copper, part.pads):
                lib_x, lib_y = (pad.local_x, pad.local_y) if fp.side == "top" else (pad.local_x, -pad.local_y)
                up_x, up_y = lib_x, -lib_y            # library coords with +Y up
                rx, ry = _rot(up_x, up_y, part.rot)
                assert (part.origin[0] + rx, part.origin[1] + ry) == pytest.approx((jp.x, jp.y), abs=1e-6), (
                    f"{plate.side} {part.ref} pad {pad.number}")
                checked += 1
    assert checked == 184 + 164


def test_soic_pin1_seen_from_below(test_board):
    """SOIC-8 on the bottom at KiCad -90: seen from below it is rotated -90
    (clockwise), so pin 1, top-left in the library, ends up upper-right of centre."""
    plate = build_plate(test_board, "bottom")
    soics = [p for p in plate.parts if p.package.startswith("SOIC-8")]
    assert len(soics) == 6
    for s in soics:
        assert s.rot == -90
        pin1 = next(p for p in s.pads if p.number == "1")
        assert pin1.x - s.x == pytest.approx(1.905)
        assert pin1.y - s.y == pytest.approx(2.475)


def test_test_pcb_plates(test_board):
    top, bottom = build_plates(test_board)
    assert (top.number, top.side, len(top.parts)) == (1, "top", 92)
    assert (bottom.number, bottom.side, len(bottom.parts)) == (2, "bottom", 64)
    for plate in (top, bottom):
        assert plate.width == pytest.approx(46.51)
        assert plate.height == pytest.approx(54)
        xs = [x for x, _ in plate.outline]
        ys = [y for _, y in plate.outline]
        assert (min(xs), min(ys)) == pytest.approx((0, 0))
        for part in plate.parts:  # every part inside the board in job coordinates
            assert 0 < part.x < plate.width and 0 < part.y < plate.height
    # the same part sits at mirrored X on the bottom plate's frame
    fp = bottom.parts[0].footprint
    assert bottom.parts[0].x == pytest.approx(88 - fp.x)
    assert bottom.parts[0].y == pytest.approx(95 - fp.y)


def test_skipped_parts_have_reasons():
    body = RECT_OUTLINE + """
      (footprint "A:B" (layer "F.Cu") (at 20 20) (property "Reference" "R1") (attr smd)
        (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")))
      (footprint "A:B" (layer "F.Cu") (at 30 20) (property "Reference" "R2") (attr smd dnp)
        (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")))
      (footprint "A:J" (layer "F.Cu") (at 40 20) (property "Reference" "J1") (attr through_hole)
        (pad "1" thru_hole circle (at 0 0) (size 1.7 1.7) (drill 1) (layers "*.Cu")))
      (footprint "A:L" (layer "F.Cu") (at 50 20) (property "Reference" "G1") (attr board_only))
    """
    plate = build_plate(load_board_text(make_board(body)), "top")
    assert [p.ref for p in plate.placed_parts] == ["R1"]
    assert {fp.ref: why for fp, why in plate.skipped} == {"J1": "through-hole", "G1": "board-only"}
    assert [p.ref for p in plate.parts] == ["R1", "R2"] and plate.parts[1].dnp


# ---- round trip required by the handoff: a known asymmetric footprint -> x, y, rot, both sides

SOT23 = """
  (footprint "Package_TO_SOT_SMD:SOT-23" (layer "{layer}") (uuid "u-q1") (at 30 20 {rot})
    (property "Reference" "Q1") (attr smd)
    (pad "1" smd rect (at -1.1 -0.95 {rot}) (size 1.0 0.6) (layers "{cu}" "{mask}"))
    (pad "2" smd rect (at -1.1 0.95 {rot}) (size 1.0 0.6) (layers "{cu}" "{mask}"))
    (pad "3" smd rect (at 1.1 0 {rot}) (size 1.0 0.6) (layers "{cu}" "{mask}")))
"""


def _sot(side, kicad_rot, local_pin1_y):
    p = "F" if side == "top" else "B"
    body = RECT_OUTLINE + SOT23.format(layer=f"{p}.Cu", cu=f"{p}.Cu", mask=f"{p}.Mask", rot=kicad_rot)
    if side == "bottom":  # KiCad stores flipped footprints mirrored in local Y
        body = body.replace("(at -1.1 -0.95", "(at -1.1 PIN1").replace("(at -1.1 0.95", "(at -1.1 -0.95")
        body = body.replace("PIN1", "0.95")
    return build_plate(load_board_text(make_board(body)), side).parts[0]


def test_round_trip_sot23_top_30deg():
    # Outline (10,10)-(60,50). KiCad (30, 20) -> top job frame (20, 30).
    q = _sot("top", 30, -0.95)
    assert (q.origin, q.rot) == ((20.0, 30.0), 30.0)
    # library pin 1 is at (-1.1, +0.95) with +Y up; rotated 30° CCW:
    c, s_ = math.cos(math.radians(30)), math.sin(math.radians(30))
    ex = (20 + (-1.1 * c - 0.95 * s_), 30 + (-1.1 * s_ + 0.95 * c))
    pin1 = next(p for p in q.pads if p.number == "1")
    assert (pin1.x, pin1.y) == pytest.approx(ex)
    # pick point = centre of the pads' bounding box
    xs = [p.x for p in q.pads]
    ys = [p.y for p in q.pads]
    assert (q.x, q.y) == pytest.approx(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2))


def test_round_trip_sot23_bottom_30deg():
    # Seen from below: KiCad (30, 20) -> (60 - 30, 50 - 20) = (30, 30); rot = 180 - 30 = 150.
    q = _sot("bottom", 30, 0.95)
    assert (q.origin, q.rot) == ((30.0, 30.0), 150.0)
    c, s_ = math.cos(math.radians(150)), math.sin(math.radians(150))
    ex = (30 + (-1.1 * c - 0.95 * s_), 30 + (-1.1 * s_ + 0.95 * c))
    pin1 = next(p for p in q.pads if p.number == "1")
    assert (pin1.x, pin1.y) == pytest.approx(ex)