"""Run-job on the touchscreen (KlipperScreen) or in Mainsail, without a laptop.

run-job --hmi replaces its keyboard prompts with Klipper `action:prompt` dialogs and its printed
progress with console messages (RESPOND). You answer by tapping a dialog button, which runs a
macro from Software/Klipper/pnp_hmi.cfg:

  PNP_ANSWER VALUE=1|0   what the dialog buttons run (1 = continue/yes, 0 = stop/no)
  PNP_CONTINUE           the same as VALUE=1, in the macro list (if a dialog doesn't show up)
  PNP_STOP               finish cleanly before the next part (answers 'no' to an open dialog)

The macros only bump counters in their own variables; this side polls them through Moonraker
(printer/objects/query?gcode_macro PNP_ANSWER), so nothing in Klipper ever waits on pnpvision
(pnpvision sends its moves through Klipper: a blocking macro would deadlock).
"""
import time

MACRO = "gcode_macro PNP_ANSWER"
STATE = "gcode_macro _PNP_STATE"        # vision_homed, job_running (pnp_hmi.cfg)


def homing_problem(mr):
    """None if the machine is homed AND VISION_HOME ran since the last X/Y homing / motors off;
    else (hard, text). hard = not homed at all (moves would fail)."""
    try:
        if not mr.is_homed():
            return True, "the machine is not homed (motors were off?): run Vision home first"
        st = mr.query(STATE)
    except Exception:
        return None                              # can't tell (no Moonraker / old config): don't block
    if "vision_homed" in st and not int(st["vision_homed"]):
        return False, ("homed, but not with Vision home since the last homing: positions can be "
                       "~2 mm off. Run Vision home first")
    return None


def _clean(text, n=200):
    """RESPOND MSG="..." can't hold double quotes; keep lines short for the small screen."""
    return " ".join(str(text).replace('"', "'").split())[:n]


class Hmi:
    def __init__(self, mr, title="PnP job", poll_s=0.3, sleep=time.sleep, echo=print):
        self.mr, self.title, self.poll_s, self.sleep, self.echo = mr, title, poll_s, sleep, echo

    # -- low level -------------------------------------------------------------------------
    def _respond(self, msg, error=False):
        try:
            self.mr.gcode(f'RESPOND {"TYPE=error " if error else ""}MSG="{_clean(msg)}"')
        except Exception as e:                       # never let the screen stop the machine
            self.echo(f"(hmi: could not send a message: {e})")

    def _cmd(self, action):
        self.mr.gcode(f'RESPOND TYPE=command MSG="action:{action}"')

    def _state(self):
        return self.mr.query(MACRO)

    # -- what run-job uses ------------------------------------------------------------------
    def start(self):
        """Clear a stop left over from an earlier job; check the macros are installed."""
        st = self._state()
        if "seq" not in st:
            raise RuntimeError("PNP_ANSWER macro missing: add [include pnp_hmi.cfg] to printer.cfg "
                               "(Software/Klipper/pnp_hmi.cfg) and restart Klipper")
        self.mr.gcode(f"SET_GCODE_VARIABLE MACRO=PNP_ANSWER VARIABLE=stop VALUE=0")

    def say(self, *parts):
        text = " ".join(str(p) for p in parts)
        self.echo(text)
        for line in text.splitlines():
            if line.strip():
                self._respond(line)

    def error(self, text):
        self.echo("ERROR: " + str(text))
        for line in str(text).splitlines()[:6]:
            if line.strip():
                self._respond(line, error=True)

    def progress(self, n, total, ref, placed=None):
        """Job page on the touchscreen: 'Layer n / total' and the status line show the part."""
        msg = f"Part {n}/{total}: {ref}" + (f", {placed} placed" if placed is not None else "")
        for g in (f"SET_PRINT_STATS_INFO TOTAL_LAYER={int(total)} CURRENT_LAYER={int(n)}",
                  f"M117 {_clean(msg, 60)}"):
            try:
                self.mr.gcode(g)
            except Exception as e:
                self.echo(f"(hmi: {e})")

    def end_job(self, ok, summary=""):
        """Job over: clear job_running and close the launcher's paused 'print' (complete if ok,
        cancelled otherwise) without moving: the pause position is re-saved here first."""
        cmds = ["SET_GCODE_VARIABLE MACRO=_PNP_STATE VARIABLE=job_running VALUE=0"]
        if summary:
            cmds.append(f"M117 {_clean(summary, 60)}")
        try:
            state = self.mr.query("print_stats").get("state")
        except Exception:
            state = None
        if state == "paused":
            cmds += ["SAVE_GCODE_STATE NAME=PAUSE_STATE\nRESUME_BASE"] if ok else ["CANCEL_PRINT_BASE"]
        for g in cmds:
            try:
                self.mr.gcode(g)
            except Exception as e:
                self.echo(f"(hmi: {e})")

    def stop_requested(self):
        try:
            return bool(int(self._state().get("stop", 0)))
        except Exception:
            return False

    def ask(self, prompt):
        """Shows `prompt` as a dialog and waits for a button. Returns what the keyboard version
        expects: 'y'/'n' for [y/N] questions, '' (continue) or 'q' (stop) otherwise."""
        text = str(prompt).strip()
        yes_no = "[y/N]" in text
        can_stop = yes_no or "q to stop" in text
        text = text.replace("[y/N]", "").replace(", or type q to stop", "").replace("press Enter", "tap Continue")
        seq0 = int(self._state().get("seq", 0))
        self.echo(text)
        self._respond(text)                              # also in the console, in case the dialog fails
        self._cmd(f"prompt_begin {_clean(self.title, 40)}")
        for line in _wrap(text, 60):
            self._cmd(f"prompt_text {_clean(line, 120)}")
        if can_stop:
            self._cmd(f"prompt_footer_button {'No' if yes_no else 'Stop'}|PNP_ANSWER VALUE=0|error")
        self._cmd(f"prompt_footer_button {'Yes' if yes_no else 'Continue'}|PNP_ANSWER VALUE=1|primary")
        self._cmd("prompt_show")
        while True:
            self.sleep(self.poll_s)
            try:
                st = self._state()
            except Exception:                          # Moonraker hiccup: keep waiting
                continue
            if int(st.get("seq", 0)) != seq0:
                break
        try:
            self._cmd("prompt_end")
        except Exception:
            pass
        ok = int(st.get("value", 1)) == 1
        self.echo("  -> " + ("yes/continue" if ok else "no/stop"))
        if yes_no:
            return "y" if ok else "n"
        return "" if ok else "q"


def _wrap(text, width):
    words, line, out = text.split(), "", []
    for w in words:
        if line and len(line) + 1 + len(w) > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return out or [""]
