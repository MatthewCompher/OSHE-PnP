"""Measured machine values (written by calibrate-* commands), kept out of hand-edited config."""
import json
import os
from pathlib import Path

DEFAULTS = {
    "down_cam_offset_mm": [0.0, 0.0],  # down-cam optical axis minus nozzle axis, machine XY
    "up_cam_xy_mm": [0.0, 0.0],        # toolhead XY where nozzle axis is over up-cam optical axis
    "up_cam_focus_z": None,             # nozzle Z where the tip is sharp in the up camera (calibration height)
    "grid_view_xyz": None,             # toolhead XYZ that puts the datum grid centred in the down cam
    "up_cam_in_datum_mm": None,         # up-cam axis in DATUM coordinates (recorded by datum --reference)
    "visual_home": None,                # {"xy": toolhead XY with the homing dot centred, + detector settings}
}

def load(path):
    p = Path(path)
    d = dict(DEFAULTS)
    if p.exists():
        d.update(json.loads(p.read_text()))
    return d

def save(path, **updates):
    d = load(path)
    d.update(updates)
    write_json_atomic(path, d)
    return d


def write_json_atomic(path, obj):
    """Write to a temp file, then rename over the old one: a power cut or crash mid-write leaves
    the old file intact instead of a half-written one (calibration is hard to re-measure)."""
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    os.replace(tmp, path)
