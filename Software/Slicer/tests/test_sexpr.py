import pytest

from pnpslice.sexpr import SExprError, parse


def test_basic_structure():
    root = parse('(kicad_pcb (version 20260206) (at 1.5 -2 90) (layers "F.Cu" "B.Mask"))')
    assert root.name == "kicad_pcb"
    assert root.value("version") == "20260206"
    assert root.floats("at") == [1.5, -2.0, 90.0]
    assert root.node("layers").atoms == ["F.Cu", "B.Mask"]
    assert root.node("missing") is None
    assert root.value("missing", "dflt") == "dflt"


def test_strings_with_parens_spaces_and_escapes():
    root = parse(r'(x (property "Ref (top)" "a \"quoted\" \\ word") (y ""))')
    p = root.node("property")
    assert p.atoms == ["Ref (top)", 'a "quoted" \\ word']
    assert root.node("y").atoms == [""]


def test_multiline_and_order_preserved():
    root = parse("(pts\n  (xy 0 0)\n  (arc (start 1 1) (mid 2 2) (end 3 1))\n  (xy 4 4))")
    assert [n.name for n in root.nodes()] == ["xy", "arc", "xy"]
    assert root.node("arc").line == 3


@pytest.mark.parametrize("bad", ["(a (b)", "(a))", "", "a", "(a) (b)"])
def test_malformed(bad):
    with pytest.raises(SExprError):
        parse(bad)