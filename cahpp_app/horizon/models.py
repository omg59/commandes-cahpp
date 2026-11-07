"""Modèles Qt bornés : aucune création de widget par article du catalogue."""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractTableModel,
    QCoreApplication,
    QModelIndex,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor

from .services import currency, number


class RowsModel(QAbstractTableModel):
    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self.columns = columns  # (libellé, fonction d'affichage, aligné à droite)
        self.rows = []

    def replace(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
        ):
            return self.columns[section][0]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self.rows):
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return str(self.columns[index.column()][1](self.rows[index.row()]))
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(
                (
                    Qt.AlignmentFlag.AlignRight
                    if self.columns[index.column()][2]
                    else Qt.AlignmentFlag.AlignLeft
                )
                | Qt.AlignmentFlag.AlignVCenter
            )
        return None


class ProductsModel(RowsModel):
    def __init__(self, parent=None):
        super().__init__(
            [
                (
                    "Désignation / référence",
                    lambda p: (
                        p["designation"]
                        + "\n"
                        + p["supplier_ref"]
                        + " · "
                        + p["supplier_name"]
                    ),
                    False,
                ),
                ("PU HT", lambda p: currency(p["unit_price"], 4), True),
                (
                    "Unités/carton",
                    lambda p: number(p["conditionnement"] or p["qml"]),
                    True,
                ),
                (
                    "État",
                    lambda p: (
                        "Inactif"
                        if not p["active"]
                        else "À vérifier"
                        if p["catalog_review_required"]
                        else "Favori"
                        if p["favorite"]
                        else "Actif"
                    ),
                    False,
                ),
            ],
            parent,
        )

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if (
            index.isValid()
            and index.row() < len(self.rows)
            and role == Qt.ItemDataRole.ForegroundRole
            and index.column() == 3
        ):
            return (
                QColor(
                    "#FFC432"
                    if QCoreApplication.instance().property("horizonDark")
                    else "#9C5B00"
                )
                if self.rows[index.row()]["catalog_review_required"]
                else None
            )
        return super().data(index, role)


class CartModel(RowsModel):
    changed = Signal()
    validation_error = Signal(str)

    def __init__(self, cart, parent=None):
        super().__init__(
            [
                ("Article", lambda l: l.designation, False),
                (
                    "Cartons",
                    lambda l: number(l.cartons, 3).rstrip("0").rstrip(","),
                    True,
                ),
                ("Total HT", lambda l: currency(l.total_ht), True),
            ],
            parent,
        )
        self.cart = cart

    def reload(self):
        self.replace(self.cart.lines)
        self.changed.emit()

    def flags(self, index):
        flags = super().flags(index)
        return (
            flags | Qt.ItemFlag.ItemIsEditable
            if index.isValid() and index.column() == 1
            else flags
        )

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.EditRole and index.isValid() and index.column() == 1:
            return number(self.rows[index.row()].cartons, 3)
        if role == Qt.ItemDataRole.ToolTipRole and index.isValid():
            line = self.rows[index.row()]
            return f"{line.designation}\n{number(line.units_per_carton)} unités/carton · {currency(line.unit_price, 4)} HT/unité"
        return super().data(index, role)

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if (
            not index.isValid()
            or index.column() != 1
            or role != Qt.ItemDataRole.EditRole
        ):
            return False
        try:
            self.cart.set_quantity(index.row(), value)
        except ValueError as exc:
            self.validation_error.emit(str(exc))
            return False
        self.dataChanged.emit(index, self.index(index.row(), 2))
        self.changed.emit()
        return True
