"""Open this file in VS Code and click the Run button (top right).

Opens the pnpslice window with the test board loaded (the first
"Test PCB.kicad_pcb" found under tests/fixtures). If there isn't one, it
opens the last board you used, or an empty window: use "Open board…" or drop
a .kicad_pcb file onto it.

The window needs PySide6 (Qt). If it isn't installed, this offers to install
it for you, once. Set MODE = "text" to get the old text summary instead.
"""

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))  # so this works without installing anything

MODE = "window"          # "window" or "text"
BOARD = None             # or a full path, e.g. r"C:\Users\you\Projects\Test PCB\Test PCB.kicad_pcb"
BOARD_NAME = "Test PCB.kicad_pcb"
FIXTURES = os.path.join(HERE, "tests", "fixtures")


def find_in_fixtures(name):
    for folder, dirs, files in os.walk(FIXTURES):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))  # skip .history etc.
        if name in files:
            return os.path.join(folder, name)
    return None


def have_pyside() -> bool:
    try:
        import PySide6  # noqa: F401
        return True
    except ImportError:
        return False


def install_pyside() -> bool:
    print("\nThe slicer window needs PySide6 (the Qt toolkit, about 100 MB download).")
    answer = input("Install it now? [Y/n] ").strip().lower()
    if answer not in ("", "y", "yes"):
        return False
    cmd = [sys.executable, "-m", "pip", "install", "PySide6-Essentials"]
    print("Running:", " ".join(cmd), "\n")
    if subprocess.call(cmd) != 0:
        print("\nInstall failed. Paste the error into the chat and I'll sort it out.")
        return False
    import importlib
    import site
    importlib.invalidate_caches()
    try:  # pip may have used the per-user folder, which wasn't on the path yet
        site.addsitedir(site.getusersitepackages())
    except Exception:
        pass
    return have_pyside()


def text_summary(board):
    from pnpslice.cli import main
    from pnpslice.crosscheck import find_gerber_dir
    if not board:
        sys.exit(f"No '{BOARD_NAME}' under {FIXTURES}; set BOARD at the top of run.py.")
    print(f"File: {board}\n")
    main(["info", board])
    gerbers = find_gerber_dir(board)
    print()
    if gerbers:
        print(f"Gerbers: {gerbers}\n")
        main(["check-gerbers", board, gerbers])
    else:
        print("No copper Gerbers found next to the board, so the pad check was skipped.")


board = BOARD or find_in_fixtures(BOARD_NAME)

if MODE == "window" and (have_pyside() or install_pyside()):
    from pnpslice.ui.app import run
    sys.exit(run(board))
else:
    text_summary(board)