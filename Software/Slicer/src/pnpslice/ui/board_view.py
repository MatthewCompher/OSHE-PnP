"""2D plate view: the board in job coordinates, zoom/pan, hover and select.

Scene units are millimetres. Qt's scene Y points down, so a job point
(x, y) is drawn at scene (x, -y): job +Y is up the screen, the origin is the
board's lower-left corner, exactly as the job file describes it.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QTransform)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView, QStyleOptionGraphicsItem

from ..plate import JobPad, JobPart, Plate
from . import theme

# pixels per mm above which fine details appear
LOD_LABELS = 14.0
LOD_GRID_1MM = 7.0


def _cosmetic(color, width=1.0) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCosmetic(True)
    return pen


def _pad_path(pad: JobPad) -> QPainterPath:
    """Pad outline centred at (0, 0), unrotated, in mm (scene orientation)."""
    w, h = pad.w, pad.h
    path = QPainterPath()
    rect = QRectF(-w / 2, -h / 2, w, h)
    if pad.shape == "circle":
        path.addEllipse(QPointF(0, 0), w / 2, w / 2)
    elif pad.shape == "oval":
        r = min(w, h) / 2
        path.addRoundedRect(rect, r, r)
    elif pad.shape == "roundrect" and pad.roundrect_rratio:
        r = min(w, h) * pad.roundrect_rratio
        path.addRoundedRect(rect, r, r)
    else:  # rect, trapezoid, chamfered_rect, custom -> rectangle is close enough to look at
        path.addRect(rect)
    return path


class PartItem(QGraphicsItem):
    """All copper pads of one part plus its pick-point marker."""

    def __init__(self, index: int, part: JobPart):
        super().__init__()
        self.index = index
        self.part = part
        self.hovered = False
        self.show_label = True
        self.state = None        # preview: None (prepare) | "placed" | "current" | "pending" | "skip"
        self.excluded = False    # prepare: un-included by the user
        self.skipped = False     # preview: in the job with skip
        self.order_no = 0        # preview: 1-based placement number
        self.job_ref = part.ref  # preview: reference as written to the job
        self.setPos(part.x, -part.y)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        self.setToolTip(self.tooltip_text())

        multi_pin = len(part.pads) > 2
        self.pads = QPainterPath()
        self.pin1 = QPainterPath()
        for pad in part.pads:
            t = QTransform()
            t.translate(pad.x - part.x, -(pad.y - part.y))
            t.rotate(-pad.angle)  # job angles are CCW; Qt's rotate() is clockwise on screen
            path = t.map(_pad_path(pad))
            if multi_pin and pad.number == "1":
                self.pin1.addPath(path)
            else:
                self.pads.addPath(path)
        both = QPainterPath(self.pads)
        both.addPath(self.pin1)
        self._body = both.boundingRect().adjusted(-0.15, -0.15, 0.15, 0.15)
        self._bounds = self._body.adjusted(-0.6, -0.6, 0.6, 0.6)

    def tooltip_text(self) -> str:
        p = self.part
        head = f"#{self.order_no} &nbsp; " if getattr(self, "order_no", 0) else ""
        txt = (f"{head}<b>{p.ref}</b> &nbsp; {p.value}<br>{p.package}<br>"
               f"X {p.x:.3f} &nbsp; Y {p.y:.3f} mm &nbsp; rot {p.rot:g}°")
        if getattr(self, "excluded", False):
            txt += f"<br><span style='color:{theme.WARN}'>excluded: in the job with skip, not placed</span>"
        elif p.dnp:
            txt += f"<br><span style='color:{theme.WARN}'>do not populate (KiCad): in the job with skip</span>"
        if p.origin_offset > 0.1:
            txt += f"<br><span style='color:{theme.WARN}'>origin is {p.origin_offset:.2f} mm from pad centre</span>"
        return txt

    def boundingRect(self) -> QRectF:
        return self._bounds

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRect(self._body)  # whole body is clickable, even for tiny 0201s
        return path

    def hoverEnterEvent(self, e):
        self.hovered = True
        self.update()
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if isinstance(view, BoardView):
            view.partHovered.emit(self.index)

    def hoverLeaveEvent(self, e):
        self.hovered = False
        self.update()
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if isinstance(view, BoardView):
            view.partHovered.emit(-1)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        lod = option.levelOfDetailFromTransform(painter.worldTransform())  # px per mm
        selected = self.isSelected() or self.state == "current"
        pending = self.state in ("pending", "skip") or (self.state is None and (self.excluded or self.part.dnp))
        painter.setPen(Qt.NoPen)
        if self.state in ("placed", "current"):
            painter.setBrush(theme.BODY_CURRENT if self.state == "current" else theme.BODY_PLACED)
            painter.drawRoundedRect(self._body, 0.08, 0.08)
        painter.setBrush(theme.PAD_PENDING if pending else (theme.PAD_HOVER if self.hovered else theme.PAD))
        painter.drawPath(self.pads)
        if not self.pin1.isEmpty():
            painter.setBrush(theme.PAD_PENDING if pending else theme.PAD_PIN1)
            painter.drawPath(self.pin1)
        if pending and not self.hovered:
            return

        # pick-point cross and orientation tick (+X of the part, rotated by rot)
        r = max(self._body.width(), self._body.height()) / 2
        a = math.radians(self.part.rot)
        painter.setPen(_cosmetic(theme.SELECT if selected else theme.PART_MARK, 1.6 if selected else 1.0))
        c = min(0.25, r * 0.4)
        painter.drawLine(QPointF(-c, 0), QPointF(c, 0))
        painter.drawLine(QPointF(0, -c), QPointF(0, c))
        if selected or lod > LOD_LABELS:
            tip = QPointF(math.cos(a) * r * 0.9, -math.sin(a) * r * 0.9)
            painter.drawLine(QPointF(0, 0), tip)

        if selected:
            painter.setPen(_cosmetic(theme.SELECT, 2.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._body)

        label = self.part.ref if self.state is None else f"#{self.order_no} {self.job_ref}"
        if self.state is not None:
            if self.skipped:
                label += " (skip)"
        elif self.part.dnp:
            label += " (DNP)"
        elif self.excluded:
            label += " (excluded)"
        if self.state == "current":  # always label the part being placed
            painter.save()
            painter.scale(1 / lod, 1 / lod)
            f = QFont()
            f.setPixelSize(13)
            f.setBold(True)
            painter.setFont(f)
            br = self._body
            box = QRectF(br.left() * lod - 80, br.top() * lod - 22, br.width() * lod + 160, 18)
            painter.setPen(theme.SELECT)
            painter.drawText(box, Qt.AlignHCenter | Qt.AlignBottom, label)
            painter.restore()
        elif self.show_label and lod > LOD_LABELS:
            painter.save()
            painter.scale(1 / lod, 1 / lod)  # draw text in screen pixels
            f = QFont()
            f.setPixelSize(11)
            painter.setFont(f)
            painter.setPen(theme.LABEL)
            br = self._body
            box = QRectF(br.left() * lod - 40, br.bottom() * lod + 1, br.width() * lod + 80, 14)
            painter.drawText(box, Qt.AlignHCenter | Qt.AlignTop, label)
            painter.restore()


class AlignOverlay(QGraphicsItem):
    """Alignment pads (ringed and lettered) and, in pick mode, every candidate pad."""

    def __init__(self, width: float, height: float):
        super().__init__()
        self.setZValue(20)
        self.rect = QRectF(-30, -(height + 30), width + 60, height + 60)
        self.picks = []          # [(name, cand)]
        self.cands = []          # [AlignCandidate]
        self.tolerance = 1.0
        self.pick_mode = False
        self.hover_key = None
        self.step = None         # preview step, or None
        self._paths = {}

    def boundingRect(self) -> QRectF:
        return self.rect

    def shape(self) -> QPainterPath:
        return QPainterPath()  # draw-only: never hit by clicks, so parts underneath stay clickable

    def _pad_path(self, c) -> QPainterPath:
        p = self._paths.get(c.key)
        if p is None:
            t = QTransform()
            t.translate(c.x, -c.y)
            t.rotate(-c.angle)
            p = t.map(_pad_path(JobPad(c.pad, c.shape, c.x, c.y, c.angle, c.w, c.h, c.roundrect_rratio)))
            self._paths[c.key] = p
        return p

    def set_data(self, picks, cands, tolerance: float, pick_mode: bool):
        self.picks, self.cands, self.tolerance, self.pick_mode = picks, cands, tolerance, pick_mode
        self._paths = {}
        self.update()

    def paint(self, painter: QPainter, option, widget=None):
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        if self.pick_mode:
            for c in self.cands:
                col = QColor(theme.CAND_OK if c.distinct(self.tolerance) else theme.CAND_BAD)
                hot = c.key == self.hover_key
                painter.setPen(_cosmetic(QColor(255, 255, 255) if hot else col, 2.5 if hot else 1.0))
                col.setAlpha(230 if hot else 150)
                painter.setBrush(col)
                painter.drawPath(self._pad_path(c))
        for name, c in self.picks:
            covered = self.step is not None and c.covered_at is not None and c.covered_at <= self.step
            col = theme.ALIGN_COVERED if covered else theme.ALIGN
            painter.setPen(_cosmetic(col, 2.0))
            fill = QColor(col)
            fill.setAlpha(90)
            painter.setBrush(fill)
            painter.drawPath(self._pad_path(c))
            painter.save()
            painter.translate(c.x, -c.y)
            painter.scale(1 / lod, 1 / lod)
            r = 15
            painter.setPen(QPen(col, 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QPointF(0, 0), r, r)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                painter.drawLine(QPointF(dx * (r - 5), dy * (r - 5)), QPointF(dx * (r + 5), dy * (r + 5)))
            f = QFont()
            f.setPixelSize(14)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(QRectF(r - 2, -r - 16, 30, 18), Qt.AlignLeft | Qt.AlignBottom, name)
            painter.restore()


class GridItem(QGraphicsItem):
    """1 mm / 5 mm grid over the board area, plus the origin axes."""

    def __init__(self, width: float, height: float):
        super().__init__()
        self.w, self.h = width, height
        self.margin = 5.0
        self.setZValue(-5)
        self.show_grid = True

    def boundingRect(self) -> QRectF:
        m = self.margin
        return QRectF(-m, -(self.h + m), self.w + 2 * m, self.h + 2 * m)

    def paint(self, painter: QPainter, option, widget=None):
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        m = self.margin
        x0, x1 = -m, self.w + m
        y0, y1 = -m, self.h + m
        if self.show_grid:
            step = 1.0 if lod > LOD_GRID_1MM else 5.0
            for minor in (True, False):
                s = step if minor else 10.0
                if not minor and step == 10.0:
                    continue
                painter.setPen(_cosmetic(theme.GRID_MINOR if minor else theme.GRID_MAJOR))
                k = math.ceil(x0 / s)
                while k * s <= x1:
                    painter.drawLine(QPointF(k * s, -y0), QPointF(k * s, -y1))
                    k += 1
                k = math.ceil(y0 / s)
                while k * s <= y1:
                    painter.drawLine(QPointF(x0, -k * s), QPointF(x1, -k * s))
                    k += 1

        # origin axes, constant size on screen
        painter.save()
        painter.scale(1 / lod, 1 / lod)
        L = 46
        for color, dx, dy, label in ((theme.AXIS_X, L, 0, "X"), (theme.AXIS_Y, 0, -L, "Y")):
            painter.setPen(QPen(color, 2))
            painter.drawLine(QPointF(0, 0), QPointF(dx, dy))
            ux, uy = (dx / L, dy / L)
            head = QPolygonF([QPointF(dx, dy),
                              QPointF(dx - 8 * ux - 4 * uy, dy - 8 * uy + 4 * ux),
                              QPointF(dx - 8 * ux + 4 * uy, dy - 8 * uy - 4 * ux)])
            painter.setBrush(color)
            painter.drawPolygon(head)
            f = QFont()
            f.setPixelSize(12)
            f.setBold(True)
            painter.setFont(f)
            painter.drawText(QPointF(dx + (6 if dx else -4), dy + (4 if dx else -6)), label)
        painter.setPen(theme.LABEL)
        f = QFont()
        f.setPixelSize(11)
        painter.setFont(f)
        painter.drawText(QPointF(-10, 16), "0,0")
        painter.restore()


class BoardView(QGraphicsView):
    partSelected = Signal(int)     # index into plate.parts, -1 = none
    partHovered = Signal(int)
    partMenuRequested = Signal(int, QPoint)  # right-click (no drag): part index or -1, global position
    alignPadClicked = Signal(str)  # pick mode: candidate key
    alignPadHovered = Signal(str)  # pick mode: candidate key, "" = none
    cursorMoved = Signal(float, float)  # job mm
    zoomChanged = Signal(float)    # px per mm

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setBackgroundBrush(QColor(theme.VIEW_BG))
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setFrameShape(QGraphicsView.NoFrame)
        # right button pans when dragged and opens our menu when clicked (see mouseReleaseEvent)
        self.setContextMenuPolicy(Qt.PreventContextMenu)
        self.viewport().setContextMenuPolicy(Qt.PreventContextMenu)
        self.plate: Plate | None = None
        self.items_by_index: list[PartItem] = []
        self.grid: GridItem | None = None
        self._pan_from = None
        self._labels = True
        self._order: list[int] = []
        self._skips: set[int] = set()
        self._path_item = None
        self.align: AlignOverlay | None = None
        self.pick_mode = False
        self.scene().selectionChanged.connect(self._on_selection)

    # ---- content -------------------------------------------------------------
    def set_plate(self, plate: Plate | None, keep_view: bool = False):
        old = self.transform()
        self.scene().clear()
        self.items_by_index = []
        self.grid = None
        self._order = []
        self._path_item = None
        self.align = None
        self.plate = plate
        if plate is None:
            self.viewport().update()
            return

        board = QPainterPath()
        board.addPolygon(QPolygonF([QPointF(x, -y) for x, y in plate.outline]))
        board.closeSubpath()
        for hole in plate.holes:
            board.addPolygon(QPolygonF([QPointF(x, -y) for x, y in hole]))
            board.closeSubpath()
        board.setFillRule(Qt.OddEvenFill)
        item = self.scene().addPath(board, _cosmetic(theme.BOARD_EDGE, 1.5), QBrush(QColor(theme.BOARD_FILL)))
        item.setZValue(-10)

        self.grid = GridItem(plate.width, plate.height)
        self.scene().addItem(self.grid)

        for i, part in enumerate(plate.parts):
            pi = PartItem(i, part)
            pi.show_label = self._labels
            self.scene().addItem(pi)
            self.items_by_index.append(pi)

        self.align = AlignOverlay(plate.width, plate.height)
        self.scene().addItem(self.align)

        m = 20.0
        self.scene().setSceneRect(QRectF(-m, -(plate.height + m), plate.width + 2 * m, plate.height + 2 * m))
        if keep_view:
            self.setTransform(old)
        else:
            self.fit()

    # ---- preview ---------------------------------------------------------------
    def set_preview(self, order: list[int] | None, refs: dict[int, str] | None = None,
                    skips: set[int] | None = None):
        """Enter preview with ``order`` (part indices in placement order), or leave it (None).

        ``skips``: part indices that are do-not-populate (in the job with skip, never placed).
        """
        self._order = order or []
        self._skips = skips or set()
        if self._path_item is not None:
            self.scene().removeItem(self._path_item)
            self._path_item = None
        for it in self.items_by_index:
            it.state = None
            it.skipped = False
            it.order_no = 0
            it.job_ref = it.part.ref
        if self.align:
            self.align.step = None
            self.align.update()
        if order:
            for n, idx in enumerate(order, start=1):
                it = self.items_by_index[idx]
                it.order_no = n
                it.skipped = idx in self._skips
                it.job_ref = (refs or {}).get(idx, it.part.ref)
                it.setToolTip(it.tooltip_text())
            self._path_item = self.scene().addPath(QPainterPath(), _cosmetic(theme.TRAVEL, 1.0))
            self._path_item.setZValue(5)
            self.set_step(len(order))
        else:
            for it in self.items_by_index:
                it.setToolTip(it.tooltip_text())
                it.update()

    def set_step(self, step: int):
        """Show the first ``step`` placements as done; part number ``step`` is the current one."""
        if not self._order:
            return
        step = max(0, min(step, len(self._order)))
        if self.align:
            self.align.step = step
            self.align.update()
        for n, idx in enumerate(self._order, start=1):
            it = self.items_by_index[idx]
            if idx in self._skips:
                it.state = "current" if n == step else "skip"
            else:
                it.state = "placed" if n < step else ("current" if n == step else "pending")
            it.update()
        if self._path_item is not None:
            path = QPainterPath()
            pts = [self.items_by_index[i].pos() for i in self._order[:step] if i not in self._skips]
            if pts:
                path.moveTo(pts[0])
                for p in pts[1:]:
                    path.lineTo(p)
            self._path_item.setPath(path)

    # ---- alignment ---------------------------------------------------------------
    def set_alignment(self, picks, cands, tolerance: float, pick_mode: bool):
        """picks: [(name, AlignCandidate)]; cands: all candidates (drawn in pick mode)."""
        self.pick_mode = pick_mode
        for it in self.items_by_index:  # parts don't take clicks while picking pads
            it.setAcceptedMouseButtons(Qt.NoButton if pick_mode else Qt.AllButtons)
            it.setAcceptHoverEvents(not pick_mode)
        if self.align:
            self.align.set_data(picks, cands, tolerance, pick_mode)
        self.viewport().setCursor(Qt.CrossCursor if pick_mode else Qt.ArrowCursor)

    def _cand_at(self, scene_pt) -> str:
        if not self.align or not self.align.cands:
            return ""
        x, y = scene_pt.x(), -scene_pt.y()
        reach = max(0.6, 10 / max(self.transform().m11(), 1e-6))
        best, key = reach, ""
        for c in self.align.cands:
            d = math.hypot(c.x - x, c.y - y) - max(c.w, c.h) / 2
            if d < best:
                best, key = d, c.key
        return key

    def set_excluded(self, indices: set[int]):
        """Grey out parts the user excluded (prepare view)."""
        for i, it in enumerate(self.items_by_index):
            ex = i in indices
            if it.excluded != ex:
                it.excluded = ex
                it.setToolTip(it.tooltip_text())
                it.update()

    def set_labels(self, on: bool):
        self._labels = on
        for it in self.items_by_index:
            it.show_label = on
            it.update()

    def set_grid(self, on: bool):
        if self.grid:
            self.grid.show_grid = on
            self.grid.update()

    # ---- view ---------------------------------------------------------------
    def fit(self):
        if not self.plate:
            return
        m = 3.0
        r = QRectF(-m, -(self.plate.height + m), self.plate.width + 2 * m, self.plate.height + 2 * m)
        self.fitInView(r, Qt.KeepAspectRatio)
        self.zoomChanged.emit(self.transform().m11())

    def zoom_by(self, factor: float):
        cur = self.transform().m11()
        factor = max(0.5 / cur, min(factor, 2000 / cur))
        self.scale(factor, factor)
        self.zoomChanged.emit(self.transform().m11())

    def select_part(self, index: int, center: bool = True):
        self.scene().blockSignals(True)
        self.scene().clearSelection()
        if 0 <= index < len(self.items_by_index):
            it = self.items_by_index[index]
            it.setSelected(True)
            if center:
                self.centerOn(it)
        self.scene().blockSignals(False)
        self.viewport().update()

    def _on_selection(self):
        sel = [i for i in self.scene().selectedItems() if isinstance(i, PartItem)]
        self.partSelected.emit(sel[0].index if sel else -1)

    # ---- input --------------------------------------------------------------
    def wheelEvent(self, e):
        self.zoom_by(1.0015 ** e.angleDelta().y())

    def mousePressEvent(self, e):
        if self.pick_mode and e.button() == Qt.LeftButton:
            key = self._cand_at(self.mapToScene(e.position().toPoint()))
            if key:
                self.alignPadClicked.emit(key)
                e.accept()
                return
        over_part = self._part_at(e.position().toPoint()) is not None
        if e.button() in (Qt.MiddleButton, Qt.RightButton) or (e.button() == Qt.LeftButton and not over_part):
            self._pan_from = e.position()
            self._pan_moved = False
            self.viewport().setCursor(Qt.ClosedHandCursor)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        p = self.mapToScene(e.position().toPoint())
        self.cursorMoved.emit(p.x(), -p.y())
        if self.pick_mode and self.align and self._pan_from is None:
            key = self._cand_at(p)
            if key != self.align.hover_key:
                self.align.hover_key = key
                self.align.update()
                self.alignPadHovered.emit(key)
        if self._pan_from is not None:
            d = e.position() - self._pan_from
            if abs(d.x()) + abs(d.y()) > 2:
                self._pan_moved = True
            self._pan_from = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pan_from is not None:
            self._pan_from = None
            self.viewport().setCursor(Qt.CrossCursor if self.pick_mode else Qt.ArrowCursor)
            if e.button() == Qt.LeftButton and not self._pan_moved:
                self.scene().clearSelection()  # click on empty board = deselect
            elif e.button() == Qt.RightButton and not self._pan_moved:
                it = self._part_at(e.position().toPoint())
                self.partMenuRequested.emit(it.index if it else -1, e.globalPosition().toPoint())
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def _part_at(self, pos) -> "PartItem | None":
        for it in self.items(pos):
            if isinstance(it, PartItem):
                return it
        return None

    def mouseDoubleClickEvent(self, e):
        if self._part_at(e.position().toPoint()) is None:
            self.fit()
        else:
            super().mouseDoubleClickEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_F:
            self.fit()
        elif e.key() in (Qt.Key_Plus, Qt.Key_Equal):
            self.zoom_by(1.25)
        elif e.key() == Qt.Key_Minus:
            self.zoom_by(0.8)
        else:
            super().keyPressEvent(e)

    def drawForeground(self, painter: QPainter, rect: QRectF):
        if self.plate is None:
            painter.save()
            painter.resetTransform()
            painter.setPen(QColor(theme.TEXT_DIM))
            f = QFont()
            f.setPixelSize(15)
            painter.setFont(f)
            painter.drawText(self.viewport().rect(), Qt.AlignCenter,
                             "Open a KiCad board (Ctrl+O)\nor drop a .kicad_pcb file here")
            painter.restore()