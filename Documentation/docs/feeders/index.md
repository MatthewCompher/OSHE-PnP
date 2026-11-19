# Feeders

Each feeder holds one reel of 8 mm component tape. A hobby servo pushes a lever that pulls the
tape forward by one pocket, so the next part sits under the pick spot.

## How the software drives them

```
pnpvision run-job -> Moonraker -> FEEDER_TOGGLE SLOT=1 -> Klipper -> Arduino Uno D5 -> servo
```

- The servos are Klipper `[servo feeder_N]` objects on the Uno (`pnp_feeders.cfg`).
- One feed: servo 0° -> stroke angle -> 0° (400 ms out, 400 ms back), then the servo goes limp so
  it doesn't buzz at rest.
- pnpvision knows which feeder holds which package from `calibration/feeders.json`
  (`teach-feeder`). The Job page shows it for every job.
- If a pick comes up empty, pnpvision feeds again and retries (up to 3 picks per part).

| Macro | Use |
|---|---|
| `FEEDER_TOGGLE SLOT=1 [COUNT=3]` | feed 1 (or 3) parts |
| `FEEDER_SET SLOT=1 ANGLE=45` / `OFF=1` | move a servo to an angle / let it go limp (setup) |

| Slot | Uno pin | Stroke | State |
|---|---|---|---|
| F1 | D5 (`uno:PD5`) | 90° | **in use**, 0603 resistors |
| F2 | D6 (`uno:PD6`) | 105° | abandoned (servo gears stripped) |
| F3 | D3 (`uno:PD3`) | 90° | abandoned (lever doesn't catch/release reliably) |

Pages: [Loading Tape](loading-tape.md) · [Teaching a Feeder](teaching.md) ·
[Testing and Troubleshooting](troubleshooting.md)
