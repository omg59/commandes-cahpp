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
from .dates import format_date, format_datetime, date_sort_key
from ..numbers import parse_decimal


def date_column(title, key, *, include_time=False):
    formatter = format_datetime if include_time else format_date
    return (
        title,
        lambda row: formatter(row[key]),
        False,
        lambda row: date_sort_key(row[key]),
    )


class RowsModel(QAbstractTableModel):
    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self.columns = columns  # (libellé, affichage, aligné à droite[, clé de tri])
        self.rows = []
        self.sortable = True
        self.sort_column = None
        self.sort_order = Qt.SortOrder.AscendingOrder

    def replace(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        if self.sort_column is not None:
            self._sort_rows()
        self.endResetModel()

    def _sort_rows(self):
        column = self.sort_column

        def key(row):
            if len(self.columns[column]) > 3:
                return self.columns[column][3](row)
            value = self.columns[column][1](row)
            if self.columns[column][2]:
                try:
                    return (
                        0,
                        parse_decimal(
                            str(value)
                            .replace("€", "")
                            .replace("%", "")
                            .replace(" j", "")
                        ),
                    )
                except ValueError:
                    return (1, str(value).casefold())
            return (0, str(value).casefold())

        self.rows.sort(key=key, reverse=self.sort_order == Qt.SortOrder.DescendingOrder)

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if column < 0:
            self.sort_column = None
            return
        if not self.sortable or not 0 <= column < len(self.columns):
            return
        self.beginResetModel()
        self.sort_column, self.sort_order = column, order
        self._sort_rows()
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
    def __init__(self, parent=None, *, order_mode=False):
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
        if order_mode:
            self.columns = [
                ("Référence", lambda p: p["supplier_ref"], False),
                ("Désignation", lambda p: p["designation"], False),
                *self.columns[1:],
            ]
        self.state_column = len(self.columns) - 1

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if (
            index.isValid()
            and index.row() < len(self.rows)
            and role == Qt.ItemDataRole.ForegroundRole
            and index.column() == self.state_column
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
    QUANTITY_COLUMN = 2

    def __init__(self, cart, parent=None):
        super().__init__(
            [
                ("Référence", lambda l: l.supplier_ref, False),
                ("Désignation", lambda l: l.designation, False),
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
        self.sortable = False

    def reload(self):
        self.replace(self.cart.lines)
        self.changed.emit()

    def flags(self, index):
        flags = super().flags(index)
        return (
            flags | Qt.ItemFlag.ItemIsEditable
            if index.isValid() and index.column() == self.QUANTITY_COLUMN
            else flags
        )

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if (
            role == Qt.ItemDataRole.EditRole
            and index.isValid()
            and index.column() == self.QUANTITY_COLUMN
        ):
            return number(self.rows[index.row()].cartons, 3)
        if role == Qt.ItemDataRole.ToolTipRole and index.isValid():
            line = self.rows[index.row()]
            return f"{line.designation}\n{number(line.units_per_carton)} unités/carton · {currency(line.unit_price, 4)} HT/unité"
        return super().data(index, role)

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if (
            not index.isValid()
            or index.column() != self.QUANTITY_COLUMN
            or role != Qt.ItemDataRole.EditRole
        ):
            return False
        try:
            self.cart.set_quantity(index.row(), value)
        except ValueError as exc:
            self.validation_error.emit(str(exc))
            return False
        self.dataChanged.emit(index, self.index(index.row(), 3))
        self.changed.emit()
        return True
