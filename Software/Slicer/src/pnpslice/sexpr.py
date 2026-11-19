"""Minimal S-expression reader for KiCad files (.kicad_pcb, .kicad_mod).

Every list becomes a Node whose ``name`` is its first atom. The rest of the
list is kept, in order, in ``items``: atoms are ``str`` and sublists are
``Node``. Numbers stay as strings; callers convert with ``float()`` where they
expect a number, which keeps this module ignorant of the KiCad schema.
"""

from __future__ import annotations

import re
from typing import Iterator, Union

Item = Union[str, "Node"]

_TOKEN = re.compile(
    r'\s*(?:(?P<open>\()|(?P<close>\))|"(?P<str>(?:[^"\\]|\\.)*)"|(?P<atom>[^\s()"]+))'
)
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"'}


class SExprError(ValueError):
    pass


class Node:
    __slots__ = ("name", "items", "line")

    def __init__(self, name: str, items: list[Item] | None = None, line: int = 0):
        self.name = name
        self.items: list[Item] = items if items is not None else []
        self.line = line  # 1-based line of the opening "(" (for error messages)

    # ---- navigation -----------------------------------------------------
    @property
    def atoms(self) -> list[str]:
        """The non-list items, in order: ``(at 1 2 90)`` -> ['1', '2', '90']."""
        return [i for i in self.items if isinstance(i, str)]

    def nodes(self, name: str | None = None) -> Iterator["Node"]:
        """Direct child lists, optionally only those called ``name``."""
        for i in self.items:
            if isinstance(i, Node) and (name is None or i.name == name):
                yield i

    def node(self, name: str) -> "Node | None":
        """First direct child list called ``name``, or None."""
        return next(self.nodes(name), None)

    def value(self, name: str, default: str | None = None) -> str | None:
        """First atom of the child ``name``: ``(layer "F.Cu")`` -> 'F.Cu'."""
        n = self.node(name)
        if n is None or not n.atoms:
            return default
        return n.atoms[0]

    def floats(self, name: str) -> list[float] | None:
        """All atoms of child ``name`` as floats, or None if absent."""
        n = self.node(name)
        if n is None:
            return None
        return [float(a) for a in n.atoms]

    def __repr__(self) -> str:  # compact, for debugging
        inner = " ".join(i if isinstance(i, str) else f"({i.name} …)" for i in self.items[:6])
        return f"({self.name} {inner}{' …' if len(self.items) > 6 else ''})"


def _unescape(s: str) -> str:
    if "\\" not in s:
        return s
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), s)


def parse(text: str) -> Node:
    """Parse one top-level S-expression and return its root Node."""
    stack: list[Node] = []
    root: Node | None = None
    pos, n = 0, len(text)
    line = 1
    expect_name = False

    while pos < n:
        m = _TOKEN.match(text, pos)
        if m is None:
            if text[pos:].strip() == "":
                break
            raise SExprError(f"unexpected character {text[pos]!r} at line {line}")
        line += text.count("\n", pos, m.end())
        pos = m.end()
        kind = m.lastgroup

        if kind == "open":
            node = Node("", line=line)
            if stack:
                stack[-1].items.append(node)
            elif root is not None:
                raise SExprError(f"more than one top-level expression (line {line})")
            else:
                root = node
            stack.append(node)
            expect_name = True
        elif kind == "close":
            if not stack:
                raise SExprError(f"unbalanced ')' at line {line}")
            stack.pop()
            expect_name = False
        else:
            if not stack:
                raise SExprError(f"atom outside any list at line {line}")
            atom = _unescape(m.group("str")) if kind == "str" else m.group("atom")
            if expect_name:
                stack[-1].name = atom
                expect_name = False
            else:
                stack[-1].items.append(atom)

    if stack:
        raise SExprError(f"file ended with {len(stack)} unclosed '(' (first opened at line {stack[0].line})")
    if root is None:
        raise SExprError("empty file")
    return root