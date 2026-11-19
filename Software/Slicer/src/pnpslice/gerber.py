"""Just enough of a Gerber (RS-274X) reader to cross-check pad positions.

It collects flashes (D03) and the aperture function each one uses. KiCad
flashes every normal pad at its centre, so the SMD-pad flashes on a copper
layer are an independent record of where the pads are. Gerbers are in the
same place as the board file but with +Y up, so KiCad (x, y) = Gerber (x, -y)
(unless the Gerbers were plotted with the drill/aux origin; see ``offset``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_FS = re.compile(r"%FS[LT]?A?X(\d)(\d)Y(\d)(\d)\*%")
_AD = re.compile(r"%ADD(\d+)")
_TA_FUNC = re.compile(r"%TA\.AperFunction,([^*,]+)")
_COORD = re.compile(r"(?:X(?P<x>[+-]?\d+))?(?:Y(?P<y>[+-]?\d+))?(?:I[+-]?\d+)?(?:J[+-]?\d+)?D0?(?P<d>[123])\*")
_SELECT = re.compile(r"^(?:G54)?D(\d{2,})\*$")


@dataclass
class Flash:
    x: float          # mm, Gerber frame (+Y up)
    y: float
    aperture: int
    function: str     # e.g. "SMDPad,CuDef", "ViaPad", "" if not stated


@dataclass
class GerberFile:
    path: str
    file_function: str
    flashes: list[Flash]

    def pad_flashes(self) -> list[Flash]:
        """Flashes whose aperture is marked as an SMD or component pad."""
        return [f for f in self.flashes if f.function.startswith(("SMDPad", "ComponentPad"))]


def read_gerber(path: str) -> GerberFile:
    with open(path, encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    int_x, dec_x, int_y, dec_y = 4, 6, 4, 6
    scale = 1.0  # mm
    m = _FS.search(text)
    if m:
        dec_x, dec_y = int(m.group(2)), int(m.group(4))
    if "%MOIN*%" in text:
        scale = 25.4

    file_function = ""
    ff = re.search(r"%TF\.FileFunction,([^*]+)\*%", text)
    if ff:
        file_function = ff.group(1)

    ap_function: dict[int, str] = {}
    pending_function = ""
    current_ap = -1
    x = y = 0
    flashes: list[Flash] = []

    for raw in re.split(r"\n", text):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("%TA.AperFunction"):
            fm = _TA_FUNC.match(line)
            full = line[len("%TA.AperFunction,"):].rstrip("*%")
            pending_function = full if fm else ""
            continue
        if line.startswith("%TD"):
            pending_function = ""
            continue
        ad = _AD.match(line)
        if ad:
            ap_function[int(ad.group(1))] = pending_function
            continue
        if line.startswith("%") or line.startswith("G04"):
            continue
        sel = _SELECT.match(line)
        if sel:
            current_ap = int(sel.group(1))
            continue
        body = re.sub(r"^G0?[123]", "", line)
        cm = _COORD.search(body)
        if cm:
            if cm.group("x") is not None:
                x = int(cm.group("x"))
            if cm.group("y") is not None:
                y = int(cm.group("y"))
            if cm.group("d") == "3":
                flashes.append(Flash(x / 10**dec_x * scale, y / 10**dec_y * scale,
                                     current_ap, ap_function.get(current_ap, "")))
    return GerberFile(path=path, file_function=file_function, flashes=flashes)