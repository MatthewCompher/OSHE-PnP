# Testing and Troubleshooting

## Feeder cycle test

Picks from a feeder and drops the part in the reject bin, N times, without vision. It measures
the feeder and the pick on their own:

```bash
python -m pnpvision feeder-cycle F1 --n 20
```

It reports how many picks came up with a part. Each try is logged, so `report` includes it.

## Problems

| Symptom | Check |
|---|---|
| Servo doesn't move | `FEEDER_SET SLOT=1 ANGLE=45`; servo 5 V supply on; its ground joined to the Uno; signal on D5 |
| Servo buzzes at rest | normal only during a stroke; after `FEEDER_TOGGLE` it should go limp. Narrow the pulse widths in `pnp_feeders.cfg` if it buzzes at 0° or 180° |
| Tape doesn't advance far enough | reel drags; lever not reaching the next hole: raise that slot's stroke angle (`variable_stroke_angles`) by 5 - 15° |
| Tape advances, but the pick is empty | part bounced out: keep the plain 400/400 ms stroke; check the cover tape is peeled back far enough |
| Part picked off-centre every time | re-teach the pick spot |
| Servo gets hot or slips | stripped gears: replace the servo |
| Error about a missing `[servo feeder_N]` | that slot isn't configured (or is commented out) in `pnp_feeders.cfg` |
