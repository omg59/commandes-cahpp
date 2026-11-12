"""Dialogues français ; les validations finales restent dans le moteur métier."""

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from ..numbers import parse_decimal
from .services import number
from .widgets import button, label


class ProductDialog(QDialog):
    def __init__(self, database, product_id, parent=None, *, operations=None):
        super().__init__(parent)
        self.database = database
        self.operations = operations
        self.product = database.get_product(product_id)
        self.saved = False
        self.setWindowTitle("Vérifier / modifier l'article")
        self.setMinimumWidth(510)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(label(self.product["designation"], "heading", True))
        layout.addWidget(
            label(
                self.product["supplier_name"] + " · " + self.product["supplier_ref"],
                "muted",
                True,
            )
        )
        self.fields = {}
        form = QFormLayout()
        for title, key in [
            ("Référence fournisseur", "supplier_ref"),
            ("Désignation", "designation"),
            ("Unités par carton", "conditionnement"),
            ("Détail du conditionnement", "unit_packaging"),
            ("Prix unitaire HT (€)", "unit_price"),
            ("TVA (%)", "vat"),
        ]:
            value = self.product.get(key)
            if key == "conditionnement":
                value = value or self.product["qml"]
            if key in ("conditionnement", "unit_price", "vat"):
                value = (
                    "" if value is None else number(value, 4).rstrip("0").rstrip(",")
                )
            entry = QLineEdit(str(value or ""))
            entry.setAccessibleName(title)
            form.addRow(title, entry)
            self.fields[key] = entry
        layout.addLayout(form)
        self.team_notes = QPlainTextEdit(self.product.get("internal_notes") or "")
        self.team_notes.setMaximumHeight(85)
        self.team_notes.setAccessibleName("Notes internes de l'article")
        form.addRow("Notes internes", self.team_notes)
        self.replacement = QLineEdit(self.product.get("replacement_code_cahpp") or "")
        self.replacement.setAccessibleName("Code CAHPP de remplacement")
        form.addRow("Code CAHPP de remplacement", self.replacement)
        self.confirm = QCheckBox("J'ai vérifié les informations auprès du fournisseur.")
        if self.product["catalog_review_required"]:
            layout.addWidget(
                label(self.product["catalog_review_reason"], "warning", True)
            )
            layout.addWidget(self.confirm)
        self.error = label("", "warning", True)
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button("Annuler", self.reject))
        self.save_button = button("Enregistrer", self.save, "primary")
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

    def save(self):
        try:
            values = {key: widget.text().strip() for key, widget in self.fields.items()}
            if not values["designation"]:
                raise ValueError("La désignation est obligatoire.")
            if self.product["catalog_review_required"] and not self.confirm.isChecked():
                raise ValueError(
                    "Vérifiez les informations puis cochez la confirmation."
                )
            for key, title in [
                ("conditionnement", "Unités par carton"),
                ("unit_price", "Prix unitaire"),
                ("vat", "TVA"),
            ]:
                values[key] = float(
                    parse_decimal(
                        values[key],
                        title,
                        minimum=0,
                        maximum=100 if key == "vat" else None,
                    )
                )
            if values["conditionnement"] <= 0:
                raise ValueError(
                    "Le nombre d'unités par carton doit être supérieur à zéro."
                )
            from contextlib import nullcontext

            guard = (
                self.operations.locked_product(self.product["id"])
                if self.operations
                else nullcontext()
            )
            with guard:
                current = self.database.get_product(self.product["id"])
                if current != self.product:
                    raise ValueError(
                        "Cet article a changé depuis son ouverture. Fermez puis rouvrez la fiche avant de l'enregistrer."
                    )
                if self.product["source"] == "LOCAL":
                    self.database.update_manual_product(self.product["id"], **values)
                else:
                    self.database.set_product_override(
                        self.product["id"],
                        **values,
                        catalog_review_confirmed=self.confirm.isChecked(),
                        reviewed_catalog_token=self.product["catalog_review_token"],
                    )
                self.database.update_product_team_details(
                    self.product["id"],
                    self.team_notes.toPlainText(),
                    self.replacement.text(),
                )
        except ValueError as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.saved = True
        self.accept()
