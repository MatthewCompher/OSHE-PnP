"""Run one pnpvision command for a touchscreen / Mainsail button and show its output there.

    python -m pnpvision.relay [--as Button_name] check-machine --yes

--as: the name shown in the console (underscores become spaces), e.g. "Go to bin" for teach-bin --goto.
Commands that move the machine (MOVING) refuse to start unless VISION_HOME ran since the last
homing / motors off.

Started in the background by scripts/pnp_cmd.sh (PNP_* macros in Software/Klipper/pnp_hmi.cfg).
Every output line goes to the Klipper console (RESPOND), errors in red, and to
results/pnp_cmd_macro.log. The command gets no keyboard: anything that would wait for Enter fails
instead of hanging. It shares run-job's lock, so a button can't move the machine while a job runs.
"""
import os
import subprocess
import sys

from . import config as C
from .hmi import Hmi

LOCK = "/tmp/pnpvision_run_job.lock"
MOVING = {"check-machine", "teach-bin", "align-board", "teach-feeder", "calibrate-motion", "datum"}


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit("usage: python -m pnpvision.relay COMMAND [ARGS...]")
    label = None
    if args[0] == "--as" and len(args) > 2:
        label, args = args[1].replace("_", " "), args[2:]
    cfg = C.load("config.toml")
    from .cli import make_mr
    from .hmi import homing_problem
    mr = make_mr(cfg)
    hmi = Hmi(mr, echo=lambda *a: None)
    name = label or args[0]
    if args[0] in MOVING:
        prob = homing_problem(mr)
        if prob:
            hmi.error(f"{name}: {prob[1]}")
            return 1
    lock = None
    try:
        import fcntl
        lock = open(LOCK, "w")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:
        pass
    except OSError:
        hmi.error(f"{name}: a job is running; PNP_STOP it first")
        return 1
    hmi.say(f"{name}: started")
    p = subprocess.Popen([sys.executable, "-m", "pnpvision", *args], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, bufsize=1)
    tail = []
    for line in p.stdout:
        line = line.rstrip()
        print(line, flush=True)
        if not line.strip() or line.startswith("  File ") or line.startswith("    "):
            continue                      # traceback noise: the last line says what went wrong
        tail = (tail + [line])[-3:]
        hmi.say(line)
    rc = p.wait()
    if rc:
        hmi.error(f"{name} failed (exit {rc}): {tail[-1] if tail else 'see results/pnp_cmd_macro.log'}")
    else:
        hmi.say(f"{name}: done")
    return rc


if __name__ == "__main__":
    sys.exit(main())
