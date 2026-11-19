import math

import pytest

from pnpslice.board import BoardError, load_board_text
from conftest import RECT_OUTLINE, make_board


def test_rectangle_from_shuffled_reversed_lines():
    b = load_board_text(make_board(RECT_OUTLINE))
    assert b.outline.bbox == (10, 10, 60, 50)
    assert b.outline.is_rectangle
    assert math.isclose(b.outline.area, 2000)


def test_gr_rect():
    b = load_board_text(make_board('(gr_rect (start 0 0) (end 30 20) (layer "Edge.Cuts"))'))
    assert b.outline.bbox == (0, 0, 30, 20)


def test_rounded_corners_with_arcs():
    r = 2.0
    s = math.sqrt(0.5) * r
    body = f"""
      (gr_line (start 2 0) (end 28 0) (layer "Edge.Cuts"))
      (gr_arc (start 28 0) (mid {30 - r + s} {r - s}) (end 30 2) (layer "Edge.Cuts"))
      (gr_line (start 30 2) (end 30 20) (layer "Edge.Cuts"))
      (gr_line (start 30 20) (end 0 20) (layer "Edge.Cuts"))
      (gr_line (start 0 20) (end 0 2) (layer "Edge.Cuts"))
      (gr_arc (start 0 2) (mid {r - s} {r - s}) (end 2 0) (layer "Edge.Cuts"))
    """
    o = load_board_text(make_board(body)).outline
    x0, y0, x1, y1 = o.bbox
    assert (x0, y0, x1, y1) == pytest.approx((0, 0, 30, 20), abs=1e-6)
    assert not o.is_rectangle
    # area = full rect minus two corner pieces of (r^2 - pi r^2 / 4)
    assert o.area == pytest.approx(600 - 2 * (r * r - math.pi * r * r / 4), abs=0.01)
    # arc stays outside the corner cut: no point beyond the box
    assert all(0 - 1e-9 <= x <= 30 + 1e-9 and -1e-9 <= y <= 20 + 1e-9 for x, y in o.outer)


def test_circle_board_and_cutout():
    body = """
      (gr_circle (center 50 50) (end 70 50) (layer "Edge.Cuts"))
      (gr_rect (start 45 45) (end 55 55) (layer "Edge.Cuts"))
    """
    o = load_board_text(make_board(body)).outline
    assert o.width == pytest.approx(40, abs=0.01)
    assert len(o.holes) == 1
    assert not o.contains(50, 50)       # in the cut-out
    assert o.contains(35, 50)           # on the board
    assert not o.contains(80, 50)       # off the board


def test_poly_outline():
    body = '(gr_poly (pts (xy 0 0) (xy 40 0) (xy 40 30) (xy 0 30)) (layer "Edge.Cuts"))'
    assert load_board_text(make_board(body)).outline.bbox == (0, 0, 40, 30)


def test_small_gap_within_tolerance_is_joined():
    body = RECT_OUTLINE.replace("(start 10 50) (end 10 10)", "(start 10 50) (end 10 10.005)")
    load_board_text(make_board(body))  # 5 um gap: fine


def test_open_outline_reports_location():
    body = RECT_OUTLINE.replace("(start 10 50) (end 10 10)", "(start 10 50) (end 10 12)")
    with pytest.raises(BoardError, match="not closed"):
        load_board_text(make_board(body))


def test_no_outline():
    with pytest.raises(BoardError, match="no outline"):
        load_board_text(make_board(""))


def test_non_edge_layers_ignored():
    body = RECT_OUTLINE + '(gr_rect (start 0 0) (end 500 500) (layer "F.SilkS"))'
    assert load_board_text(make_board(body)).outline.bbox == (10, 10, 60, 50)


def test_edge_cuts_inside_footprint_is_transformed():
    # Footprint at (20, 20) rotated 90: local (5, 0) -> board (20, 15)
    body = RECT_OUTLINE + """
      (footprint "Slot" (layer "F.Cu") (at 20 20 90)
        (property "Reference" "H1")
        (fp_rect (start -5 -1) (end 5 1) (layer "Edge.Cuts")))
    """
    o = load_board_text(make_board(body)).outline
    assert len(o.holes) == 1
    hx0, hy0, hx1, hy1 = (min(p[0] for p in o.holes[0]), min(p[1] for p in o.holes[0]),
                          max(p[0] for p in o.holes[0]), max(p[1] for p in o.holes[0]))
    assert (hx0, hy0, hx1, hy1) == pytest.approx((19, 15, 21, 25))


def test_test_pcb_outline(test_board):
    o = test_board.outline
    assert o.bbox == (41.49, 41, 88, 95)
    assert o.is_rectangle
    assert o.width == pytest.approx(46.51)
    assert o.height == pytest.approx(54)