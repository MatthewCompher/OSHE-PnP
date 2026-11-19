"""Package and nozzle-tip tables for the job runner.

PACKAGE: what the up camera should see and how the part may be turned.
  body_mm   (long, short) body seen from below, for the size check
  axis_deg  machine angle of the body's LONG axis when the footprint is at job rot 0
            (KiCad chips: pads along X -> 0; SOIC: pin rows along Y -> body long axis along Y -> 90)
  symmetric True = looks the same turned 180 deg (chips): any of the two ways is fine
            False = has a pin 1: the coarse turn comes from the feeder's tape_angle_deg and the
            up camera only fine-corrects (within +-MAX_FINE_DEG)
  tip       nozzle tip that handles it
Overrides / additions: config.toml [packages."<name>"] with the same keys.

TIP (Samsung CP40 tips; calibration/machine.json "tips": {name: {...}}, written by
`tip NAME --board-touch-z Z --inspect-z Z`):
  board_touch_z  Z where this tip touches the bare board top (sets place Z: minus part height)
  inspect_z      Z with a part on this tip in focus over the up camera
  Feeders store part_top_z for the tip they were taught with ("teach_tip"); another tip shifts
  that by the difference in board_touch_z (= the difference in tip length).
"""
import re

# Body sizes from typical datasheets (Murata/Yageo). Tips: CP40 names ~ tip size in mm (N045 0.45,
# N08 0.8, N14 1.4, N24 2.4, N400 4.0, N750 7.5). N08 placed 0805 fine on 2026-11-11, so it does
# 0402-0805 (fewer swaps); N045 for 0201; N24 for SOIC-8. Verify the small/large ends on the machine.
DEFAULT_PACKAGES = {
    "R_0201_0603Metric": dict(body_mm=(0.6, 0.3), axis_deg=0.0, symmetric=True, tip="N045"),
    "C_0201_0603Metric": dict(body_mm=(0.6, 0.3), axis_deg=0.0, symmetric=True, tip="N045"),
    "R_0402_1005Metric": dict(body_mm=(1.0, 0.5), axis_deg=0.0, symmetric=True, tip="N08"),
    "C_0402_1005Metric": dict(body_mm=(1.0, 0.5), axis_deg=0.0, symmetric=True, tip="N08"),
    "R_0603_1608Metric": dict(body_mm=(1.6, 0.8), axis_deg=0.0, symmetric=True, tip="N08"),
    "C_0603_1608Metric": dict(body_mm=(1.6, 0.8), axis_deg=0.0, symmetric=True, tip="N08"),
    "R_0805_2012Metric": dict(body_mm=(2.0, 1.25), axis_deg=0.0, symmetric=True, tip="N08"),
    "C_0805_2012Metric": dict(body_mm=(2.0, 1.25), axis_deg=0.0, symmetric=True, tip="N08"),
    "R_1206_3216Metric": dict(body_mm=(3.2, 1.6), axis_deg=0.0, symmetric=True, tip="N14"),
    "C_1206_3216Metric": dict(body_mm=(3.2, 1.6), axis_deg=0.0, symmetric=True, tip="N14"),
    # body only (the leads are thin and dark from below); 4.9 x 3.9 mm
    "SOIC-8_3.9x4.9mm_P1.27mm": dict(body_mm=(4.9, 3.9), axis_deg=90.0, symmetric=False, tip="N24"),
}
MAX_FINE_DEG = 15.0


class PackageError(KeyError):
    pass


def package_info(name, overrides=None):
    d = dict(DEFAULT_PACKAGES.get(name, {}))
    if overrides and name in overrides:
        d.update(overrides[name])
    if not d:
        # unknown chip resistor/capacitor naming: R_xxxx_yyyyMetric
        m = re.match(r"^[RCL]_(\d{4})_(\d{2})(\d{2})Metric", name)
        if m:
            d = dict(body_mm=(int(m.group(2)) / 10, int(m.group(3)) / 10), axis_deg=0.0,
                     symmetric=True, tip=None)
    if not d:
        raise PackageError(f"package {name!r} unknown: add it to config.toml [packages]")
    d["body_mm"] = tuple(d["body_mm"])
    # chip resistors: white underside, black top -> the up camera can tell upside down.
    # Capacitors look the same on both sides: no check.
    d.setdefault("flip_check", name.startswith("R_"))
    return d


def tip_for(placement, pkg):
    return placement.get("nozzle") or pkg.get("tip")


def feeder_part_top_z(feeder_d, tip_name, tips):
    """part_top_z of a feeder taught with one tip, converted to another tip."""
    z = float(feeder_d["part_top_z"])
    taught = feeder_d.get("teach_tip")
    if taught and taught != tip_name and taught in tips and tip_name in tips:
        z += tips[tip_name]["board_touch_z"] - tips[taught]["board_touch_z"]
    return z
