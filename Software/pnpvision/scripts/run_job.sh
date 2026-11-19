#!/bin/bash
# Started by the RUN_JOB Klipper macro (gcode_shell_command, Software/Klipper/pnp_hmi.cfg).
# $1 = job name with spaces written as _ (e.g. Test_PCB-top for "jobs/Test PCB-top.job.json"; run-job
# looks it up and reports a wrong name on the screen), the rest = extra run-job options.
# Like vision_home.sh, pnpvision runs in the BACKGROUND (it sends its moves back through Klipper).
cd /home/pnp/OSHE-PnP/Software/pnpvision || exit 1
mkdir -p results
echo "=== $(date) RUN_JOB $*" >> results/run_job_macro.log
setsid nohup /home/pnp/venv-pnp/bin/python -m pnpvision run-job "$@" --hmi \
    >> results/run_job_macro.log 2>&1 < /dev/null &
exit 0
