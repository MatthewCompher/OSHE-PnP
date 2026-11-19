"""Part heights (needed by the runner for the placement Z).

Where a height comes from, first match wins:
  1. "setting"   - a height you set in pnpslice for that package (saved per board)
  2. "footprint" - a Height field on the footprint in KiCad (e.g. "1.75" or "1.75 mm")
  3. "typical"   - the built-in table below, by KiCad footprint name

The table holds typical body heights for common KiCad library packages. They
are good enough to start with, but check them against your parts' datasheets:
capacitors in particular vary a lot with value.
"""

from __future__ import annotations

import re

# (pattern on the footprint name, height in mm). First match wins, so put
# specific patterns before general ones.
TYPICAL: list[tuple[str, float]] = [
    # chip resistors
    (r"^R_0201_", 0.23), (r"^R_0402_", 0.35), (r"^R_0603_", 0.45), (r"^R_0805_", 0.50),
    (r"^R_1206_", 0.55), (r"^R_1210_", 0.55), (r"^R_2010_", 0.60), (r"^R_2512_", 0.60),
    # MLCC capacitors (typical; high values are taller)
    (r"^C_0201_", 0.30), (r"^C_0402_", 0.50), (r"^C_0603_", 0.80), (r"^C_0805_", 1.25),
    (r"^C_1206_", 1.60),
    # chip LEDs
    (r"^LED_0402_", 0.40), (r"^LED_0603_", 0.75), (r"^LED_0805_", 0.80), (r"^LED_1206_", 1.10),
    # diodes
    (r"^D_SOD-523", 0.70), (r"^D_SOD-323", 1.10), (r"^D_SOD-123", 1.35),
    (r"^D_SMA", 2.30), (r"^D_SMB", 2.40),
    # transistors / small regulators
    (r"^SOT-323|^SC-70", 1.00), (r"^SOT-23", 1.10), (r"^SOT-89", 1.60), (r"^SOT-223", 1.80),
    # ICs
    (r"^SOIC-", 1.75), (r"^SSOP-", 2.00), (r"^TSSOP-", 1.20), (r"^MSOP-", 1.10),
    (r"^LQFP-", 1.60), (r"^TQFP-", 1.20), (r"^(V|W|U)?QFN-", 0.90), (r"^(V|W|U)?DFN-", 0.90),
]
_TYPICAL = [(re.compile(p), h) for p, h in TYPICAL]

# Footprint fields KiCad users commonly put a height in.
FIELD_NAMES = ("height", "height_mm", "height (mm)", "component height", "max height")

_NUM = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*(mm)?\s*$", re.IGNORECASE)


def parse_height(text: str | None) -> float | None:
    """'1.75', '1.75mm', '1.75 mm' -> 1.75. Anything else -> None."""
    if text is None:
        return None
    m = _NUM.match(str(text).replace(",", "."))
    if not m:
        return None
    v = float(m.group(1))
    return v if 0 < v < 50 else None


def typical_height(package: str) -> float | None:
    for rx, h in _TYPICAL:
        if rx.search(package):
            return h
    return None


def footprint_height(properties: dict[str, str]) -> float | None:
    lower = {k.strip().lower(): v for k, v in properties.items()}
    for name in FIELD_NAMES:
        if name in lower:
            h = parse_height(lower[name])
            if h is not None:
                return h
    return None


def resolve_height(package: str, properties: dict[str, str],
                   overrides: dict[str, float] | None = None) -> tuple[float | None, str]:
    """(height_mm or None, source) where source is setting / footprint / typical / missing."""
    if overrides and package in overrides and overrides[package]:
        return float(overrides[package]), "setting"
    h = footprint_height(properties)
    if h is not None:
        return h, "footprint"
    h = typical_height(package)
    if h is not None:
        return h, "typical"
    return None, "missing"


SOURCE_LABELS = {
    "setting": "your setting",
    "footprint": "KiCad footprint field",
    "typical": "typical for package",
    "missing": "unknown",
}