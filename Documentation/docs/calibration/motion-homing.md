# 2. Motion and Homing

## 3. Down-camera motion map

The motion map says how camera pixels turn into machine millimetres. It absorbs any camera
rotation, mirroring or scale difference, so the camera doesn't need to be squared up
mechanically (ours sits 0.5° rotated).

1. Fix a dark ~3 mm dot at PCB-top height (tape it down: it must not move).
2. Centre the down camera over it, then:
   ```bash
   python -m pnpvision calibrate-motion --cam down --step 3
   ```
3. Optional check: `python -m pnpvision repeatability --n 20` (ours: ~0.01 mm).

## 4. Visual homing

Sensorless homing lands 0.1 - 2 mm off. **Visual homing** fixes that: after `G28 X Y`, the down
camera centres on **datum dot 0** and sets that spot to its taught coordinates. Everything after
this step is measured in this frame.

1. Home (`G28`), jog the down camera over datum dot 0 (Z 30 or higher!).
2. Teach it:
   ```bash
   python -m pnpvision home --teach --polarity bright --thresh 230
   ```
3. From now on use **Vision home** (touchscreen) or `VISION_HOME` (console) instead of plain
   `G28`. Wait for its result line.

!!! danger "After every power-up, motor timeout or emergency stop: Vision home first"
    Taught positions are only valid in the visual-home frame.

### Homing order (`G28`)
Z first (to the top), then Y, then X (both with homing current), then the rotation axis is set to
0 where it stands (it has no endstop). If homing stops early in mid-air, the stall detection is too
sensitive: keep homing at 40 mm/s and 1.0 A (20 mm/s or 0.8 A false-triggered on ours).

## 5. Datum reference

The datum grid (4 mm pitch, white dots) lets pnpvision check the down camera hasn't drifted.

```bash
python -m pnpvision datum --teach        # whole grid centred and sharp
python -m pnpvision datum --reference
```
