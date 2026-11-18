# 3. Nozzle and Up Camera

## 6. Up-camera map and centre

The up camera has to know exactly where the nozzle axis is in its image.

1. `UP_LIGHT_ON`. Move the nozzle (empty, N08 tip) over the up camera at safe Z, then lower it until
   the **tip** is sharp - not the holder face. With a part on the tip, the part's bottom is sharp at
   about Z 34.6; that is the calibration plane.
2. Tune the detector without moving: `python -m pnpvision find-dot --cam up --polarity dark --thresh 40 --rmin 8 --rmax 30`
   (the bore of the tip shows as a dark circle).
3. Map and centre:
   ```bash
   python -m pnpvision calibrate-motion --cam up --find-center --step 1 --polarity dark --thresh 40 --rmin 8 --rmax 30
   ```
   Steps over ~1 mm fail (the tip's side wall hides the bore).

## 7. Down camera to nozzle offset

How far the down camera's centre is from the nozzle. Measured by eye on datum dot 0:

```bash
python -m pnpvision calibrate-offset
```

Lower the nozzle onto the dot centre by eye when asked; do it 3 times. Ours: (9.183, 52.927) mm,
spread ±0.04 mm.

## 8. Tip heights

For each nozzle tip, record where it touches the bare board and where a part on it is in focus
over the up camera:

```bash
python -m pnpvision tip N08 --board-touch-z 39.5 --inspect-z 34.6 --current
```

Find the touch Z by jogging down in 0.1 mm steps onto a bare PCB until a paper slip just drags.

## 9. Rotation direction

With a part on the nozzle over the up camera, turn in 30° steps and inspect (`inspect-up`). If the
measured angle goes the wrong way, flip `[rotation] direction` in `config.toml`.

## 10. Placement check

Put spare parts on a bare board, pick and place them, and measure where they land with the down
camera:

```bash
python -m pnpvision place-test           # then --correct to check
```

Our result: parts within 0.03 - 0.14 mm, angles within ±0.9° at 0° and 90°.
