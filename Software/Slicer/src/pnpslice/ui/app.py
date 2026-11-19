"""Start the slicer window: ``python -m pnpslice.ui.app [board.kicad_pcb]``."""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from . import theme
from .main_window import MainWindow


def run(board_path: str | None = None, argv: list[str] | None = None) -> int:
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("pnpslice")
    app.setOrganizationName("OSHE")
    theme.apply(app)
    win = MainWindow()
    win.show()
    path = board_path or win.settings.value("last_board", "")
    if path and os.path.isfile(path):
        win.load(path)
    return app.exec()


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else None))