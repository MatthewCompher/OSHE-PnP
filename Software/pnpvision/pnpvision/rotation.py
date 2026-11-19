"""Nozzle rotation through Klipper's [manual_stepper stepper_r] (rotation_distance 360: 1 unit =
1 degree; G28 sets it to 0).

Part angles are MACHINE-FRAME angles of the part's long axis, as the cameras report them through
their motion maps (UpCam.inspect and MotionMap.direction_mm): degrees from machine +X toward +Y,
mod 180 for symmetric chips. `direction` = part angle change per motor degree; measured
2026-11-11: motor +30 -> part -29.2, -29.5 (so -1).

Turning the nozzle turns the part about the nozzle axis, so an off-centre part's offset turns
with it (rotate_xy). The tip's runout was measured at ~0.02 mm radius (2026-11-11), so the axis
is taken as the up camera's crosshair.
"""
import numpy as np


def shortest_turn(target_deg, measured_deg, symmetry_deg=180.0):
    """Part rotation (deg, in (-symmetry/2, symmetry/2]) that brings measured to target."""
    d = (float(target_deg) - float(measured_deg)) % symmetry_deg
    return d - symmetry_deg if d > symmetry_deg / 2 else d


def rotate_xy(v, deg):
    a = np.radians(deg)
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s], [s, c]]) @ np.asarray(v, float)


class Rotator:
    """Tracks the motor angle in software (absolute MOVE from the G28 zero)."""

    def __init__(self, gcode, stepper="stepper_r", direction=-1.0, range_deg=(-3600.0, 3600.0),
                 symmetry_deg=180.0):
        self.gcode, self.stepper = gcode, stepper
        self.direction, self.range = float(direction), tuple(range_deg)
        self.symmetry = float(symmetry_deg)
        self.motor = 0.0

    @classmethod
    def from_config(cls, gcode, rc):
        return cls(gcode, rc.get("stepper", "stepper_r"), rc.get("direction", -1.0),
                   rc.get("range_deg", (-3600.0, 3600.0)), rc.get("symmetry_deg", 180.0))

    def move_motor(self, deg):
        lo, hi = self.range
        if not (lo <= deg <= hi):
            raise ValueError(f"rotation {deg:.1f} deg outside [rotation] range_deg {self.range}")
        self.gcode(f"MANUAL_STEPPER STEPPER={self.stepper} MOVE={deg:.3f}\nM400")
        self.motor = float(deg)

    def zero(self):
        self.move_motor(0.0)

    def turn_part(self, part_deg):
        """Turn the part by part_deg (machine frame). Returns the motor angle now."""
        self.move_motor(self.motor + part_deg / self.direction)
        return self.motor

    def turn_to(self, target_deg, measured_deg):
        """Shortest turn (mod symmetry) from measured to target. Returns the part turn made."""
        d = shortest_turn(target_deg, measured_deg, self.symmetry)
        self.turn_part(d)
        return d
