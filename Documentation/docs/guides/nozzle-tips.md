# Nozzle Tips

The toolhead takes **Samsung CP40** nozzle tips. They pull straight off and push on.

| Tip | Approx. bore | Used for |
|---|---|---|
| N045 | 0.45 mm | 0201 |
| N08 | 0.8 mm | 0402, 0603, 0805 (**default**) |
| N14 | 1.4 mm | 1206 |
| N24 | 2.4 mm | SOIC-8 |
| N400, N750 | 4.0, 7.5 mm | larger parts |

## Changing a tip

1. Lift the nozzle (Z 20), switch the vacuum off.
2. Pull the old tip off straight down; push the new one on until it seats.
3. If this tip was used before: `python -m pnpvision tip N14 --current`.
4. If it is a new tip: record its heights ([Tip heights](../calibration/nozzle.md#8-tip-heights)),
   then centre the up camera on it (`calibrate-motion --cam up --center-only`).
5. Run the [Recovery Check](../calibration/recovery.md) if the holder was touched.

A job that needs a different tip asks you to swap it, then re-centres by itself.

!!! tip "A bent or clogged tip"
    shows up as parts picked off-centre or "empty" pickups with the part still in the pocket. Look at
    an up-camera photo of the empty tip (`snapshot --cam up --lit`): the bore should be a clean dark
    circle.
