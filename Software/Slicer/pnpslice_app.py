"""Entry point of the packaged slicer app (pnpslice.exe, built by build_exe.ps1).

Same as `python -m pnpslice.ui.app [board.kicad_pcb]`: opens the window, with the board given on
the command line (or dropped onto pnpslice.exe), else the last board used.
"""
import sys

from pnpslice.ui.app import run

if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else None))
