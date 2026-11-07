"""Petites primitives de formulaires et validation, sans widgets par article."""

from functools import wraps

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from ..local_services import resolve_portable_path
from .widgets import button, label


def action(function):
    @wraps(function)
    def guarded(self, *args, **kwargs):
        try:
            return function(self, *args, **kwargs)
        except Exception as exc:
            self.window.report_error(exc)
            return False

    return guarded


def selected_row(view, model):
    rows = view.selectionModel().selectedRows()
    return (
        model.rows[rows[0].row()] if rows and rows[0].row() < len(model.rows) else None
    )


def open_document(value):
    path = resolve_portable_path(value)
    if not path.is_file():
        raise ValueError(
            "Ce document n'est pas disponible localement. Synchronisez le poste ou rattachez-le à nouveau."
        )
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


class Fields:
    def __init__(self, layout):
        self.widgets = {}
        self.form = QFormLayout()
        layout.addLayout(self.form)

    def add(self, title, key, *, multiline=False, check=False):
        widget = (
            QCheckBox(title)
            if check
            else QPlainTextEdit()
            if multiline
            else QLineEdit()
        )
        widget.setAccessibleName(title)
        if multiline:
            widget.setMaximumHeight(125)
        self.widgets[key] = widget
        self.form.addRow("" if check else title, widget)
        return widget

    def values(self):
        return {
            key: ("1" if w.isChecked() else "0")
            if isinstance(w, QCheckBox)
            else w.toPlainText().strip()
            if isinstance(w, QPlainTextEdit)
            else w.text().strip()
            for key, w in self.widgets.items()
        }

    def load(self, values):
        for key, w in self.widgets.items():
            value = str(values.get(key) or "")
            w.blockSignals(True)
            if isinstance(w, QCheckBox):
                w.setChecked(value == "1")
            elif isinstance(w, QPlainTextEdit):
                w.setPlainText(value)
            else:
                w.setText(value)
            w.blockSignals(False)


class FormDialog(QDialog):
    def __init__(self, window, title):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(title)
        self.setMinimumWidth(540)
        self.body = QVBoxLayout(self)
        self.body.setSpacing(12)
        self.body.addWidget(label(title, "heading"))
        self.fields = Fields(self.body)

    def actions(self, callback):
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Annuler", self.reject))
        row.addWidget(button("Enregistrer", callback, "primary"))
        self.body.addLayout(row)
