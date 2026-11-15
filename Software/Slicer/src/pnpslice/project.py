"""Per-board slicer settings, saved next to the board as <board>.pnpslice.json.

Like a slicer project file: your heights and options for this board, so you
don't re-enter them each time. Delete the file to go back to the defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .alignment import DEFAULT_CLEARANCE_MM, DEFAULT_COUNT

FILE_VERSION = 1


def settings_path(board_path: str) -> str:
    stem, _ = os.path.splitext(board_path)
    return stem + ".pnpslice.json"


@dataclass
class ProjectSettings:
    heights: dict[str, float] = field(default_factory=dict)   # package -> mm
    auto_number: bool = False                                 # number duplicate references
    align_count: int = DEFAULT_COUNT                          # 2-4 alignment pads
    align_clearance: float = DEFAULT_CLEARANCE_MM             # look-alike pads must be at least this far away
    alignment: dict[str, list[str]] = field(default_factory=dict)  # side -> pad keys picked by hand
    excluded: set[str] = field(default_factory=set)           # footprint keys you un-included
    path: str | None = None                                   # where it was loaded from / saves to

    @classmethod
    def load(cls, board_path: str) -> "ProjectSettings":
        path = settings_path(board_path)
        s = cls(path=path)
        if not os.path.isfile(path):
            return s
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return s  # unreadable: start from defaults rather than refuse to open the board
        heights = data.get("heights", {})
        if isinstance(heights, dict):
            for k, v in heights.items():
                try:
                    if float(v) > 0:
                        s.heights[str(k)] = float(v)
                except (TypeError, ValueError):
                    pass
        s.auto_number = bool(data.get("auto_number", False))
        try:
            s.align_count = max(2, min(4, int(data.get("align_count", DEFAULT_COUNT))))
        except (TypeError, ValueError):
            pass
        try:
            if "align_clearance_mm" in data:
                c = float(data["align_clearance_mm"])
            elif "align_tolerance_mm" in data:          # milestone-4 files stored ± tolerance
                c = 2 * float(data["align_tolerance_mm"])
            else:
                c = DEFAULT_CLEARANCE_MM
            if 0 < c <= 20:
                s.align_clearance = c
        except (TypeError, ValueError):
            pass
        ex = data.get("excluded", [])
        if isinstance(ex, list):
            s.excluded = {str(k) for k in ex}
        al = data.get("alignment", {})
        if isinstance(al, dict):
            for side in ("top", "bottom"):
                keys = al.get(side)
                if isinstance(keys, list):
                    s.alignment[side] = [str(k) for k in keys][:4]
        return s

    def to_dict(self) -> dict:
        return {"pnpslice_settings": FILE_VERSION,
                "heights": dict(sorted(self.heights.items())),
                "auto_number": self.auto_number,
                "align_count": self.align_count,
                "align_clearance_mm": self.align_clearance,
                "alignment": {k: v for k, v in sorted(self.alignment.items()) if v},
                "excluded": sorted(self.excluded)}

    def save(self) -> None:
        if not self.path:
            raise ValueError("no path to save settings to")
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
            f.write("\n")
        os.replace(tmp, self.path)