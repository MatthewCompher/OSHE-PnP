# Safety

The machine moves fast (up to 400 mm/s in a job), runs on 24 V and uses compressed air. Read this
page before you power it on.

## Emergency stop

!!! danger "How to stop the machine immediately"
    Tap **EMERGENCY STOP** on the touchscreen. It is:

    - on the **PnP Job page** whenever a job runs (next to Continue and Stop job), and
    - in the **Pick & Place** menu at all times.

    Mainsail (browser) has the same button in its top bar. All three send Klipper's emergency stop
    (`M112`): every motor and output stops at once, the vacuum turns off and the part drops.

    To recover: `FIRMWARE_RESTART` (Mainsail console or touchscreen), then **Vision home**.

The emergency stop is a **software** stop: it relies on the Pi and Klipper running. For a hard
stop, switch off the power supply. A hardware emergency-stop switch in the 24 V line is a planned
upgrade ([Roadmap](../project/roadmap.md)).

**Stop job** (on the Job page) is the gentle stop: the job ends cleanly after the current part.
It needs two taps so it can't be hit by accident.

## Hazards and how they are handled

Approach: ISO 12100 style. For each hazard, first design it out, then guard or limit it, then warn.

| Hazard | Where | Mitigation |
|---|---|---|
| Moving gantry (impact, pinch) | X/Y belts, carriage, corners | Belts run in extrusion slots; motor current limited (1.0 A X/Y); travel limits in Klipper and pnpvision; red **JOB RUNNING** banner on the touchscreen; emergency stop |
| Nozzle moving down | toolhead | Z speed capped at 50 mm/s in Klipper; Z range limited to 0 - 51 mm; pnpvision lifts to a safe height before any X/Y move |
| Unexpected motion after power loss | whole machine | Klipper needs homing after every power-up; a job never resumes by itself |
| Unexpected motion from the network | whole machine | Moonraker trusts the local network: connect it only to a network you trust; a running job blocks other machine buttons |
| Electrical (24 V, mains supply) | electronics enclosure | Electronics enclosed; 24 V line fused; switch off and unplug before opening |
| Compressed air (about 60 psi) | compressor, tubing, valve, venturi | The valve closes on power loss or any Klipper fault (`shutdown_value: 0`); switch the compressor off and bleed the line before disconnecting tubing |
| Heat | stepper drivers | No heaters on the machine; drivers run at 0.5 - 1.0 A, well below the TMC5160 limits; board fan output (FAN0) |
| Small parts | reject bin, feeders | 0603/0805 parts are tiny: keep the reject bin emptied and away from children |

## Rules for operating

- Keep hands out of the work area while the **JOB RUNNING** banner is shown.
- Don't jog or run other macros while a job runs: the job moves the machine itself
  (other PnP buttons refuse to start).
- Before jogging by hand, lift the nozzle to Z 30 or higher (a smaller number) - the reject bin
  (15 mm), datum (11 mm) and PCB mounts (8 - 10 mm) stick up from the plate.
- Switch off and unplug the supply before maintenance; switch off the compressor and bleed the air.
- No PPE is needed for normal operation. Use eye protection when working on pressurized tubing.

## After an emergency stop

1. Make sure nothing is caught or jammed. Remove any loose part from the board.
2. `FIRMWARE_RESTART`.
3. **Vision home** (the touchscreen menu), then restart the job. Parts already placed stay placed:
   use the job's `--only` option or a smaller job for the rest.
