# Teaching a Feeder

Tells pnpvision where a feeder's pick spot is and what package it holds. Do it once per feeder,
and again if the feeder moves.

1. **Vision home**. Feed a part into the pick window.
2. Jog the nozzle (Mainsail, Z 30 or higher first) over the part, then lower it in small steps
   until it **just touches** the part.
3. Save it:
   ```bash
   python -m pnpvision teach-feeder F1 --servo 1 --package R_0603_1608Metric
   ```
   - `--package` must match the KiCad footprint name in your jobs.
   - `--value 10k` limits the feeder to parts with that value.
   - For a hand-loaded track without a servo: `--manual --tape-angle <deg>`.
4. Lift the nozzle.

The saved spot is in `calibration/feeders.json`. During jobs the pick position refines itself
from the up camera (how far off-centre each part was picked).

Check it with [feeder-cycle](troubleshooting.md#feeder-cycle-test).
