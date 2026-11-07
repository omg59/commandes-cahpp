"""Préparation et historique : mêmes garde-fous métier que la version stable."""

from functools import partial
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..numbers import parse_decimal
from .catalog import CatalogBrowser
from .models import CartModel, RowsModel
from .services import Cart, currency, number
from .widgets import button, card, label, table


class PreparePage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.cart = Cart()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        header = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(label("Préparer une commande", "title"))
        text.addWidget(
            label("Un fournisseur, un panier, des quantités explicites.", "muted")
        )
        header.addLayout(text, 1)
        header.addWidget(button("Nouvelle préparation", window.new_order))
        layout.addLayout(header)
        filters = QHBoxLayout()
        filters.addWidget(label("Fournisseur"))
        self.suppliers = QComboBox()
        self.suppliers.setMinimumWidth(220)
        self.suppliers.setAccessibleName("Fournisseur de la commande")
        self.reload_suppliers()
        self.suppliers.currentIndexChanged.connect(self.supplier_changed)
        filters.addWidget(self.suppliers, 1)
        self.badge = label("Brouillon · aucun envoi", "badge")
        filters.addWidget(self.badge)
        layout.addLayout(filters)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.browser = CatalogBrowser(window, "prepare-search", supplier_picker=False)
        self.browser.add_requested.connect(window.add_product)
        self.add_selected = button(
            "Ajouter l'article sélectionné", self.add_selection, "primary"
        )
        self.browser.layout().addWidget(self.add_selected)
        split.addWidget(self.browser)
        side, body = card()
        side.setMinimumWidth(270)
        body.addWidget(label("Ma préparation", "heading"))
        self.supplier_label = label("", "muted", True)
        body.addWidget(self.supplier_label)
        self.model = CartModel(self.cart, self)
        self.cart_table = table(self.model)
        self.cart_table.setMinimumHeight(180)
        self.cart_table.verticalHeader().setDefaultSectionSize(62)
        self.model.changed.connect(self.update_totals)
        self.model.validation_error.connect(window.notify)
        body.addWidget(self.cart_table, 1)
        body.addWidget(button("Retirer la ligne sélectionnée", self.remove_selected))
        self.total = label("0,00 € HT", "metricValue")
        body.addWidget(self.total)
        self.vat = label("", "muted")
        self.franco = label("", "muted", True)
        body.addWidget(self.vat)
        body.addWidget(self.franco)
        self.requester = QLineEdit()
        self.requester.setPlaceholderText("Service / unité destinataire")
        self.requester.setAccessibleName("Service destinataire")
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Note sur le bon de commande")
        self.notes.setAccessibleName("Note de commande")
        self.notes.setMaximumHeight(80)
        self.requester.textChanged.connect(self.mark_dirty)
        self.notes.textChanged.connect(self.mark_dirty)
        body.addWidget(self.requester)
        body.addWidget(self.notes)
        self.save_button = button(
            "Enregistrer le brouillon", self.save_draft, "primary"
        )
        self.pdf_button = button("Générer le bon PDF", self.generate_pdf, "accent")
        body.addWidget(self.save_button)
        body.addWidget(self.pdf_button)
        body.addWidget(
            label("La génération du PDF n'envoie rien au fournisseur.", "muted", True)
        )
        split.addWidget(side)
        split.setSizes([680, 380])
        split.setStretchFactor(0, 1)
        layout.addWidget(split, 1)
        self.supplier_changed()

    def mark_dirty(self):
        if self.cart.lines:
            self.cart.dirty = True

    def reload_suppliers(self):
        current = self.suppliers.currentData()
        self.suppliers.blockSignals(True)
        self.suppliers.clear()
        for row in self.window.database.list_suppliers(used_only=True):
            self.suppliers.addItem(row["name"], row["id"])
        index = self.suppliers.findData(current)
        self.suppliers.setCurrentIndex(max(0, index))
        self.suppliers.blockSignals(False)

    def supplier_changed(self, *_):
        sid = self.suppliers.currentData()
        if self.cart.lines and sid != self.cart.supplier_id:
            if not self.window.allow_discard_or_save():
                self.select_supplier(self.cart.supplier_id)
                return
            self.reset()
            self.select_supplier(sid)
        self.browser.supplier_id = sid
        self.browser.search() if sid else self.browser.model.replace([])
        self.update_totals()

    def select_supplier(self, sid):
        self.suppliers.blockSignals(True)
        self.suppliers.setCurrentIndex(self.suppliers.findData(sid))
        self.suppliers.blockSignals(False)
        self.browser.supplier_id = sid

    def reset(self):
        self.cart = Cart()
        self.model.cart = self.cart
        self.model.reload()
        self.requester.blockSignals(True)
        self.notes.blockSignals(True)
        self.requester.clear()
        self.notes.clear()
        self.requester.blockSignals(False)
        self.notes.blockSignals(False)
        self.badge.setText("Brouillon · aucun envoi")

    def refresh(self):
        self.reload_suppliers()
        if self.cart.lines:
            self.select_supplier(self.cart.supplier_id)
        self.browser.supplier_id = self.suppliers.currentData()
        if self.browser.supplier_id:
            self.browser.search()
        self.update_totals()

    def add_selection(self):
        p = self.browser.selected_product()
        if p:
            self.window.add_product(p)

    def add(self, p):
        if self.cart.lines and p["supplier_id"] != self.cart.supplier_id:
            if not self.window.allow_discard_or_save():
                return False
            self.reset()
        price = None
        pack = None
        if p["unit_price"] is None:
            text, ok = QInputDialog.getText(
                self, "Prix manquant", "Prix unitaire HT (€) :"
            )
            if not ok:
                return False
            price = parse_decimal(text, "Prix unitaire", minimum=0)
        if p["conditionnement"] and p["qml"] and p["conditionnement"] != p["qml"]:
            text, ok = QInputDialog.getText(
                self,
                "Confirmer le conditionnement",
                f"Conditionnement : {number(p['conditionnement'])} · Qml : {number(p['qml'])}\nNombre d'unités à utiliser par carton :",
                text=number(p["conditionnement"]),
            )
            if not ok:
                return False
            pack = parse_decimal(text, "Unités par carton", minimum=0)
        self.cart.add(p, price=price, packaging=pack)
        self.select_supplier(p["supplier_id"])
        self.model.reload()
        self.browser.search()
        return True

    def remove_selected(self):
        indexes = self.cart_table.selectionModel().selectedRows()
        if indexes:
            self.cart.remove(indexes[0].row())
            self.model.reload()

    def update_totals(self):
        self.total.setText(currency(self.cart.total_ht) + " HT")
        self.vat.setText(
            f"TVA : {currency(self.cart.total_vat)} · TTC : {currency(self.cart.total_ttc)}"
        )
        self.supplier_label.setText(self.suppliers.currentText())
        supplier = self.window.database.get_supplier(
            self.cart.supplier_id or self.suppliers.currentData()
        )
        threshold = supplier["franco_ht"] if supplier else None
        self.franco.setText(
            "Franco non renseigné"
            if threshold is None
            else "Franco atteint"
            if self.cart.total_ht >= threshold
            else currency(float(threshold) - float(self.cart.total_ht))
            + " avant le franco de "
            + currency(threshold)
        )
        self.save_button.setEnabled(bool(self.cart.lines))
        self.pdf_button.setEnabled(bool(self.cart.lines))

    def save_draft(self):
        try:
            if self.cart.order_id:
                order, _ = self.window.database.get_order(self.cart.order_id)
                if order["status"] != "Brouillon":
                    if not self.window.database.can_delete_unsent_order(order):
                        raise ValueError(
                            "Une commande envoyée ne peut pas être modifiée."
                        )
                    if (
                        QMessageBox.question(
                            self,
                            "Reprendre la commande",
                            "Le bon a déjà été généré. Le reprendre en brouillon avec le même numéro ? Le PDF devra être régénéré.",
                        )
                        != QMessageBox.StandardButton.Yes
                    ):
                        return False
                    self.window.database.reopen_unsent_order(order["id"])
            oid = self.cart.save(
                self.window.database, self.notes.toPlainText(), self.requester.text()
            )
            order, _ = self.window.database.get_order(oid)
            self.badge.setText(order["order_number"] + " · Brouillon")
            self.window.notify("Brouillon enregistré : " + order["order_number"])
            self.window.data_changed()
            return True
        except ValueError as exc:
            self.window.report_error(exc)
            return False

    def generate_pdf(self):
        if not self.save_draft():
            return
        from ..local_services import safe_filename
        from ..paths import EXPORT_DIR
        from ..pdf_export import generate_order_pdf

        order, _ = self.window.database.get_order(self.cart.order_id)
        output = EXPORT_DIR / (safe_filename(order["order_number"]) + ".pdf")
        try:
            generate_order_pdf(self.window.database, order["id"], output)
        except (OSError, ValueError) as exc:
            self.window.report_error(exc)
            return
        self.badge.setText(order["order_number"] + " · Générée, non envoyée")
        self.window.notify("Bon PDF créé dans le dossier exports du profil Horizon.")
        self.window.data_changed()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output)))

    def load_order(self, oid):
        order = self.cart.load(self.window.database, oid)
        self.select_supplier(self.cart.supplier_id)
        self.requester.setText(order["requester_service"])
        self.notes.setPlainText(order["notes"])
        self.cart.dirty = False
        self.model.reload()
        self.browser.search()
        self.badge.setText(order["order_number"] + " · Brouillon")


class OrdersPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.selected_id = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(label("Commandes", "title"))
        layout.addWidget(
            label("Brouillons, bons générés et suivi des commandes envoyées.", "muted")
        )
        filters = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText("Numéro, fournisseur, référence ou note…")
        self.query.setAccessibleName("Recherche historique")
        self.filter = QComboBox()
        self.filter.addItems(
            ["Toutes", "À préparer / envoyer", "À recevoir", "Terminées"]
        )
        self.filter.setAccessibleName("État des commandes")
        self.query.returnPressed.connect(self.refresh)
        self.filter.currentTextChanged.connect(self.refresh)
        filters.addWidget(self.query, 1)
        filters.addWidget(self.filter)
        filters.addWidget(button("Rechercher", self.refresh))
        layout.addLayout(filters)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.model = RowsModel(
            [
                (
                    "Commande / fournisseur",
                    lambda r: r["order_number"] + "\n" + r["supplier_name"],
                    False,
                ),
                ("Date", lambda r: r["order_date"], False),
                (
                    "État",
                    lambda r: (
                        r["status"]
                        + "\n"
                        + (r["delivery_status"] if r["sent_at"] else "Non envoyée")
                    ),
                    False,
                ),
                ("Total HT", lambda r: currency(r["total_ht"]), True),
            ],
            self,
        )
        box, body = card()
        body.setContentsMargins(0, 0, 0, 0)
        self.table = table(self.model)
        body.addWidget(self.table)
        self.table.selectionModel().selectionChanged.connect(self.select)
        split.addWidget(box)
        box, body = card()
        box.setMinimumWidth(245)
        self.heading = label("Sélectionnez une commande", "heading", True)
        self.details = label("", "", True)
        body.addWidget(self.heading)
        body.addWidget(self.details)
        self.resume = button("Reprendre en brouillon", self.resume_order)
        self.pdf = button("Ouvrir le PDF", self.open_pdf)
        self.sent = button("Marquer comme envoyée", self.mark_sent, "primary")
        self.delete = button("Supprimer la commande", self.delete_order)
        for b in (self.resume, self.pdf, self.sent, self.delete):
            body.addWidget(b)
            b.setEnabled(False)
        body.addStretch()
        body.addWidget(
            label(
                "Réceptions détaillées, pièces jointes et messagerie seront portées dans les prochaines versions Horizon.",
                "muted",
                True,
            )
        )
        split.addWidget(box)
        split.setSizes([770, 285])
        layout.addWidget(split, 1)

    def refresh(self, *_):
        self.window.jobs.submit(
            "orders",
            partial(
                self.window.service.orders, self.query.text(), self.filter.currentText()
            ),
            self.result,
        )

    def result(self, rows, error):
        if error:
            self.window.report_error(error)
            return
        old = self.selected_id
        self.model.replace(rows or [])
        index = next((i for i, r in enumerate(self.model.rows) if r["id"] == old), 0)
        if self.model.rows:
            self.table.selectRow(index)
        else:
            self.select()

    def select(self, *_):
        selected = self.table.selectionModel().selectedRows()
        row = (
            self.model.rows[selected[0].row()]
            if selected and selected[0].row() < len(self.model.rows)
            else None
        )
        self.selected_id = row["id"] if row else None
        if not row:
            self.heading.setText("Sélectionnez une commande")
            self.details.clear()
            for b in (self.resume, self.pdf, self.sent, self.delete):
                b.setEnabled(False)
            return
        self.heading.setText(row["order_number"])
        self.details.setText(
            f"{row['supplier_name']}\n\n{row['status']}\n{row['delivery_status']}\n\nTotal HT : {currency(row['total_ht'])}\nTotal TTC : {currency(row['total_ttc'])}\n\nPréparée le {row['order_date']}\n"
            + (
                "Envoyée le " + row["sent_at"][:10]
                if row["sent_at"]
                else "Envoi non enregistré"
            )
        )
        editable = self.window.database.can_delete_unsent_order(row)
        self.resume.setEnabled(editable)
        self.delete.setEnabled(editable)
        self.pdf.setEnabled(bool(row["pdf_path"]))
        self.sent.setEnabled(
            editable and row["status"] in ("Générée", "E-mail préparé")
        )

    def resume_order(self):
        if not self.selected_id or not self.window.allow_discard_or_save():
            return
        order, _ = self.window.database.get_order(self.selected_id)
        if order["status"] != "Brouillon":
            if (
                QMessageBox.question(
                    self,
                    "Reprendre la commande",
                    "Revenir au brouillon avec le même numéro ? Le PDF sera à régénérer.",
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            self.window.database.reopen_unsent_order(self.selected_id)
        self.window.prepare.load_order(self.selected_id)
        self.window.navigate("prepare")

    def open_pdf(self):
        order, _ = self.window.database.get_order(self.selected_id)
        path = Path(order["pdf_path"])
        if not path.is_absolute():
            path = self.window.profile / path
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.window.notify(
                "Le PDF historique n'est pas disponible dans ce profil d'essai. Reprenez la commande pour le régénérer si elle n'a pas été envoyée."
            )

    def mark_sent(self):
        if (
            QMessageBox.question(
                self,
                "Confirmer l'envoi réel",
                "Avez-vous effectivement envoyé cette commande au fournisseur ? Ce bouton n'envoie aucun message.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.window.database.update_order_status(self.selected_id, "Envoyée")
        self.window.data_changed()

    def delete_order(self):
        if (
            QMessageBox.question(
                self,
                "Supprimer la commande",
                "Supprimer cette commande non envoyée du profil d'essai ? Les PDF exportés restent sur le disque.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.window.database.delete_unsent_order(self.selected_id)
        except ValueError as exc:
            self.window.report_error(exc)
            return
        self.window.data_changed()
