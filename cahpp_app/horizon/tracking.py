"""Réceptions, documents, notes et audit des commandes dans des dialogues Qt."""

from datetime import date
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..local_services import attach_document, remove_document
from ..local_services import resolve_portable_path
from ..paths import DOCUMENTS_DIR
from ..numbers import parse_decimal
from .forms import FormDialog, action, open_document, selected_row
from .models import RowsModel, date_column
from .dates import format_date, parse_date
from .services import number
from .widgets import button, label, table

DOCUMENT_TYPES = (
    "Bon de livraison",
    "Confirmation de commande",
    "Facture",
    "Devis",
    "Avoir",
    "Correspondance",
    "Pièce jointe e-mail",
    "Autre…",
)


class ReceiptModel(RowsModel):
    def flags(self, index):
        flags = super().flags(index)
        return (
            flags | Qt.ItemFlag.ItemIsEditable
            if index.isValid() and index.column() == 3
            else flags
        )

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and index.column() == 3 and role == Qt.ItemDataRole.EditRole:
            return str(self.rows[index.row()]["quantity"])
        return super().data(index, role)

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if (
            role != Qt.ItemDataRole.EditRole
            or not index.isValid()
            or index.column() != 3
        ):
            return False
        try:
            row = self.rows[index.row()]
            quantity = parse_decimal(
                value, "Unités reçues", minimum=0, maximum=row["remaining_units"]
            )
        except ValueError:
            return False
        row["quantity"] = quantity
        self.dataChanged.emit(index, index)
        return True


class ReceiptDialog(FormDialog):
    def __init__(self, window, order_id):
        super().__init__(window, "Enregistrer une réception")
        self.order_id = order_id
        self.resize(900, 650)
        self.fields.add("Date de réception (JJ/MM/AAAA)", "date").setText(
            format_date(date.today())
        )
        self.fields.add("Référence du bon de livraison", "reference")
        self.fields.add("Notes", "notes", multiline=True)
        self.body.addWidget(
            label(
                "Saisir des UNITÉS reçues, pas des cartons. Double-cliquez dans la colonne reçue.",
                "muted",
                True,
            )
        )
        self.model = ReceiptModel(
            [
                ("Article", lambda r: r["designation"], False),
                ("Commandées (unités)", lambda r: number(r["total_units"], 3), True),
                ("Restantes (unités)", lambda r: number(r["remaining_units"], 3), True),
                (
                    "Reçues aujourd'hui (unités)",
                    lambda r: number(r["quantity"], 3),
                    True,
                ),
            ]
        )
        self.model.replace(
            [
                dict(r, quantity=0)
                for r in window.database.receipt_summary(order_id)["lines"]
            ]
        )
        self.table = table(self.model)
        self.body.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(button("Tout le reliquat reçu", partial(self.fill, True)))
        row.addWidget(button("Effacer les quantités", partial(self.fill, False)))
        self.body.addLayout(row)
        self.actions(self.save)

    def fill(self, remaining):
        self.model.replace(
            [
                dict(r, quantity=r["remaining_units"] if remaining else 0)
                for r in self.model.rows
            ]
        )

    @action
    def save(self):
        values = self.fields.values()
        quantities = {r["line_uid"]: r["quantity"] for r in self.model.rows}
        with self.window.operations.locked_order(self.order_id):
            self.window.database.add_receipt(
                self.order_id,
                parse_date(values["date"]),
                quantities,
                reference=values["reference"],
                notes=values["notes"],
            )
        self.window.data_changed()
        self.accept()


