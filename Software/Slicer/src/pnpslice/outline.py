"""Board outline from the Edge.Cuts layer.

Collects every Edge.Cuts shape (board-level ``gr_*`` and footprint-level
``fp_*``), turns arcs/circles/curves into polylines, and chains the open
pieces into closed loops. The loop with the largest area is the board edge;
the others are cut-outs.

Coordinates here are still KiCad's (Y down, page origin). The job frame
(lower-left origin, Y up, mirrored for the bottom side) is applied later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import geometry as g
from .geometry import Point
from .sexpr import Node

EDGE_LAYER = "Edge.Cuts"
DEFAULT_CHAIN_TOL = 0.01  # mm; gaps smaller than this are treated as joined


class OutlineError(ValueError):
    pass


@dataclass
class Outline:
    outer: list[Point]                       # closed polygon, first point not repeated
    holes: list[list[Point]] = field(default_factory=list)
    extra: list[list[Point]] = field(default_factory=list)  # loops outside the outer edge

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        """(min_x, min_y, max_x, max_y) in KiCad coordinates."""
        return g.bbox(self.outer)

    @property
    def width(self) -> float:
        x0, _, x1, _ = self.bbox
        return x1 - x0

    @property
    def height(self) -> float:
        _, y0, _, y1 = self.bbox
        return y1 - y0

    @property
    def area(self) -> float:
        return abs(g.polygon_area(self.outer)) - sum(abs(g.polygon_area(h)) for h in self.holes)

    @property
    def is_rectangle(self) -> bool:
        x0, y0, x1, y1 = self.bbox
        return abs(self.area - (x1 - x0) * (y1 - y0)) < 1e-3 and not self.holes

    def contains(self, x: float, y: float) -> bool:
        """True if (x, y) is on the board: inside the edge and not in a cut-out."""
        if not g.point_in_polygon(x, y, self.outer):
            return False
        return not any(g.point_in_polygon(x, y, h) for h in self.holes)


# ---------------------------------------------------------------------------
# shape extraction


def _xy(node: Node | None, what: str, where: Node) -> Point:
    if node is None or len(node.atoms) < 2:
        raise OutlineError(f"Edge.Cuts {where.name} at line {where.line} has no '{what}'")
    return float(node.atoms[0]), float(node.atoms[1])


def _poly_points(pts: Node, tol: float) -> list[Point]:
    out: list[Point] = []
    for item in pts.nodes():
        if item.name == "xy":
            out.append((float(item.atoms[0]), float(item.atoms[1])))
        elif item.name == "arc":  # arcs inside polygons (KiCad 7+)
            arc = g.arc_points(_xy(item.node("start"), "start", item), _xy(item.node("mid"), "mid", item),
                               _xy(item.node("end"), "end", item), tol)
            if out and g.dist(out[-1], arc[0]) < 1e-9:
                arc = arc[1:]
            out.extend(arc)
    return out


def shape_to_paths(node: Node, tol: float = 0.005) -> tuple[list[list[Point]], list[list[Point]]]:
    """Return (open_paths, closed_loops) for one graphic item, in its own coordinates."""
    kind = node.name.split("_", 1)[-1]  # gr_line / fp_line -> line
    if kind == "line":
        return [[_xy(node.node("start"), "start", node), _xy(node.node("end"), "end", node)]], []
    if kind == "arc":
        if node.node("mid") is None:
            raise OutlineError(f"old-style arc at line {node.line}; re-save the board in KiCad 6 or newer")
        return [g.arc_points(_xy(node.node("start"), "start", node), _xy(node.node("mid"), "mid", node),
                             _xy(node.node("end"), "end", node), tol)], []
    if kind == "circle":
        c = _xy(node.node("center"), "center", node)
        e = _xy(node.node("end"), "end", node)
        return [], [g.circle_points(c, g.dist(c, e), tol)]
    if kind == "rect":
        (x0, y0), (x1, y1) = _xy(node.node("start"), "start", node), _xy(node.node("end"), "end", node)
        return [], [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]
    if kind == "poly":
        pts_node = node.node("pts")
        pts = _poly_points(pts_node, tol) if pts_node is not None else []
        if len(pts) >= 2 and g.dist(pts[0], pts[-1]) < 1e-9:
            pts = pts[:-1]
        return ([], [pts]) if len(pts) >= 3 else ([], [])
    if kind in ("curve", "bezier"):
        pts_node = node.node("pts")
        cps = [p for p in _poly_points(pts_node, tol)] if pts_node is not None else []
        if len(cps) != 4:
            raise OutlineError(f"Bezier on Edge.Cuts at line {node.line} doesn't have 4 control points")
        return [g.bezier_points(*cps)], []
    return [], []  # text, dimensions, etc. are not part of the edge


def _on_edge(node: Node) -> bool:
    if node.value("layer") == EDGE_LAYER:
        return True
    layers = node.node("layers")
    return layers is not None and EDGE_LAYER in layers.atoms


_SHAPES = {"line", "arc", "circle", "rect", "poly", "curve", "bezier"}


def collect_edge_paths(root: Node, fp_transform: Callable[[Node], Callable[[float, float], Point]],
                       tol: float = 0.005) -> tuple[list[list[Point]], list[list[Point]]]:
    """All Edge.Cuts paths on the board, in board coordinates."""
    open_paths: list[list[Point]] = []
    loops: list[list[Point]] = []

    for node in root.nodes():
        if node.name.startswith("gr_") and node.name[3:] in _SHAPES and _on_edge(node):
            o, c = shape_to_paths(node, tol)
            open_paths += o
            loops += c

    for fp in root.nodes("footprint"):
        to_board = fp_transform(fp)
        for node in fp.nodes():
            if node.name.startswith("fp_") and node.name[3:] in _SHAPES and _on_edge(node):
                o, c = shape_to_paths(node, tol)
                open_paths += [[to_board(*p) for p in path] for path in o]
                loops += [[to_board(*p) for p in loop] for loop in c]

    return open_paths, loops


# ---------------------------------------------------------------------------
# chaining


def chain_paths(paths: list[list[Point]], tol: float = DEFAULT_CHAIN_TOL) -> list[list[Point]]:
    """Join open polylines end-to-end into closed loops.

    Raises OutlineError naming the loose end if something doesn't close.
    """
    pending = [list(p) for p in paths if len(p) >= 2]
    loops: list[list[Point]] = []

    while pending:
        chain = pending.pop(0)
        while True:
            if len(chain) > 2 and g.dist(chain[0], chain[-1]) <= tol:
                loops.append(chain[:-1])
                break
            # Candidate joins: (gap, index, how). "end"/"end_rev" append to the
            # chain's tail; "start"/"start_rev" prepend to its head.
            best = None
            for i, p in enumerate(pending):
                for gap, how in (
                    (g.dist(chain[-1], p[0]), "end"),
                    (g.dist(chain[-1], p[-1]), "end_rev"),
                    (g.dist(chain[0], p[-1]), "start"),
                    (g.dist(chain[0], p[0]), "start_rev"),
                ):
                    if gap <= tol and (best is None or gap < best[0]):
                        best = (gap, i, how)
            if best is None:
                a, b = chain[0], chain[-1]
                raise OutlineError(
                    "board outline (Edge.Cuts) is not closed: there is a gap near "
                    f"({b[0]:.3f}, {b[1]:.3f}) / ({a[0]:.3f}, {a[1]:.3f}) in KiCad coordinates. "
                    "Run DRC in KiCad to find it."
                )
            _, i, how = best
            p = pending.pop(i)
            if how == "end":
                chain.extend(p[1:])
            elif how == "end_rev":
                chain.extend(p[::-1][1:])
            elif how == "start":
                chain[:0] = p[:-1]
            else:  # start_rev
                chain[:0] = p[::-1][:-1]
    return loops


def build_outline(open_paths: list[list[Point]], loops: list[list[Point]],
                  chain_tol: float = DEFAULT_CHAIN_TOL) -> Outline:
    all_loops = [l for l in loops + chain_paths(open_paths, chain_tol) if len(l) >= 3]
    if not all_loops:
        raise OutlineError("the board has no outline: draw it on the Edge.Cuts layer in KiCad")
    all_loops.sort(key=lambda l: abs(g.polygon_area(l)), reverse=True)
    outer, rest = all_loops[0], all_loops[1:]
    holes, extra = [], []
    for loop in rest:
        (holes if g.point_in_polygon(*loop[0], outer) else extra).append(loop)
    return Outline(outer=outer, holes=holes, extra=extra)