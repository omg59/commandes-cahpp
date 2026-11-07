"""Fiches fournisseurs et recommandations du moteur 1.6."""

from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..numbers import parse_decimal
from .forms import Fields, action, selected_row
from .models import RowsModel
from .services import currency, number
from .widgets import button, card, label, table


class SuppliersPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.current_id = None
        self.baseline = None
        self.source_updated = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("Fournisseurs", "title"))
        self.query = QLineEdit()
        self.query.setPlaceholderText("Rechercher un fournisseur…")
        self.query.textChanged.connect(self.filter)
        layout.addWidget(self.query)
        split = QSplitter()
        self.model = RowsModel(
            [
                ("Fournisseur", lambda r: r["name"], False),
                ("N° client", lambda r: r["customer_number"], False),
                ("Franco HT", lambda r: currency(r["franco_ht"]), True),
            ]
        )
        self.table = table(self.model)
        self.table.selectionModel().selectionChanged.connect(self.select)
        split.addWidget(self.table)
        box, body = card()
        self.heading = label("Sélectionnez un fournisseur", "heading", True)
        body.addWidget(self.heading)
        self.fields = Fields(body)
        for text, key in [
            ("Numéro client", "customer_number"),
            ("Contact", "contact_name"),
            ("E-mail", "email"),
            ("Téléphone", "phone"),
            ("Adresse", "address"),
            ("Site internet", "website"),
            ("Franco HT (€)", "franco_ht"),
            ("Minimum de commande HT (€)", "minimum_order_ht"),
            ("Notes", "notes"),
        ]:
            self.fields.add(text, key, multiline=key in ("notes", "address"))
        body.addWidget(button("Enregistrer la fiche", self.save, "primary"))
        split.addWidget(box)
        split.setSizes([450, 620])
        layout.addWidget(split, 1)

    def has_unsaved_changes(self):
        return self.baseline is not None and self.fields.values() != self.baseline

    def refresh(self):
        if not self.has_unsaved_changes():
            self.filter()

    def filter(self, *_):
        if self.has_unsaved_changes():
            return
        query = self.query.text().casefold()
        rows = [
            dict(r)
            for r in self.window.database.list_suppliers()
            if query in r["name"].casefold()
        ]
        old = self.current_id
        self.current_id = None
        self.model.replace(rows)
        if rows:
            self.table.selectRow(
                next((i for i, r in enumerate(rows) if r["id"] == old), 0)
            )
        else:
            self.current_id = None
            self.baseline = None
            self.heading.setText("Aucun fournisseur")

    def select(self, *_):
        row = selected_row(self.table, self.model)
        if not row or row["id"] == self.current_id:
            return
        if self.has_unsaved_changes():
            choice = QMessageBox.question(
                self,
                "Fiche non enregistrée",
                "Enregistrer la fiche fournisseur avant de changer ?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if choice == QMessageBox.StandardButton.Cancel or (
                choice == QMessageBox.StandardButton.Save and not self.save()
            ):
                self.table.selectionModel().blockSignals(True)
                index = next(
                    (
                        i
                        for i, r in enumerate(self.model.rows)
                        if r["id"] == self.current_id
                    ),
                    None,
                )
                if index is not None:
                    self.table.selectRow(index)
                self.table.selectionModel().blockSignals(False)
                return
        self.current_id = row["id"]
        source = dict(self.window.database.get_supplier(self.current_id))
        for key in ("franco_ht", "minimum_order_ht"):
            source[key] = (
                ""
                if source[key] is None
                else number(source[key], 4).rstrip("0").rstrip(",")
            )
        self.fields.load(source)
        self.baseline = self.fields.values()
        self.source_updated = source["updated_at"]
        self.heading.setText(source["name"])

    @action
    def save(self):
        if not self.current_id:
            raise ValueError("Sélectionnez un fournisseur.")
        values = self.fields.values()
        for key in ("franco_ht", "minimum_order_ht"):
            values[key] = (
                float(parse_decimal(values[key], "Montant HT", minimum=0))
                if values[key]
                else None
            )
        with self.window.operations.resource("fournisseur", self.current_id):
            current = self.window.database.get_supplier(self.current_id)
            if current["updated_at"] != self.source_updated:
                raise ValueError(
                    "La fiche a été modifiée depuis son ouverture. Rechargez-la avant d'enregistrer."
                )
            self.window.database.update_supplier(self.current_id, **values)
        self.source_updated = self.window.database.get_supplier(self.current_id)[
            "updated_at"
        ]
        self.baseline = self.fields.values()
        self.window.notify("Fiche fournisseur enregistrée.")
        self.window.data_changed()
        return True


class SuggestionsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label("À recommander", "title"))
        layout.addWidget(
            label(
                "Suggestions selon le rythme des commandes envoyées. Sélectionnez les articles d'un même fournisseur.",
                "muted",
                True,
            )
        )
        self.query = QLineEdit()
        self.query.setPlaceholderText("Filtrer les suggestions…")
        self.query.textChanged.connect(self.filter)
        layout.addWidget(self.query)
        self.rows = []
        self.model = RowsModel(
            [
                (
                    "Article / fournisseur",
                    lambda r: r["designation"] + "\n" + r["supplier_name"],
                    False,
                ),
                ("Dernière commande", lambda r: r["last_order_date"], False),
                ("Rythme (jours)", lambda r: number(r["average_interval_days"]), True),
                ("Retard (jours)", lambda r: number(r["overdue_days"]), True),
                ("Cartons habituels", lambda r: number(r["usual_cartons"], 3), True),
            ]
        )
        self.table = table(self.model)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(button("Actualiser", self.refresh))
        row.addWidget(button("Préparer avec la sélection", self.prepare, "primary"))
        row.addStretch()
        layout.addLayout(row)
        self.status = label("", "muted")
        layout.addWidget(self.status)

    def refresh(self):
        def work(*, cancel, progress):
            return [dict(r) for r in self.window.database.reorder_suggestions()]

        def done(rows, error):
            if error:
                self.window.report_error(error)
                return
            self.rows = rows
            self.filter()

        self.window.jobs.submit("suggestions", work, done)

    def filter(self, *_):
        query = self.query.text().casefold()
        self.model.replace(
            [
                r
                for r in self.rows
                if query
                in (
                    r["designation"] + r["supplier_name"] + r["supplier_ref"]
                ).casefold()
            ]
        )
        self.status.setText(f"{len(self.model.rows)} suggestion(s)")

    @action
    def prepare(self):
        rows = [
            self.model.rows[i.row()] for i in self.table.selectionModel().selectedRows()
        ]
        if not rows:
            raise ValueError("Sélectionnez au moins un article.")
        if len({r["supplier_id"] for r in rows}) != 1:
            raise ValueError("Sélectionnez les articles d'un seul fournisseur.")
        if not self.window.allow_discard_or_save():
            return
        self.window.prepare.reset()
        for row in rows:
            self.window.add_product(
                self.window.database.get_product(row["product_id"]),
                quantity=row["usual_cartons"] or 1,
            )
        self.window.navigate("prepare")
