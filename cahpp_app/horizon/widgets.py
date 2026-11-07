"""Composants visuels Qt ; graphiques légers dessinés avec QPainter."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .services import currency, number
from .theme import BLUE, YELLOW, SKY


def label(text="", name="", wrap=False):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setObjectName(name)
    item.setWordWrap(wrap)
    return item


def button(text, callback=None, name=""):
    item = QPushButton(text)
    item.setObjectName(name)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    if callback:
        item.clicked.connect(callback)
    return item


def card(parent=None):
    box = QFrame(parent)
    box.setObjectName("card")
    layout = QVBoxLayout(box)
    layout.setContentsMargins(17, 16, 17, 16)
    layout.setSpacing(10)
    return box, layout


def table(model):
    item = QTableView()
    item.setModel(model)
    if getattr(model, "sortable", False):
        item.setSortingEnabled(True)
        item.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
    item.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
    item.setSelectionMode(QTableView.SelectionMode.SingleSelection)
    item.setShowGrid(False)
    item.verticalHeader().hide()
    item.verticalHeader().setDefaultSectionSize(58)
    item.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    item.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    item.setMinimumHeight(170)
    item.setWordWrap(True)
    return item


class Metric(QFrame):
    def __init__(self, title):
        super().__init__()
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.addWidget(label(title, "muted", True))
        self.value = label("—", "metricValue")
        self.detail = label("Chargement…", "muted", True)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)

    def set_value(self, value, detail=""):
        self.value.setText(str(value))
        self.detail.setText(detail)


class Chart(QWidget):
    selected = Signal(object)

    def __init__(self, kind="line", parent=None):
        super().__init__(parent)
        self.kind = kind
        self.labels = []
        self.values = []
        self.keys = []
        self.hits = []
        self.setMinimumHeight(220)
        self.setMinimumWidth(160)
        self.setMouseTracking(True)
        self.setAccessibleName(
            "Évolution des montants HT"
            if kind == "line"
            else "Montants HT par fournisseur"
        )

    def set_values(self, labels, values, keys=None):
        self.labels = list(labels)
        self.values = [float(v or 0) for v in values]
        self.keys = list(keys or labels)
        self.setAccessibleDescription(
            " ; ".join(
                f"{name} : {currency(value)} HT"
                for name, value in zip(self.labels, self.values)
            )
        )
        if self.kind == "bars":
            self.setMinimumHeight(max(220, min(6, len(self.values)) * 52 + 12))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = QApplication.instance().property("horizonColors") or {
            "text": "#172F50",
            "muted": "#5E7290",
            "border": "#DCE5F0",
        }
        accent = QColor(
            SKY if QApplication.instance().property("horizonDark") else BLUE
        )
        text, muted, grid = [QColor(colors[k]) for k in ("text", "muted", "border")]
        font = self.font()
        font.setPointSize(9)
        painter.setFont(font)
        self.hits = []
        if not self.values or not any(self.values):
            painter.setPen(muted)
            painter.drawText(
                self.rect(),
                int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap),
                "Aucune commande envoyée sur cette période.",
            )
            return
        if self.kind == "bars":
            height = max(43, min(64, (self.height() - 12) / max(len(self.values), 1)))
            for i, (name, value) in enumerate(zip(self.labels[:6], self.values[:6])):
                top = 5 + i * height
                painter.setPen(text)
                title = painter.fontMetrics().elidedText(
                    name, Qt.TextElideMode.ElideRight, max(70, self.width() - 125)
                )
                painter.drawText(
                    QRectF(0, top, self.width(), 21), Qt.AlignmentFlag.AlignLeft, title
                )
                painter.drawText(
                    QRectF(0, top, self.width(), 21),
                    Qt.AlignmentFlag.AlignRight,
                    currency(value),
                )
                track = QRectF(0, top + 29, self.width() - 2, 7)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(grid)
                painter.drawRoundedRect(track, 3, 3)
                painter.setBrush(accent)
                painter.drawRoundedRect(
                    QRectF(
                        track.x(),
                        track.y(),
                        track.width() * value / max(self.values),
                        7,
                    ),
                    3,
                    3,
                )
                self.hits.append((QRectF(0, top, self.width(), height), i))
            return
        area = QRectF(53, 25, max(10, self.width() - 74), max(10, self.height() - 62))
        maximum = max(self.values) * 1.2
        painter.setPen(muted)
        painter.drawText(QRectF(area.x(), 0, 100, 20), "Montant HT (€)")
        for f in (0, 0.5, 1):
            y = area.bottom() - f * area.height()
            painter.setPen(QPen(grid, 1))
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.setPen(muted)
            value = maximum * f
            tick = number(value / 1000, 1) + " k" if value >= 1000 else number(value)
            painter.drawText(
                QRectF(0, y - 10, 45, 20),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                tick,
            )
        points = [
            QPointF(
                area.left() + area.width() * i / max(1, len(self.values) - 1),
                area.bottom() - area.height() * v / maximum,
            )
            for i, v in enumerate(self.values)
        ]
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        fill = QPainterPath(path)
        fill.lineTo(area.right(), area.bottom())
        fill.lineTo(area.left(), area.bottom())
        fill.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(88, 165, 219, 35))
        painter.drawPath(fill)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(accent, 2.5))
        painter.drawPath(path)
        tick_width = max(
            45, max(painter.fontMetrics().horizontalAdvance(t) for t in self.labels) + 8
        )
        step = max(1, math.ceil((len(points) - 1) * tick_width / area.width()))
        last_tick = -1000
        for i, point in enumerate(points):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(YELLOW if i == len(points) - 1 else SKY))
            painter.drawEllipse(point, 4, 4)
            painter.setPen(muted)
            if (
                i % step == 0 or i == len(points) - 1
            ) and point.x() - last_tick >= tick_width:
                last_tick = point.x()
                x = max(0, min(self.width() - 47, point.x() - 23))
                painter.drawText(
                    QRectF(x, area.bottom() + 10, 47, 20),
                    Qt.AlignmentFlag.AlignCenter,
                    self.labels[i],
                )
            self.hits.append((QRectF(point.x() - 16, area.top(), 32, area.height()), i))

    def mouseMoveEvent(self, event):
        for rect, index in self.hits:
            if rect.contains(event.position()):
                self.setToolTip(
                    f"{self.labels[index]} : {currency(self.values[index])} HT"
                )
                return
        self.setToolTip("")

    def mousePressEvent(self, event):
        for rect, index in self.hits:
            if rect.contains(event.position()):
                self.selected.emit(self.keys[index])
                break
