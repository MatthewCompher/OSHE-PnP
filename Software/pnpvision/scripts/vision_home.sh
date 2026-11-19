#!/bin/bash
# Started by the VISION_HOME Klipper macro (gcode_shell_command). pnpvision sends its own moves
# back through Moonraker, so it must run in the BACKGROUND: if the macro waited for it, Klipper
# would be blocked waiting for the script while the script waits for Klipper.
# The result appears in the Mainsail console (--notify); full output in results/vision_home_macro.log.
cd /home/pnp/OSHE-PnP/Software/pnpvision || exit 1
mkdir -p results
setsid nohup /home/pnp/venv-pnp/bin/python -m pnpvision home --notify "$@" \
    >> results/vision_home_macro.log 2>&1 < /dev/null &
exit 0
