"""Colours and the Qt style sheet (dark, teal accent, in the spirit of OrcaSlicer)."""

from PySide6.QtGui import QColor, QPalette

ACCENT = "#009688"          # OrcaSlicer's teal
ACCENT_HOVER = "#26a69a"
BG = "#1f2124"              # window
PANEL = "#2a2d31"           # sidebar / bars
PANEL_LIGHT = "#33373c"
BORDER = "#3c4046"
TEXT = "#e6e6e6"
TEXT_DIM = "#9aa0a6"
ERROR = "#ef5350"
WARN = "#ffb74d"

# board view
VIEW_BG = "#16181b"
BOARD_FILL = "#17462f"      # solder-mask green
BOARD_EDGE = "#e8c547"      # Edge.Cuts yellow, like KiCad
GRID_MINOR = QColor(255, 255, 255, 14)
GRID_MAJOR = QColor(255, 255, 255, 34)
PAD = QColor("#d6a645")     # copper / gold
PAD_PIN1 = QColor("#ff7a45")
PAD_HOVER = QColor("#ffd27a")
PART_MARK = QColor(255, 255, 255, 150)
PAD_PENDING = QColor(214, 166, 69, 55)      # preview: not placed yet
BODY_PLACED = QColor(38, 50, 56, 235)       # preview: placed part body (dark grey)
BODY_CURRENT = QColor(0, 150, 136, 200)     # preview: the part being placed
TRAVEL = QColor(38, 166, 154, 110)          # preview: path between placements
ALIGN = QColor("#e040fb")                   # alignment pads
ALIGN_COVERED = QColor(160, 160, 160, 170)  # preview: alignment pad already covered
CAND_OK = QColor(76, 200, 90)               # pick mode: distinct pad
CAND_BAD = QColor(239, 83, 80)              # pick mode: has a look-alike nearby
SELECT = QColor(ACCENT_HOVER)
AXIS_X = QColor("#ef5350")
AXIS_Y = QColor("#66bb6a")
LABEL = QColor(255, 255, 255, 210)


def apply(app) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Base, QColor(PANEL))
    pal.setColor(QPalette.AlternateBase, QColor(PANEL_LIGHT))
    pal.setColor(QPalette.Text, QColor(TEXT))
    pal.setColor(QPalette.Button, QColor(PANEL_LIGHT))
    pal.setColor(QPalette.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.Highlight, QColor(ACCENT))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ToolTipBase, QColor(PANEL_LIGHT))
    pal.setColor(QPalette.ToolTipText, QColor(TEXT))
    pal.setColor(QPalette.PlaceholderText, QColor(TEXT_DIM))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#6b7075"))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)


STYLE = f"""
QMainWindow, QWidget#central {{ background: {BG}; }}
QWidget#topbar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QLabel#appname {{ font-size: 15px; font-weight: 600; color: {TEXT}; padding: 0 10px 0 4px; }}
QPushButton#tab {{
    background: transparent; border: none; color: {TEXT_DIM};
    padding: 8px 16px; font-size: 13px; border-bottom: 2px solid transparent;
}}
QPushButton#tab:checked {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QPushButton#tab:disabled {{ color: #5b6066; }}
QPushButton#primary {{
    background: {ACCENT}; color: white; border: none; border-radius: 4px;
    padding: 6px 18px; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#primary:disabled {{ background: #3a4a48; color: #7f8a88; }}
QPushButton {{
    background: {PANEL_LIGHT}; border: 1px solid {BORDER}; border-radius: 4px;
    padding: 5px 12px; color: {TEXT};
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; }}

QWidget#sidebar, QScrollArea#sidebar {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
QLabel#section {{
    color: {TEXT}; font-weight: 600; font-size: 12px;
    padding: 10px 2px 4px 2px; border-bottom: 1px solid {BORDER};
}}
QLabel#key {{ color: {TEXT_DIM}; }}
QLabel#value {{ color: {TEXT}; }}
QLabel#hint {{ color: {TEXT_DIM}; font-size: 11px; }}

QWidget#platebar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QPushButton#plate {{
    background: {PANEL_LIGHT}; border: 1px solid {BORDER}; border-radius: 4px;
    padding: 5px 14px; color: {TEXT_DIM};
}}
QPushButton#plate:checked {{ background: {ACCENT}; border-color: {ACCENT}; color: white; font-weight: 600; }}
QPushButton#toggle {{ padding: 4px 10px; color: {TEXT_DIM}; }}
QPushButton#toggle:checked {{ background: #24423f; border-color: {ACCENT}; color: {TEXT}; }}
QLabel#viewnote {{ color: {WARN}; padding-left: 10px; }}
QWidget#sliderpanel {{ background: {PANEL}; border-left: 1px solid {BORDER}; }}
QLabel#stepbig {{ color: {TEXT}; font-size: 15px; font-weight: 600; }}
QSlider::groove:vertical {{ background: {BORDER}; width: 4px; border-radius: 2px; }}
QSlider::sub-page:vertical {{ background: {BORDER}; border-radius: 2px; }}
QSlider::add-page:vertical {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:vertical {{
    background: {ACCENT_HOVER}; border: 2px solid white; height: 14px; width: 14px;
    margin: 0 -7px; border-radius: 9px;
}}
QCheckBox {{ color: {TEXT}; spacing: 8px; }}
QSpinBox, QDoubleSpinBox {{
    background: {BG}; border: 1px solid {BORDER}; border-radius: 4px; padding: 2px 4px; color: {TEXT};
}}
QPushButton#pick:checked {{ background: #6a1b9a; border-color: #e040fb; color: white; }}
QDialog {{ background: {BG}; }}

QTableWidget {{
    background: {PANEL}; alternate-background-color: {PANEL_LIGHT};
    gridline-color: {BORDER}; border: 1px solid {BORDER}; selection-background-color: {ACCENT};
}}
QHeaderView::section {{
    background: {PANEL_LIGHT}; color: {TEXT_DIM}; border: none;
    border-right: 1px solid {BORDER}; padding: 4px 6px;
}}
QListWidget {{ background: {PANEL}; border: 1px solid {BORDER}; }}
QLineEdit {{
    background: {BG}; border: 1px solid {BORDER}; border-radius: 4px; padding: 4px 6px; color: {TEXT};
}}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QStatusBar {{ background: {PANEL}; color: {TEXT_DIM}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: {TEXT_DIM}; padding: 0 8px; }}
QToolTip {{ background: {PANEL_LIGHT}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QScrollBar:vertical {{ background: {PANEL}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
"""