class OrderWorkspaceDialog(QDialog):
    def __init__(self, window, order_id, tab=0):
        super().__init__(window)
        self.window = window
        self.order_id = order_id
        self.resize(1120, 800)
        self.setWindowTitle("Suivi de la commande")
        layout = QVBoxLayout(self)
        self.heading = label("", "heading", True)
        layout.addWidget(self.heading)
        top = QHBoxLayout()
        self.expected = QLineEdit()
        self.expected.setPlaceholderText("Date prévue JJ/MM/AAAA (vide pour effacer)")
        self.expected.setAccessibleName("Date de livraison prévue")
        top.addWidget(self.expected)
        top.addWidget(button("Enregistrer la date", self.expected_date))
        self.confirm_button = button("Confirmation fournisseur", self.confirm)
        self.invoice_button = button("Facturation", self.invoice)
        top.addWidget(self.confirm_button)
        top.addWidget(self.invoice_button)
        layout.addLayout(top)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.lines_model = RowsModel(
            [
                (
                    "Article",
                    lambda r: r["designation"] + "\n" + r["supplier_ref"],
                    False,
                ),
                ("Commandées (unités)", lambda r: number(r["total_units"], 3), True),
                ("Reçues (unités)", lambda r: number(r["received_units"], 3), True),
                ("Reliquat (unités)", lambda r: number(r["remaining_units"], 3), True),
            ]
        )
        self.receipts_model = RowsModel(
            [
                (
                    "Bon de livraison",
                    lambda r: r["reference"] or "Sans référence",
                    False,
                ),
                date_column("Date", "receipt_date"),
                ("Unités reçues", lambda r: number(r["total_received"], 3), True),
                ("Saisi par", lambda r: r["received_by"], False),
            ]
        )
        page = QWidget()
        body = QVBoxLayout(page)
        body.addWidget(table(self.lines_model), 1)
        self.receipts_table = table(self.receipts_model)
        body.addWidget(self.receipts_table, 1)
        row = QHBoxLayout()
        row.addWidget(button("Ajouter une réception", self.receipt, "primary"))
        row.addWidget(button("Annuler la réception sélectionnée", self.remove_receipt))
        row.addWidget(button("Déclarer livrée sans détail", self.delivered))
        body.addLayout(row)
        self.tabs.addTab(page, "Réceptions et reliquats")
        page = QWidget()
        body = QVBoxLayout(page)
        self.documents_model = RowsModel(
            [
                ("Document", lambda r: r["display_name"], False),
                ("Type", lambda r: r["kind"], False),
                (
                    "Préparer avec l'e-mail",
                    lambda r: "Oui" if r["include_in_email"] else "Non",
                    False,
                ),
                date_column("Ajouté le", "added_at", include_time=True),
            ]
        )
        self.documents_table = table(self.documents_model)
        self.documents_table.doubleClicked.connect(self.open_attachment)
        body.addWidget(self.documents_table, 1)
        row = QHBoxLayout()
        self.kind = QComboBox()
        self.kind.addItems(DOCUMENT_TYPES)
        self.include = QCheckBox("Joindre à la préparation d'e-mail")
        row.addWidget(self.kind)
        row.addWidget(self.include)
        row.addWidget(button("Ajouter des fichiers…", self.attach, "primary"))
        body.addLayout(row)
        row = QHBoxLayout()
        for text, fn in [
            ("Ouvrir", self.open_attachment),
            ("Modifier les propriétés", self.edit_attachment),
            ("Inclure / exclure de l'e-mail", self.toggle_attachment),
            ("Retirer le document", self.remove_attachment),
        ]:
            row.addWidget(button(text, fn))
        body.addLayout(row)
        self.tabs.addTab(page, "Documents")
        page = QWidget()
        body = QVBoxLayout(page)
        self.comments_model = RowsModel(
            [
                ("Note interne", lambda r: r["body"], False),
                ("Auteur", lambda r: r["author_name"], False),
                date_column("Date", "created_at", include_time=True),
            ]
        )
        self.comments_table = table(self.comments_model)
        body.addWidget(self.comments_table, 1)
        self.comment = QPlainTextEdit()
        self.comment.setPlaceholderText("Nouvelle note interne partagée…")
        self.comment.setMaximumHeight(100)
        body.addWidget(self.comment)
        row = QHBoxLayout()
        row.addWidget(button("Ajouter la note", self.add_comment, "primary"))
        row.addWidget(button("Supprimer la note sélectionnée", self.delete_comment))
        body.addLayout(row)
        self.tabs.addTab(page, "Notes internes")
        page = QWidget()
        body = QVBoxLayout(page)
        self.audit_model = RowsModel(
            [
                ("Action", lambda r: r["action"], False),
                ("Auteur", lambda r: r["actor_name"], False),
                date_column("Date", "occurred_at", include_time=True),
                ("Détail", lambda r: r["details"], False),
            ]
        )
        body.addWidget(table(self.audit_model), 1)
        self.tabs.addTab(page, "Historique des actions")
        self.tabs.setCurrentIndex(tab)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Actualiser", self.refresh))
        row.addWidget(button("Fermer", self.accept))
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        db = self.window.database
        summary = db.receipt_summary(self.order_id)
        order = summary["order"]
        self.heading.setText(
            f"{order['order_number']} · {order['supplier_name']}\n{order['status']} · {order['delivery_status']}"
        )
        self.expected.setText(format_date(order["expected_delivery_date"]))
        self.confirm_button.setText(
            "Annuler la confirmation"
            if order["confirmed_at"]
            else "Confirmer la commande"
        )
        self.invoice_button.setText(
            "Annuler la facturation" if order["invoiced_at"] else "Marquer facturée"
        )
        self.lines_model.replace([dict(r) for r in summary["lines"]])
        self.receipts_model.replace([dict(r) for r in summary["receipts"]])
        self.documents_model.replace(
            [dict(r) for r in db.list_order_attachments(self.order_id)]
        )
        self.comments_model.replace(
            [dict(r) for r in db.list_order_comments(self.order_id)]
        )
        self.audit_model.replace([dict(r) for r in db.list_order_audit(self.order_id)])

    def change(self, function):
        with self.window.operations.locked_order(self.order_id):
            function()
        self.window.data_changed()
        self.refresh()

    @action
    def expected_date(self):
        value = self.expected.text().strip()
        expected = parse_date(value) if value else None
        self.change(
            partial(
                self.window.database.update_expected_delivery_date,
                self.order_id,
                expected,
            )
        )

    @action
    def confirm(self):
        order, _ = self.window.database.get_order(self.order_id)
        value = self.expected.text().strip()
        expected = parse_date(value) if value else None
        self.change(
            partial(
                self.window.database.mark_order_confirmed,
                self.order_id,
                not bool(order["confirmed_at"]),
                expected_delivery_date=expected,
            )
        )

    @action
    def invoice(self):
        order, _ = self.window.database.get_order(self.order_id)
        self.change(
            partial(
                self.window.database.mark_order_invoiced,
                self.order_id,
                not bool(order["invoiced_at"]),
            )
        )

    @action
    def delivered(self):
        if (
            QMessageBox.question(
                self,
                "Confirmer la livraison",
                "Déclarer cette commande entièrement livrée sans saisir de quantités détaillées ?",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.change(
                partial(
                    self.window.database.update_delivery_status, self.order_id, "Livrée"
                )
            )

    @action
    def receipt(self):
        dialog = ReceiptDialog(self.window, self.order_id)
        dialog.exec()
        self.refresh()

    @action
    def remove_receipt(self):
        row = selected_row(self.receipts_table, self.receipts_model)
        if (
            row
            and QMessageBox.question(
                self,
                "Annuler une réception",
                "Annuler cette réception et recalculer les reliquats ?",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.change(partial(self.window.database.delete_receipt, row["id"]))

    @action
    def attach(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Rattacher des documents")
        if not paths:
            return
        kind = self.kind.currentText()
        if kind == "Autre…":
            kind, ok = QInputDialog.getText(self, "Type de document", "Type :")
            if not ok or not kind.strip():
                return
        with self.window.operations.locked_order(self.order_id):
            for path in paths:
                attach_document(
                    self.window.database,
                    self.order_id,
                    path,
                    kind,
                    self.include.isChecked(),
                )
        self.window.data_changed()
        self.refresh()

    @action
    def open_attachment(self, *_):
        row = selected_row(self.documents_table, self.documents_model)
        if row:
            open_document(row["stored_path"])

    @action
    def toggle_attachment(self):
        row = selected_row(self.documents_table, self.documents_model)
        if row:
            self.change(
                partial(
                    self.window.database.set_attachment_email,
                    row["id"],
                    not row["include_in_email"],
                )
            )

    @action
    def edit_attachment(self):
        row = selected_row(self.documents_table, self.documents_model)
        if not row:
            return
        kind, ok = QInputDialog.getItem(
            self,
            "Propriétés du document",
            "Type :",
            list(DOCUMENT_TYPES[:-1]),
            editable=True,
        )
        if ok and kind.strip():
            self.change(
                partial(
                    self.window.database.update_attachment_properties,
                    row["id"],
                    kind.strip(),
                    self.include.isChecked(),
                )
            )

    @action
    def remove_attachment(self):
        row = selected_row(self.documents_table, self.documents_model)
        if (
            row
            and QMessageBox.question(
                self,
                "Retirer le document",
                "Retirer cette pièce jointe de la commande ?",
            )
            == QMessageBox.StandardButton.Yes
        ):

            def remove():
                path = resolve_portable_path(row["stored_path"])
                try:
                    path.relative_to(DOCUMENTS_DIR.resolve())
                except ValueError:
                    # Les profils alpha 1 pouvaient encore référencer un
                    # original externe : retirer le lien ne doit pas l'effacer.
                    self.window.database.delete_order_attachment(row["id"])
                else:
                    remove_document(self.window.database, row["id"])

            self.change(remove)

    @action
    def add_comment(self):
        text = self.comment.toPlainText().strip()
        if text:
            self.change(
                partial(self.window.database.add_order_comment, self.order_id, text)
            )
            self.comment.clear()

    @action
    def delete_comment(self):
        row = selected_row(self.comments_table, self.comments_model)
        if (
            row
            and QMessageBox.question(
                self, "Supprimer la note", "Supprimer cette note interne ?"
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.change(partial(self.window.database.delete_order_comment, row["id"]))
