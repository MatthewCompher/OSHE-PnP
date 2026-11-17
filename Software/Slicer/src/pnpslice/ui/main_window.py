"""Main window, OrcaSlicer-style.

Prepare tab: board, plate, slice settings, live problem list, parts table.
Slice plate:  runs the slicer on the current plate; if there are no errors,
              switches to Preview.
Preview tab:  the placement order with a step slider (like Orca's layer
              slider); Export job… writes the job file.
"""

from __future__ import annotations

import os
from collections import Counter

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QColor, QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QDialog,
                               QDialogButtonBox, QDoubleSpinBox, QFileDialog, QGridLayout, QHBoxLayout,
                               QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter, QStackedWidget,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .. import __version__
from ..board import Board, BoardError, load_board
from ..heights import SOURCE_LABELS, resolve_height
from ..job import build_job, default_filename, write_job
from ..plate import Plate, build_plates
from ..project import ProjectSettings
from ..slicer import Issue, SliceResult, slice_plate
from . import theme
from .board_view import BoardView


def _label(text: str, name: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName(name)
    return lab


def _table(headers: list[str], stretch_col: int) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(22)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    h = t.horizontalHeader()
    h.setSectionResizeMode(QHeaderView.ResizeToContents)
    h.setSectionResizeMode(stretch_col, QHeaderView.Stretch)
    return t


class NumItem(QTableWidgetItem):
    """Table cell that sorts by number."""

    def __init__(self, value: float | None, fmt: str):
        super().__init__("—" if value is None else format(value, fmt))
        self.value = float("inf") if value is None else value
        self.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

    def __lt__(self, other):
        return self.value < getattr(other, "value", 0)


# ---------------------------------------------------------------------------
# Prepare sidebar


class PrepareSidebar(QScrollArea):
    """Scrolls when the window is short, like Orca's settings panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("sidebar")
        self.setWidget(inner)
        self.setObjectName("sidebar")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 4, 12, 12)
        lay.setSpacing(6)
        self._issues: list[Issue] = []

        # Board
        lay.addWidget(_label("Board", "section"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(3)
        self.board_vals = {}
        for row, key in enumerate(("Name", "Size", "Thickness", "KiCad", "File")):
            grid.addWidget(_label(key, "key"), row, 0, Qt.AlignTop)
            v = _label("-", "value")
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.setWordWrap(True)
            grid.addWidget(v, row, 1)
            self.board_vals[key] = v
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        # Plate
        lay.addWidget(_label("Plate", "section"))
        self.plate_info = _label("-", "value")
        self.plate_info.setWordWrap(True)
        self.plate_info.setTextFormat(Qt.RichText)
        lay.addWidget(self.plate_info)
        self.include_all_btn = QPushButton("Include all")
        self.include_all_btn.setToolTip("Put every part you excluded on this plate back in the job")
        self.include_all_btn.hide()
        lay.addWidget(self.include_all_btn, 0, Qt.AlignLeft)

        # Slice settings
        lay.addWidget(_label("Slice settings", "section"))
        self.auto_number = QCheckBox("Auto-number duplicate references")
        self.auto_number.setToolTip("Gives parts that share a reference (or are unnumbered) names like "
                                    "R0805_1, R0805_2… in the job file only. Your KiCad file isn't changed.")
        lay.addWidget(self.auto_number)
        row = QHBoxLayout()
        self.heights_btn = QPushButton("Edit heights…")
        row.addWidget(self.heights_btn)
        self.heights_note = _label("", "hint")
        self.heights_note.setWordWrap(True)
        row.addWidget(self.heights_note, 1)
        lay.addLayout(row)
        lay.addWidget(_label("Order: lowest parts first, one package at a time, shortest path.", "hint"))

        # Alignment
        lay.addWidget(_label("Alignment pads", "section"))
        row = QHBoxLayout()
        row.addWidget(_label("Pads", "key"))
        self.align_count = QSpinBox()
        self.align_count.setRange(2, 4)
        self.align_count.setToolTip("How many pads to choose automatically (2-4). 3 or more also fixes rotation.")
        row.addWidget(self.align_count)
        row.addSpacing(10)
        row.addWidget(_label("Look-alike clearance ≥", "key"))
        self.align_clear = QDoubleSpinBox()
        self.align_clear.setRange(0.5, 10.0)
        self.align_clear.setSingleStep(0.25)
        self.align_clear.setDecimals(2)
        self.align_clear.setSuffix(" mm")
        self.align_clear.setToolTip("A pad only counts as distinct if no pad of similar shape and size is "
                                    "closer than this. JOB_FORMAT.md asks for 3 mm. Lower it only if the "
                                    "board sits accurately on the machine (look-alikes must be more than "
                                    "twice the board's position error away).")
        row.addWidget(self.align_clear)
        row.addStretch(1)
        lay.addLayout(row)
        self.align_list = QListWidget()
        self.align_list.setFixedHeight(96)
        self.align_list.setFocusPolicy(Qt.NoFocus)
        self.align_list.setWordWrap(True)
        lay.addWidget(self.align_list)
        row = QHBoxLayout()
        self.pick_btn = QPushButton("Pick by hand")
        self.pick_btn.setObjectName("pick")
        self.pick_btn.setCheckable(True)
        self.pick_btn.setToolTip("Click pads on the board to add or remove them. "
                                 "Green outline = distinct, red = has a look-alike nearby.")
        row.addWidget(self.pick_btn)
        self.auto_btn = QPushButton("Auto")
        self.auto_btn.setToolTip("Forget your picks and choose automatically")
        row.addWidget(self.auto_btn)
        self.align_mode = _label("", "hint")
        row.addWidget(self.align_mode, 1)
        lay.addLayout(row)

        # Problems
        lay.addWidget(_label("Problems", "section"))
        self.problems = QListWidget()
        self.problems.setWordWrap(True)
        self.problems.setFixedHeight(130)
        self.problems.setFocusPolicy(Qt.NoFocus)
        self.problems.setToolTip("Click a problem to show the first part it's about")
        lay.addWidget(self.problems)

        # Parts
        lay.addWidget(_label("Parts", "section"))
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by reference, value or package…")
        self.filter.textChanged.connect(self._apply_filter)
        lay.addWidget(self.filter)
        self.table = _table(["Ref", "Package", "X", "Y", "Rot", "H"], 1)
        self.table.setSortingEnabled(True)
        self.table.setMinimumHeight(280)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        lay.addWidget(self.table, 1)
        hint = _label("Untick a part (or right-click it here or on the board) to exclude it. "
                      "X / Y in mm from the board's lower-left corner, as seen from this side. "
                      "Rot in degrees, counter-clockwise. H = height in mm.", "hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

    def show_board(self, board: Board | None):
        if board is None:
            for v in self.board_vals.values():
                v.setText("-")
            return
        o = board.outline
        shape = "" if o.is_rectangle else f", {len(o.outer)}-point outline"
        holes = f", {len(o.holes)} cut-out(s)" if o.holes else ""
        self.board_vals["Name"].setText(board.name)
        self.board_vals["Size"].setText(f"{o.width:.2f} × {o.height:.2f} mm{shape}{holes}")
        self.board_vals["Thickness"].setText(f"{board.thickness:g} mm")
        self.board_vals["KiCad"].setText(f"{board.generator_version or '?'}  (format {board.file_version})")
        self.board_vals["File"].setText(os.path.basename(board.path))
        self.board_vals["File"].setToolTip(board.path)

    def show_plate(self, board: Board, plate: Plate, check: SliceResult, settings: ProjectSettings):
        side = "top, looking down" if plate.side == "top" else "bottom, seen from below (mirrored)"
        excluded = {p.key for p in plate.parts if p.key in settings.excluded and not p.dnp}
        to_place = [p for p in plate.parts if not p.dnp and p.key not in excluded]
        n_dnp = sum(1 for p in plate.parts if p.dnp)
        extra = [f"{len(excluded)} excluded"] if excluded else []
        extra += [f"{n_dnp} do-not-populate"] if n_dnp else []
        lines = [f"<b>{plate.title}</b> &nbsp;<span style='color:{theme.TEXT_DIM}'>{side}</span>",
                 f"{len(to_place)} parts to place"
                 + (f" <span style='color:{theme.WARN}'>(+{', '.join(extra)}: kept with skip)</span>"
                    if extra else "")]
        for pkg, n in sorted(Counter(p.package for p in to_place).items()):
            lines.append(f"&nbsp;&nbsp;{n} × {pkg}")
        for why, n in plate.skipped_counts().items():
            lines.append(f"<span style='color:{theme.TEXT_DIM}'>skipped {n}: {why}</span>")
        self.plate_info.setText("<br>".join(lines))
        self.include_all_btn.setVisible(bool(excluded))
        self.include_all_btn.setText(f"Include all ({len(excluded)} excluded)")

        self.auto_number.blockSignals(True)
        self.auto_number.setChecked(settings.auto_number)
        self.auto_number.blockSignals(False)
        src = Counter(p.height_source for p in {pl.part.package: pl for pl in check.placements}.values())
        bits = [f"{n} {SOURCE_LABELS[s]}" for s, n in src.items()]
        self.heights_note.setText(", ".join(bits))

        self.show_issues(board, check)
        self.show_alignment(check, settings)

        heights = {pl.part_index: pl for pl in check.placements}
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(plate.parts))
        for row, p in enumerate(plate.parts):
            ref = QTableWidgetItem(p.ref + (" (DNP)" if p.dnp else ""))
            ref.setData(Qt.UserRole, row)
            if p.dnp:
                ref.setFlags(ref.flags() & ~Qt.ItemIsUserCheckable)
                ref.setToolTip(f"{p.ref}  {p.value}  — do not populate in KiCad: in the job with skip")
                ref.setForeground(QColor(theme.TEXT_DIM))
            else:
                ref.setFlags(ref.flags() | Qt.ItemIsUserCheckable)
                ex = p.key in excluded
                ref.setCheckState(Qt.Unchecked if ex else Qt.Checked)
                ref.setToolTip(f"{p.ref}  {p.value}  — untick to exclude (kept in the job with skip)")
                if ex:
                    ref.setForeground(QColor(theme.TEXT_DIM))
            self.table.setItem(row, 0, ref)
            pk = QTableWidgetItem(p.package)
            pk.setToolTip(p.package)
            self.table.setItem(row, 1, pk)
            self.table.setItem(row, 2, NumItem(p.x, ".3f"))
            self.table.setItem(row, 3, NumItem(p.y, ".3f"))
            self.table.setItem(row, 4, NumItem(p.rot, "g"))
            pl = heights.get(row)
            h = NumItem(pl.height if pl else None, "g")
            if pl:
                h.setToolTip(f"from {SOURCE_LABELS[pl.height_source]}")
            self.table.setItem(row, 5, h)
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        self._apply_filter(self.filter.text())

    def show_alignment(self, check: SliceResult, settings: ProjectSettings):
        for w, v in ((self.align_count, settings.align_count), (self.align_clear, settings.align_clearance)):
            w.blockSignals(True)
            w.setValue(v)
            w.blockSignals(False)
        self.align_list.clear()
        for pick in check.alignment:
            it = QListWidgetItem(f"{pick.name}   {pick.cand.describe(settings.align_clearance)}")
            ok = pick.cand.distinct(settings.align_clearance)
            it.setForeground(QColor(theme.TEXT if ok else theme.WARN))
            self.align_list.addItem(it)
        if not check.alignment:
            self.align_list.addItem("No visible pads on this side")
        self.align_mode.setText("picked by hand" if check.align_manual else "chosen automatically")
        self.auto_btn.setEnabled(check.align_manual or bool(settings.alignment.get(check.plate.side)))

    def show_issues(self, board: Board, check: SliceResult):
        self.problems.clear()
        self._issues = list(check.issues)
        for issue in self._issues:
            it = QListWidgetItem(("✖ " if issue.is_error else "⚠ ") + issue.message)
            it.setForeground(QColor(theme.ERROR if issue.is_error else theme.WARN))
            self.problems.addItem(it)
        for w in board.warnings:
            it = QListWidgetItem("⚠ " + w)
            it.setForeground(QColor(theme.WARN))
            self.problems.addItem(it)
            self._issues.append(Issue("warning", w))
        if not check.errors:
            it = QListWidgetItem("✔ Ready to slice")
            it.setForeground(QColor(theme.ACCENT_HOVER))
            self.problems.insertItem(0, it)
            self._issues.insert(0, Issue("ok", ""))

    def issue_at(self, row: int) -> Issue | None:
        return self._issues[row] if 0 <= row < len(self._issues) else None

    def _apply_filter(self, text: str):
        t = text.strip().lower()
        for row in range(self.table.rowCount()):
            cells = [self.table.item(row, c) for c in (0, 1)]
            hay = " ".join((c.text() + " " + (c.toolTip() or "")) for c in cells if c).lower()
            self.table.setRowHidden(row, bool(t) and t not in hay)

    def select_index(self, index: int):
        self.table.blockSignals(True)
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            it = self.table.item(row, 0)
            if it and it.data(Qt.UserRole) == index:
                self.table.selectRow(row)
                self.table.scrollToItem(it, QAbstractItemView.PositionAtCenter)
                break
        self.table.blockSignals(False)

    def index_at_row(self, row: int) -> int:
        it = self.table.item(row, 0)
        return it.data(Qt.UserRole) if it else -1

    def selected_index(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return -1
        return self.table.item(rows[0].row(), 0).data(Qt.UserRole)


# ---------------------------------------------------------------------------
# Preview sidebar


class PreviewSidebar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 4, 12, 12)
        lay.setSpacing(6)
        lay.addWidget(_label("Job", "section"))
        self.summary = _label("-", "value")
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.RichText)
        lay.addWidget(self.summary)
        lay.addWidget(_label("Warnings", "section"))
        self.warnings = QListWidget()
        self.warnings.setWordWrap(True)
        self.warnings.setMaximumHeight(130)
        self.warnings.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.warnings)
        lay.addWidget(_label("Placement order", "section"))
        self.table = _table(["#", "Ref", "Package", "H"], 2)
        lay.addWidget(self.table, 1)
        hint = _label("Click a row, or use the slider / ↑ ↓ keys, to step through the placements.", "hint")
        hint.setWordWrap(True)
        lay.addWidget(hint)

    def show_result(self, board: Board, result: SliceResult):
        plate = result.plate
        hs = [p.height for p in result.placements]
        pk = len({p.part.package for p in result.placements})
        n_skip = sum(1 for p in result.placements if p.skip)
        skip_txt = f" (+{n_skip} skip)" if n_skip else ""
        self.summary.setText(
            f"<b>{plate.title}</b><br>{len(result.placements) - n_skip} placements{skip_txt}, "
            f"{pk} package(s)<br>"
            f"heights {min(hs):g} – {max(hs):g} mm<br>"
            f"alignment: {', '.join(a.name + ' ' + a.cand.label() for a in result.alignment)}<br>"
            f"<span style='color:{theme.TEXT_DIM}'>file: {default_filename(board, plate.side)}</span>")
        self.warnings.clear()
        for w in result.warnings:
            it = QListWidgetItem("⚠ " + w.message)
            it.setForeground(QColor(theme.WARN))
            self.warnings.addItem(it)
        if not result.warnings:
            self.warnings.addItem("✔ No warnings")
        self.table.setRowCount(len(result.placements))
        for row, p in enumerate(result.placements):
            n = NumItem(p.order, "d")
            self.table.setItem(row, 0, n)
            ref = QTableWidgetItem(p.ref + (" (skip)" if p.skip else ""))
            if p.ref != p.original_ref:
                ref.setToolTip(f"{p.original_ref} in KiCad")
            if p.skip:
                ref.setForeground(QColor(theme.TEXT_DIM))
            self.table.setItem(row, 1, ref)
            pk_item = QTableWidgetItem(p.part.package)
            pk_item.setToolTip(p.part.package)
            self.table.setItem(row, 2, pk_item)
            h = NumItem(p.height, "g")
            h.setToolTip(f"from {SOURCE_LABELS[p.height_source]}")
            self.table.setItem(row, 3, h)

    def select_step(self, step: int):
        self.table.blockSignals(True)
        self.table.clearSelection()
        if 1 <= step <= self.table.rowCount():
            self.table.selectRow(step - 1)
            self.table.scrollToItem(self.table.item(step - 1, 0), QAbstractItemView.EnsureVisible)
        self.table.blockSignals(False)


# ---------------------------------------------------------------------------
# Heights dialog


class HeightsDialog(QDialog):
    """Package heights for the whole board; edit a value to override it."""

    def __init__(self, board: Board, plates: list[Plate], settings: ProjectSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Part heights")
        self.resize(640, 460)
        self.settings = settings
        lay = QVBoxLayout(self)
        lay.addWidget(_label("Height of each package in mm, used for the placement Z. Type a value to set "
                             "your own; clear it to go back to the default. Typical values are a starting "
                             "point: check them against your parts' datasheets.", "hint"))
        lay.itemAt(0).widget().setWordWrap(True)

        counts: Counter = Counter()
        example: dict = {}
        for plate in plates:
            for p in plate.parts:
                counts[p.package] += 1
                example.setdefault(p.package, p)
        self.packages = sorted(counts)
        self.table = QTableWidget(len(self.packages), 4)
        self.table.setHorizontalHeaderLabels(["Package", "Parts", "Height (mm)", "From"])
        self.table.verticalHeader().setVisible(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeToContents)
        h.setSectionResizeMode(0, QHeaderView.Stretch)
        self.defaults: dict[str, tuple] = {}
        for row, pkg in enumerate(self.packages):
            props = example[pkg].footprint.properties
            default = resolve_height(pkg, props, None)
            self.defaults[pkg] = default
            cur = resolve_height(pkg, props, settings.heights)
            a = QTableWidgetItem(pkg)
            a.setFlags(a.flags() & ~Qt.ItemIsEditable)
            b = QTableWidgetItem(str(counts[pkg]))
            b.setFlags(b.flags() & ~Qt.ItemIsEditable)
            b.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            c = QTableWidgetItem("" if cur[0] is None else f"{cur[0]:g}")
            c.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            d = QTableWidgetItem(SOURCE_LABELS[cur[1]])
            d.setFlags(d.flags() & ~Qt.ItemIsEditable)
            for col, item in enumerate((a, b, c, d)):
                self.table.setItem(row, col, item)
        self.table.itemChanged.connect(self._changed)
        lay.addWidget(self.table, 1)
        self.error = _label("", "hint")
        self.error.setStyleSheet(f"color: {theme.ERROR}")
        lay.addWidget(self.error)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _changed(self, item: QTableWidgetItem):
        if item.column() != 2:
            return
        pkg = self.packages[item.row()]
        txt = item.text().strip()
        src = self.table.item(item.row(), 3)
        self.table.blockSignals(True)
        if not txt:
            dh, ds = self.defaults[pkg]
            item.setText("" if dh is None else f"{dh:g}")
            src.setText(SOURCE_LABELS[ds])
        else:
            src.setText(SOURCE_LABELS["setting"])
        self.table.blockSignals(False)

    def _accept(self):
        new: dict[str, float] = {}
        for row, pkg in enumerate(self.packages):
            txt = self.table.item(row, 2).text().strip().replace(",", ".")
            if not txt:
                continue
            try:
                v = float(txt)
            except ValueError:
                self.error.setText(f"“{txt}” for {pkg} isn't a number.")
                return
            if not 0 < v < 50:
                self.error.setText(f"Height for {pkg} must be between 0 and 50 mm.")
                return
            if self.table.item(row, 3).text() == SOURCE_LABELS["setting"] or self.defaults[pkg][0] != v:
                new[pkg] = v
        self.settings.heights = new
        self.accept()


# ---------------------------------------------------------------------------
# Main window


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        self.setWindowTitle(f"pnpslice {__version__}")
        self.resize(1360, 860)
        self.setAcceptDrops(True)
        self.settings = settings if settings is not None else QSettings("OSHE", "pnpslice")
        self.board: Board | None = None
        self.project = ProjectSettings()
        self.plates: list[Plate] = []
        self.checks: list[SliceResult] = []          # live check per plate
        self.sliced: dict[int, SliceResult] = {}     # results of "Slice plate", per plate
        self.plate_idx = 0
        self.mode = "prepare"

        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(1)
        self.side_stack = QStackedWidget()
        self.side_stack.setMinimumWidth(340)
        self.sidebar = PrepareSidebar()
        self.preview_side = PreviewSidebar()
        self.side_stack.addWidget(self.sidebar)
        self.side_stack.addWidget(self.preview_side)
        split.addWidget(self.side_stack)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._build_platebar())
        view_row = QHBoxLayout()
        view_row.setContentsMargins(0, 0, 0, 0)
        view_row.setSpacing(0)
        self.view = BoardView()
        view_row.addWidget(self.view, 1)
        view_row.addWidget(self._build_slider())
        rl.addLayout(view_row, 1)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([380, 980])
        root.addWidget(split, 1)
        self.setCentralWidget(central)

        sb = self.statusBar()
        self.st_cursor = QLabel("")
        self.st_part = QLabel("")
        self.st_zoom = QLabel("")
        sb.addWidget(self.st_cursor)
        sb.addWidget(self.st_part, 1)
        sb.addPermanentWidget(self.st_zoom)

        self.view.cursorMoved.connect(self._on_cursor)
        self.view.partHovered.connect(self._on_hover)
        self.view.partSelected.connect(self._on_view_select)
        self.view.zoomChanged.connect(lambda z: self.st_zoom.setText(f"{z:.1f} px/mm"))
        self.sidebar.table.itemSelectionChanged.connect(self._on_table_select)
        self.sidebar.problems.itemClicked.connect(self._on_problem_click)
        self.sidebar.auto_number.toggled.connect(self._on_auto_number)
        self.sidebar.heights_btn.clicked.connect(self.edit_heights)
        self.preview_side.table.itemSelectionChanged.connect(self._on_order_select)
        self.sidebar.align_count.valueChanged.connect(self._on_align_count)
        self.sidebar.align_clear.valueChanged.connect(self._on_align_clear)
        self.sidebar.pick_btn.toggled.connect(self._on_pick_mode)
        self.sidebar.auto_btn.clicked.connect(self._on_align_auto)
        self.view.alignPadClicked.connect(self._on_align_pad_clicked)
        self.view.partMenuRequested.connect(self._part_menu)
        self.sidebar.table.itemChanged.connect(self._on_part_check)
        self.sidebar.table.customContextMenuRequested.connect(self._on_table_menu)
        self.sidebar.include_all_btn.clicked.connect(self._include_all)
        self.view.alignPadHovered.connect(self._on_align_pad_hovered)

        for keys, slot in ((QKeySequence.Open, self.open_dialog), ("F5", self.reload),
                           ("Ctrl+R", self.slice_current), ("Ctrl+E", self.export_current)):
            act = QAction(self)
            act.setShortcut(QKeySequence(keys))
            act.triggered.connect(slot)
            self.addAction(act)
        for key, delta in (("Up", 1), ("Right", 1), ("Down", -1), ("Left", -1),
                           ("PgUp", 10), ("PgDown", -10)):
            sc = QShortcut(QKeySequence(key), self.view)
            sc.activated.connect(lambda d=delta: self._nudge_step(d))
        QShortcut(QKeySequence("Home"), self.view).activated.connect(lambda: self.slider.setValue(1))
        QShortcut(QKeySequence("End"), self.view).activated.connect(lambda: self.slider.setValue(self.slider.maximum()))

        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self._update_buttons()

    # ---- layout pieces ---------------------------------------------------------
    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("topbar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 0, 10, 0)
        h.setSpacing(4)
        h.addWidget(_label("pnpslice", "appname"))
        self.tab_prepare = QPushButton("Prepare")
        self.tab_preview = QPushButton("Preview")
        self.tab_group = QButtonGroup(self)
        for i, b in enumerate((self.tab_prepare, self.tab_preview)):
            b.setObjectName("tab")
            b.setCheckable(True)
            self.tab_group.addButton(b, i)
            h.addWidget(b)
        self.tab_prepare.setChecked(True)
        self.tab_prepare.clicked.connect(lambda: self.set_mode("prepare"))
        self.tab_preview.clicked.connect(lambda: self.set_mode("preview"))
        h.addStretch(1)
        open_btn = QPushButton("Open board…")
        open_btn.clicked.connect(self.open_dialog)
        h.addWidget(open_btn)
        self.reload_btn = QPushButton("Reload")
        self.reload_btn.setToolTip("Re-read the board file after saving it in KiCad (F5)")
        self.reload_btn.clicked.connect(self.reload)
        h.addWidget(self.reload_btn)
        h.addSpacing(10)
        self.slice_btn = QPushButton("Slice plate")
        self.slice_btn.setObjectName("primary")
        self.slice_btn.setToolTip("Check this plate and work out the placement order (Ctrl+R)")
        self.slice_btn.clicked.connect(self.slice_current)
        h.addWidget(self.slice_btn)
        self.export_btn = QPushButton("Export job…")
        self.export_btn.setObjectName("primary")
        self.export_btn.setToolTip("Save the job file for this plate (Ctrl+E)")
        self.export_btn.clicked.connect(self.export_current)
        h.addWidget(self.export_btn)
        bar.setFixedHeight(44)
        return bar

    def _build_platebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("platebar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(10, 6, 10, 6)
        h.setSpacing(6)
        self.plate_group = QButtonGroup(self)
        self.plate_btns = []
        for i in range(2):
            b = QPushButton()
            b.setObjectName("plate")
            b.setCheckable(True)
            b.setEnabled(False)
            self.plate_group.addButton(b, i)
            self.plate_btns.append(b)
            h.addWidget(b)
        self._set_plate_buttons()
        self.plate_group.idClicked.connect(self.show_plate)
        self.view_note = _label("", "viewnote")
        h.addWidget(self.view_note)
        h.addStretch(1)
        self.btn_labels = QPushButton("Labels")
        self.btn_grid = QPushButton("Grid")
        for b, slot in ((self.btn_labels, lambda on: self.view.set_labels(on)),
                        (self.btn_grid, lambda on: self.view.set_grid(on))):
            b.setObjectName("toggle")
            b.setCheckable(True)
            b.setChecked(True)
            b.toggled.connect(slot)
            h.addWidget(b)
        fit = QPushButton("Fit")
        fit.setObjectName("toggle")
        fit.setToolTip("Fit the board in the view (F, or double-click empty space)")
        fit.clicked.connect(lambda: self.view.fit())
        h.addWidget(fit)
        return bar

    def _build_slider(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("sliderpanel")
        panel.setFixedWidth(84)
        v = QVBoxLayout(panel)
        v.setContentsMargins(6, 10, 6, 10)
        v.setSpacing(6)
        self.step_top = _label("", "stepbig")
        self.step_top.setAlignment(Qt.AlignCenter)
        v.addWidget(self.step_top)
        self.slider = QSlider(Qt.Vertical)
        self.slider.setMinimum(1)
        self.slider.setPageStep(10)
        self.slider.valueChanged.connect(self._on_step)
        v.addWidget(self.slider, 1, Qt.AlignHCenter)
        self.step_bottom = _label("1", "hint")
        self.step_bottom.setAlignment(Qt.AlignCenter)
        v.addWidget(self.step_bottom)
        self.slider_panel = panel
        panel.hide()
        return panel

    def _set_plate_buttons(self):
        for i, b in enumerate(self.plate_btns):
            if i < len(self.plates):
                p = self.plates[i]
                mark = " ✓" if i in self.sliced else ""
                n = sum(1 for q in p.parts if not q.dnp and q.key not in self.project.excluded)
                b.setText(f"{p.title}  ({n}){mark}")
                b.setEnabled(True)
            else:
                b.setText(("Plate 1 · Top", "Plate 2 · Bottom")[i])
                b.setEnabled(False)
        if self.plates:
            self.plate_btns[self.plate_idx].setChecked(True)

    def _update_buttons(self):
        has = bool(self.plates)
        sliced = self.plate_idx in self.sliced
        self.reload_btn.setEnabled(self.board is not None)
        self.slice_btn.setEnabled(has)
        self.export_btn.setEnabled(sliced)
        self.tab_preview.setEnabled(sliced)
        self.tab_preview.setToolTip("" if sliced else "Slice this plate first")

    # ---- loading ---------------------------------------------------------------
    def open_dialog(self):
        start = self.settings.value("last_dir", "") or ""
        path, _ = QFileDialog.getOpenFileName(self, "Open KiCad board", start,
                                              "KiCad board (*.kicad_pcb);;All files (*)")
        if path:
            self.load(path)

    def reload(self):
        if self.board:
            self.load(self.board.path, keep_view=True)

    def load(self, path: str, keep_view: bool = False) -> bool:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            board = load_board(path)
            plates = build_plates(board)
            project = ProjectSettings.load(path)
        except BoardError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Can't open board", str(e))
            return False
        except Exception as e:  # keep the window alive on unexpected errors
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Error reading board", f"{type(e).__name__}: {e}")
            return False
        QApplication.restoreOverrideCursor()

        self.board = board
        self.plates = plates
        self.project = project
        self.sliced = {}
        self._recheck()
        if not keep_view:
            self.plate_idx = next((i for i, p in enumerate(plates) if p.parts), 0)
        self.settings.setValue("last_board", path)
        self.settings.setValue("last_dir", os.path.dirname(path))
        self.setWindowTitle(f"{board.name} — pnpslice {__version__}")
        self.sidebar.show_board(board)
        self.set_mode("prepare", refresh=False)
        self.show_plate(self.plate_idx, keep_view=keep_view)
        self.statusBar().showMessage(f"Loaded {path}", 4000)
        return True

    def _recheck(self):
        """Re-run the slicer checks for every plate (cheap) after anything changes."""
        self.checks = [slice_plate(self.board, p, self.project) for p in self.plates]

    def _settings_changed(self):
        try:
            self.project.save()
        except OSError as e:
            self.statusBar().showMessage(f"Couldn't save settings next to the board: {e}", 8000)
        had = bool(self.sliced)
        self.sliced = {}  # settings changed: slices are out of date
        self._recheck()
        self.set_mode("prepare", refresh=False)
        self.show_plate(self.plate_idx, keep_view=True)
        if had:
            self.statusBar().showMessage("Settings changed: slice again to update the preview", 6000)

    # ---- plates and modes ------------------------------------------------------
    def show_plate(self, idx: int, keep_view: bool = False):
        if not self.plates:
            return
        self.plate_idx = idx
        plate = self.plates[idx]
        self.plate_btns[idx].setChecked(True)
        if self.mode == "preview" and idx not in self.sliced:
            self.mode = "prepare"
        self.view.set_plate(plate, keep_view=keep_view)
        self.view.set_labels(self.btn_labels.isChecked())
        self.view.set_grid(self.btn_grid.isChecked())
        self.sidebar.show_plate(self.board, plate, self.checks[idx], self.project)
        self.view.set_excluded({i for i, p in enumerate(plate.parts)
                                if p.key in self.project.excluded and not p.dnp})
        self._show_alignment()
        self.view_note.setText("Seen from below: mirrored compared with KiCad's view"
                               if plate.side == "bottom" else "")
        self._set_plate_buttons()
        self._apply_mode()

    def set_mode(self, mode: str, refresh: bool = True):
        if mode == "preview" and self.plate_idx not in self.sliced:
            mode = "prepare"
        self.mode = mode
        if refresh:
            self._apply_mode()

    def _show_alignment(self):
        if not self.plates:
            return
        preview = self.mode == "preview" and self.plate_idx in self.sliced
        res = self.sliced[self.plate_idx] if preview else self.checks[self.plate_idx]
        picking = self.sidebar.pick_btn.isChecked() and not preview
        self.view.set_alignment([(a.name, a.cand) for a in res.alignment], res.align_candidates,
                                self.project.align_clearance, picking)

    def _apply_mode(self):
        preview = self.mode == "preview" and self.plate_idx in self.sliced
        if preview and self.sidebar.pick_btn.isChecked():
            self.sidebar.pick_btn.setChecked(False)
        (self.tab_preview if preview else self.tab_prepare).setChecked(True)
        self.side_stack.setCurrentIndex(1 if preview else 0)
        self.slider_panel.setVisible(preview)
        if preview:
            res = self.sliced[self.plate_idx]
            self.preview_side.show_result(self.board, res)
            self.view.set_preview([p.part_index for p in res.placements], res.renamed,
                                  {p.part_index for p in res.placements if p.skip})
            n = len(res.placements)
            self.slider.blockSignals(True)
            self.slider.setMaximum(n)
            self.slider.setValue(n)
            self.slider.blockSignals(False)
            self._on_step(n)
        else:
            self.view.set_preview(None)
        self._show_alignment()
        self._update_buttons()

    # ---- slicing / export --------------------------------------------------------
    def slice_current(self):
        if not self.plates:
            return
        plate = self.plates[self.plate_idx]
        res = slice_plate(self.board, plate, self.project)
        self.checks[self.plate_idx] = res
        if not res.ok:
            self.set_mode("prepare", refresh=False)
            self.show_plate(self.plate_idx, keep_view=True)
            msgs = "\n\n".join("• " + i.message for i in res.errors)
            QMessageBox.warning(self, "Can't slice yet", f"{plate.title} has problems to fix first:\n\n{msgs}")
            return
        self.sliced[self.plate_idx] = res
        self.mode = "preview"
        self._set_plate_buttons()
        self._apply_mode()
        n_skip = sum(1 for p in res.placements if p.skip)
        self.statusBar().showMessage(f"{plate.title}: {len(res.placements) - n_skip} placements"
                                     + (f" (+{n_skip} skip)" if n_skip else "")
                                     + ". Step through them with the slider, then Export job…", 6000)

    def export_current(self):
        res = self.sliced.get(self.plate_idx)
        if res is None or self.board is None:
            return
        name = default_filename(self.board, res.plate.side)
        start = os.path.join(self.settings.value("last_export_dir", "") or os.path.dirname(self.board.path), name)
        path, _ = QFileDialog.getSaveFileName(self, f"Export job for {res.plate.title}", start,
                                              "pnp job (*.job.json);;JSON (*.json)")
        if not path:
            return
        try:
            job = build_job(self.board, res)
            write_job(path, job)
        except Exception as e:
            QMessageBox.warning(self, "Couldn't export", str(e))
            return
        self.settings.setValue("last_export_dir", os.path.dirname(path))
        self.statusBar().showMessage(f"Saved {path}", 8000)

    def edit_heights(self):
        if not self.plates:
            return
        dlg = HeightsDialog(self.board, self.plates, self.project, self)
        if dlg.exec() == QDialog.Accepted:
            self._settings_changed()

    def _on_auto_number(self, on: bool):
        if self.board is None:
            return
        self.project.auto_number = on
        self._settings_changed()

    # ---- excluding parts ----------------------------------------------------------
    def set_excluded(self, keys, exclude: bool):
        """Exclude (or include again) parts by footprint key; saved per board."""
        keys = set(keys)
        before = set(self.project.excluded)
        if exclude:
            self.project.excluded |= keys
        else:
            self.project.excluded -= keys
        if self.project.excluded != before:
            self._settings_changed()

    def _include_all(self):
        if self.plates:
            self.set_excluded({p.key for p in self.plates[self.plate_idx].parts}, False)

    def _on_part_check(self, item: QTableWidgetItem):
        if item.column() != 0 or not (item.flags() & Qt.ItemIsUserCheckable) or not self.plates:
            return
        part = self.plates[self.plate_idx].parts[item.data(Qt.UserRole)]
        want_excluded = item.checkState() == Qt.Unchecked
        if want_excluded != (part.key in self.project.excluded):
            self.set_excluded({part.key}, want_excluded)

    def _on_table_menu(self, pos):
        row = self.sidebar.table.rowAt(pos.y())
        if row >= 0:
            self._part_menu(self.sidebar.index_at_row(row), self.sidebar.table.viewport().mapToGlobal(pos))

    def _part_menu(self, idx: int, global_pos):
        """Right-click menu for a part (or empty board when idx is -1)."""
        if not self.plates:
            return
        plate = self.plates[self.plate_idx]
        menu = QMenu(self)
        if 0 <= idx < len(plate.parts):
            part = plate.parts[idx]
            if part.dnp:
                a = menu.addAction(f"{part.ref} is do-not-populate in KiCad")
                a.setEnabled(False)
            elif part.key in self.project.excluded:
                menu.addAction(f"Include {part.ref}", lambda: self.set_excluded({part.key}, False))
            else:
                menu.addAction(f"Exclude {part.ref}", lambda: self.set_excluded({part.key}, True))
            same = [p for p in plate.parts if p.package == part.package and not p.dnp]
            keys = {p.key for p in same}
            n_ex = len(keys & self.project.excluded)
            menu.addSeparator()
            if n_ex < len(same):
                menu.addAction(f"Exclude all {len(same)} × {part.package} on this plate",
                               lambda: self.set_excluded(keys, True))
            if n_ex:
                menu.addAction(f"Include all {len(same)} × {part.package} on this plate",
                               lambda: self.set_excluded(keys, False))
        plate_keys = {p.key for p in plate.parts}
        if plate_keys & self.project.excluded:
            menu.addSeparator()
            menu.addAction("Include everything on this plate", self._include_all)
        if menu.isEmpty():
            return
        menu.exec(global_pos if global_pos is not None else QCursor.pos())

    # ---- alignment ---------------------------------------------------------------
    def _on_align_count(self, n: int):
        if self.board is None:
            return
        self.project.align_count = n
        self._settings_changed()

    def _on_align_clear(self, c: float):
        if self.board is None:
            return
        self.project.align_clearance = round(c, 3)
        self._settings_changed()

    def _on_pick_mode(self, on: bool):
        if not self.plates:
            self.sidebar.pick_btn.setChecked(False)
            return
        if on:
            if self.mode == "preview":
                self.set_mode("prepare")
            side = self.plates[self.plate_idx].side
            if not self.project.alignment.get(side):  # start from the automatic choice
                self.project.alignment[side] = [a.cand.key for a in self.checks[self.plate_idx].alignment]
                self._settings_changed()
            self.statusBar().showMessage("Click pads to add or remove them (2-4). Green = distinct, "
                                         "red = has a look-alike nearby. Click “Pick by hand” again when done.")
        else:
            self.statusBar().clearMessage()
        self._show_alignment()

    def _on_align_auto(self):
        if not self.plates:
            return
        self.sidebar.pick_btn.setChecked(False)
        self.project.alignment.pop(self.plates[self.plate_idx].side, None)
        self._settings_changed()

    def _on_align_pad_clicked(self, key: str):
        side = self.plates[self.plate_idx].side
        keys = list(self.project.alignment.get(side, []))
        if key in keys:
            keys.remove(key)
        elif len(keys) >= 4:
            self.statusBar().showMessage("4 pads is the most: click one of the picked pads to remove it first.",
                                         5000)
            return
        else:
            keys.append(key)
        self.project.alignment[side] = keys
        self._settings_changed()

    def _on_align_pad_hovered(self, key: str):
        if not key:
            self.st_part.setText("")
            return
        c = next((c for c in self.checks[self.plate_idx].align_candidates if c.key == key), None)
        if c:
            self.st_part.setText(c.describe(self.project.align_clearance))

    # ---- events ----------------------------------------------------------------
    def _on_step(self, step: int):
        res = self.sliced.get(self.plate_idx)
        if res is None:
            return
        n = len(res.placements)
        self.view.set_step(step)
        self.step_top.setText(f"{step}\n/ {n}")
        self.preview_side.select_step(step)
        if 1 <= step <= n:
            p = res.placements[step - 1]
            self.st_part.setText(f"#{p.order}  {p.ref}  ·  {p.part.package}  ·  X {p.part.x:.3f}  "
                                 f"Y {p.part.y:.3f}  rot {p.part.rot:g}°  ·  h {p.height:g} mm")

    def _nudge_step(self, d: int):
        if self.mode == "preview":
            self.slider.setValue(self.slider.value() + d)

    def _on_order_select(self):
        rows = self.preview_side.table.selectionModel().selectedRows()
        if rows:
            self.slider.setValue(rows[0].row() + 1)

    def _on_cursor(self, x: float, y: float):
        self.st_cursor.setText(f"X {x:8.3f}   Y {y:8.3f} mm")

    def _on_hover(self, idx: int):
        if idx < 0 or not self.plates:
            if self.mode != "preview":
                self.st_part.setText("")
            return
        p = self.plates[self.plate_idx].parts[idx]
        self.st_part.setText(f"{p.ref}  {p.value}  ·  {p.package}  ·  "
                             f"X {p.x:.3f}  Y {p.y:.3f}  rot {p.rot:g}°")

    def _on_view_select(self, idx: int):
        if self.mode == "preview":
            res = self.sliced.get(self.plate_idx)
            if res and idx >= 0:
                step = next((p.order for p in res.placements if p.part_index == idx), None)
                if step:
                    self.slider.setValue(step)
            return
        self.sidebar.select_index(idx)

    def _on_table_select(self):
        self.view.select_part(self.sidebar.selected_index(), center=True)

    def _on_problem_click(self, item: QListWidgetItem):
        issue = self.sidebar.issue_at(self.sidebar.problems.row(item))
        if not issue or not issue.refs or not self.plates:
            return
        parts = self.plates[self.plate_idx].parts
        idx = next((i for i, p in enumerate(parts) if p.ref in issue.refs or p.package in issue.refs), -1)
        if idx >= 0:
            self.sidebar.select_index(idx)
            self.view.select_part(idx, center=True)

    def dragEnterEvent(self, e):
        if any(u.toLocalFile().lower().endswith(".kicad_pcb") for u in e.mimeData().urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.toLocalFile().lower().endswith(".kicad_pcb"):
                self.load(u.toLocalFile())
                break

    def closeEvent(self, e):
        self.settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(e)