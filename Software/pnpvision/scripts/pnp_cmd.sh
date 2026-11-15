#!/bin/bash
# Started by the PNP_* button macros (gcode_shell_command pnp_cmd, Software/Klipper/pnp_hmi.cfg).
# $@ = a pnpvision command and its options, e.g. "check-machine --yes". Runs in the BACKGROUND
# (pnpvision sends its moves back through Klipper); output goes to the console via pnpvision.relay
# and to results/pnp_cmd_macro.log.
cd /home/pnp/OSHE-PnP/Software/pnpvision || exit 1
mkdir -p results
echo "=== $(date) $*" >> results/pnp_cmd_macro.log
setsid nohup /home/pnp/venv-pnp/bin/python -m pnpvision.relay "$@" \
    >> results/pnp_cmd_macro.log 2>&1 < /dev/null &
exit 0
