"""Up-camera light rig control + 'flash and grab'.

Reality check on 'flash': these UVC cameras have no trigger input and the light is switched
by G-code through Moonraker (tens of ms of jitter), so this is NOT a microsecond strobe.
It is: light on -> wait for the light and the camera pipeline to settle -> grab a frame that
arrived after that -> light off. That is still useful (no glare/heat between picks, and an
optional ambient-light subtraction), but it costs ~settle_s per inspection. If cycle time
matters later, set keep_on=true (light stays on) and skip the switching.

Klipper side (printer.cfg) for the pin/LED backends, e.g.
    [output_pin up_light]
    pin: <free MOSFET/fan output on the Octopus Pro>   ; check LED voltage/current first
    pwm: True
    value: 0
    shutdown_value: 0
or a [neopixel up_light] / [led up_light] strip driven with SET_LED.
"""
import time

import cv2


class Light:
    is_on = False

    def on(self):
        self._set(True)
        self.is_on = True

    def off(self):
        self._set(False)
        self.is_on = False

    def _set(self, state):
        raise NotImplementedError

    def __enter__(self):
        self.on()
        return self

    def __exit__(self, *a):
        self.off()


class NullLight(Light):
    """No light rig (or room light only)."""
    def _set(self, state):
        pass


class KlipperPin(Light):
    """[output_pin NAME]  -> SET_PIN PIN=NAME VALUE=level"""
    def __init__(self, mr, name, level=1.0):
        self.mr, self.name, self.level = mr, name, float(level)

    def _set(self, state):
        v = self.level if state else 0.0
        self.mr.gcode(f"SET_PIN PIN={self.name} VALUE={v:.3f}\nM400")


class KlipperLed(Light):
    """[neopixel NAME] / [led NAME]  -> SET_LED LED=NAME RED= GREEN= BLUE= WHITE= TRANSMIT=1"""
    def __init__(self, mr, name, level=1.0, white=False, index=None):
        self.mr, self.name, self.level, self.white, self.index = mr, name, float(level), white, index

    def _set(self, state):
        v = self.level if state else 0.0
        parts = [f"SET_LED LED={self.name}"]
        if self.white:
            parts.append(f"WHITE={v:.3f}")
        else:
            parts += [f"RED={v:.3f}", f"GREEN={v:.3f}", f"BLUE={v:.3f}"]
        if self.index:
            parts.append(f"INDEX={int(self.index)}")
        parts.append("TRANSMIT=1")
        self.mr.gcode(" ".join(parts) + "\nM400")


class GpioLight(Light):
    """Light driven directly from a Pi GPIO (BCM number) through a MOSFET. Needs gpiozero."""
    def __init__(self, bcm_pin, level=1.0):
        from gpiozero import PWMOutputDevice          # imported lazily: optional dependency
        self.dev, self.level = PWMOutputDevice(int(bcm_pin)), float(level)

    def _set(self, state):
        self.dev.value = self.level if state else 0.0


def make_light(section, mr=None):
    """section = cfg['lighting']['up'] (see config.toml)."""
    kind = section.get("type", "none")
    level = section.get("level", 1.0)
    if kind == "none":
        return NullLight()
    if kind == "klipper_pin":
        return KlipperPin(mr, section["name"], level)
    if kind == "klipper_led":
        return KlipperLed(mr, section["name"], level, section.get("white", False), section.get("index"))
    if kind == "gpio":
        return GpioLight(section["name"], level)
    raise ValueError(f"unknown lighting type {kind!r}")


def grab_lit(cam, light, lens=None, settle_s=0.2, subtract_ambient=False, keep_on=False):
    """Return a frame taken with the light on (undistorted if `lens` is given).
    subtract_ambient: also grab one light-off frame and subtract it (kills room light/glare
    that does not come from your rig). The light is ALWAYS switched off afterwards unless keep_on."""
    dark = None
    try:
        if subtract_ambient and not keep_on:
            if light.is_on:
                light.off()
            dark = cam.fresh(settle_s=settle_s)
        if not light.is_on:
            light.on()
        lit = cam.fresh(settle_s=settle_s)
    finally:
        if not keep_on:
            light.off()
    frame = cv2.subtract(lit, dark) if dark is not None else lit
    return lens.undistort(frame) if lens is not None else frame
