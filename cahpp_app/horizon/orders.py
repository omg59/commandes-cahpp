"""Préparation et historique : mêmes garde-fous métier que la version stable."""

from functools import partial
from pathlib import Path
from datetime import date

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
    QFileDialog,
    QCheckBox,
    QAbstractItemView,
    QHeaderView,
)

from ..numbers import parse_decimal
from ..database import money
from .catalog import CatalogBrowser
from .models import CartModel, RowsModel, date_column
from .dates import format_date, parse_date
from .services import Cart, currency, number
from .widgets import button, card, label, table, SupplierCombo
from .forms import action, FormDialog, open_document, selected_row
from ..local_services import (
    resolve_portable_path,
    safe_filename,
    mark_order_sent,
    delete_unsent_order,
)
from .tracking import OrderWorkspaceDialog
from .dispatch import OrderDispatchDialog


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
        text.addWidget(label("Nouvelle commande", "title"))
        text.addWidget(
            label("Un fournisseur, un panier, des quantités explicites.", "muted")
        )
        header.addLayout(text, 1)
        header.addWidget(button("Nouvelle commande", window.new_order))
        layout.addLayout(header)
        filters = QHBoxLayout()
        filters.addWidget(label("Fournisseur — rechercher par nom"))
        self.suppliers = SupplierCombo()
        self.suppliers.setMinimumWidth(220)
        self.suppliers.setAccessibleName("Fournisseur de la commande")
        self.reload_suppliers()
        self.suppliers.activated.connect(self.supplier_changed)
        self.suppliers.lineEdit().textEdited.connect(self.supplier_query)
        filters.addWidget(self.suppliers, 1)
        self.badge = label("Brouillon · aucun envoi", "badge")
        filters.addWidget(self.badge)
        layout.addLayout(filters)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.splitter = split
        self.browser = CatalogBrowser(window, "prepare-search", supplier_picker=False)
        self.browser.add_requested.connect(window.add_product)
        self.add_selected = button(
            "Ajouter l'article sélectionné", self.add_selection, "primary"
        )
        self.browser.layout().addWidget(self.add_selected)
        self.browser.layout().addWidget(
            button("Ajouter un article hors catalogue…", self.manual_product)
        )
        split.addWidget(self.browser)
        side, body = card()
        side.setMinimumWidth(440)
        body.addWidget(label("Ma commande", "heading"))
        self.model = CartModel(self.cart, self)
        self.cart_table = table(self.model)
        self.cart_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.cart_table.setColumnWidth(0, 100)
        self.cart_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
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
        self.order_date = QLineEdit(format_date(date.today()))
        self.order_date.setAccessibleName("Date de commande JJ/MM/AAAA")
        self.order_date.setPlaceholderText("JJ/MM/AAAA")
        body.addWidget(label("Date de commande (JJ/MM/AAAA)", "muted"))
        body.addWidget(self.order_date)
        self.requester = QLineEdit()
        self.requester.setPlaceholderText("Service / unité destinataire")
        self.requester.setAccessibleName("Service destinataire")
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Note sur le bon de commande")
        self.notes.setAccessibleName("Note de commande")
        self.notes.setMaximumHeight(80)
        self.requester.textChanged.connect(self.mark_dirty)
        self.notes.textChanged.connect(self.mark_dirty)
        self.order_date.textChanged.connect(self.mark_dirty)
        body.addWidget(self.requester)
        body.addWidget(self.notes)
        self.save_button = button(
            "Enregistrer le brouillon", self.save_draft, "primary"
        )
        self.pdf_button = button(
            "Valider et générer le PDF…",
            lambda: self.generate_pdf(choose=True),
            "accent",
        )
        body.addWidget(self.save_button)
        body.addWidget(self.pdf_button)
        self.send_button = button("Envoyer cette commande…", self.dispatch)
        self.send_button.hide()
        body.addWidget(self.send_button)
        body.addWidget(
            label(
                "Après validation, une fenêtre propose l'envoi au fournisseur.",
                "muted",
                True,
            )
        )
        split.addWidget(side)
        split.setSizes([580, 520])
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        layout.addWidget(split, 1)
        self.supplier_changed()

    def mark_dirty(self):
        if self.cart.lines:
            self.cart.dirty = True
            self.send_button.hide()

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
        if sid is None:
            self.supplier_query()
            return
        if self.cart.lines and sid != self.cart.supplier_id:
            if not self.window.allow_discard_or_save():
                self.select_supplier(self.cart.supplier_id)
                self.browser.search()
                return
            self.reset()
            self.select_supplier(sid)
        self.browser.supplier_id = sid
        self.browser.search() if sid else self.browser.model.replace([])
        self.update_totals()

    def supplier_query(self, *_):
        self.window.jobs.cancel("prepare-search")
        self.browser.timer.stop()
        self.browser.supplier_id = None
        self.browser.rows = []
        self.browser.model.replace([])
        self.browser.status.setText(
            "Choisissez un fournisseur dans les résultats de votre saisie."
        )

    def select_supplier(self, sid):
        self.suppliers.blockSignals(True)
        self.suppliers.setCurrentIndex(self.suppliers.findData(sid))
        self.suppliers.blockSignals(False)
        self.browser.supplier_id = sid

    def reset(self):
        self.window.operations.release_order()
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
        self.order_date.setText(format_date(date.today()))

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

    def add(self, p, quantity=None):
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
        self.cart.add(
            p,
            price=price,
            packaging=pack,
            quantity=quantity
            if quantity is not None
            else (p["usual_cartons"] if p["favorite"] else 1) or 1,
        )
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
        supplier = self.window.database.get_supplier(
            self.cart.supplier_id or self.suppliers.currentData()
        )
        threshold = supplier["franco_ht"] if supplier else None
        self.franco.setText(
            "Franco non renseigné"
            if threshold is None
            else "Franco atteint"
            if self.cart.total_ht >= money(threshold)
            else currency(money(threshold) - self.cart.total_ht)
            + " avant le franco de "
            + currency(threshold)
        )
        self.save_button.setEnabled(bool(self.cart.lines))
        self.pdf_button.setEnabled(bool(self.cart.lines))
        order = (
            self.window.database.get_order(self.cart.order_id)[0]
            if self.cart.order_id
            else None
        )
        self.send_button.setVisible(
            bool(
                order
                and order["pdf_path"]
                and not order["sent_at"]
                and not self.cart.dirty
            )
        )

    @action
    def save_draft(self):
        try:
            if self.suppliers.currentData() is None:
                raise ValueError(
                    "Choisissez un fournisseur dans la liste avant d'enregistrer la commande."
                )
            if self.cart.dirty and not self.confirm_warnings():
                return False
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
                    with self.window.operations.locked_order(order["id"]):
                        self.window.database.reopen_unsent_order(order["id"])
            oid = self.window.operations.save_cart(
                self.cart,
                self.notes.toPlainText(),
                self.requester.text(),
                parse_date(self.order_date.text()),
            )
            order, _ = self.window.database.get_order(oid)
            self.order_date.blockSignals(True)
            self.order_date.setText(format_date(order["order_date"]))
            self.order_date.blockSignals(False)
            self.badge.setText(order["order_number"] + " · Brouillon")
            self.window.notify("Brouillon enregistré : " + order["order_number"])
            self.window.data_changed()
            return True
        except ValueError as exc:
            self.window.report_error(exc)
            return False

    @action
    def generate_pdf(self, choose=False):
        if not self.save_draft():
            return
        from ..local_services import safe_filename
        from ..paths import EXPORT_DIR
        from ..pdf_export import generate_order_pdf

        order, _ = self.window.database.get_order(self.cart.order_id)
        settings = self.window.database.get_settings()
        directory = Path(settings.get("pdf_default_directory") or EXPORT_DIR)
        sequence = self.window.database.daily_supplier_order_sequence(order["id"])
        filename = (
            safe_filename(
                f"{order['order_date']} - {order['supplier_name']} - {sequence}"
            )
            + ".pdf"
        )
        output = directory / filename
        if choose:
            selected, _ = QFileDialog.getSaveFileName(
                self, "Enregistrer le bon PDF", str(output), "PDF (*.pdf)"
            )
            if not selected:
                return
            output = Path(selected)
        try:
            with self.window.operations.locked_order(order["id"]):
                generate_order_pdf(self.window.database, order["id"], output)
        except (OSError, ValueError) as exc:
            self.window.report_error(exc)
            return
        self.badge.setText(order["order_number"] + " · Générée, non envoyée")
        self.window.notify("Bon PDF créé : " + str(output))
        self.window.data_changed()
        self.dispatch()

    @action
    def dispatch(self):
        if self.cart.order_id and not self.cart.dirty:
            OrderDispatchDialog(self.window, self.cart.order_id).exec()
            self.update_totals()
            if self.cart.order_id:
                order, _ = self.window.database.get_order(self.cart.order_id)
                self.badge.setText(order["order_number"] + " · " + order["status"])

    def load_order(self, oid):
        self.window.operations.hold_order(oid)
        order = self.cart.load(self.window.database, oid)
        self.select_supplier(self.cart.supplier_id)
        self.requester.setText(order["requester_service"])
        self.notes.setPlainText(order["notes"])
        self.cart.dirty = False
        self.order_date.setText(format_date(order["order_date"]))
        self.cart.dirty = False
        self.model.reload()
        self.browser.search()
        self.badge.setText(order["order_number"] + " · Brouillon")

    def confirm_warnings(self):
        supplier = self.window.database.get_supplier(self.cart.supplier_id)
        warnings = []
        if any(
            line.cartons != line.cartons.to_integral_value() for line in self.cart.lines
        ):
            warnings.append("Le panier contient un nombre de cartons non entier.")
        if supplier:
            for key, title in [
                ("minimum_order_ht", "Minimum de commande"),
                ("franco_ht", "Franco"),
            ]:
                if supplier[key] is not None and self.cart.total_ht < money(
                    supplier[key]
                ):
                    warnings.append(
                        f"{title} non atteint : {currency(self.cart.total_ht)} / {currency(supplier[key])}."
                    )
        if not self.cart.order_id and self.cart.lines:
            similar = self.window.database.find_recent_similar_order(
                self.cart.supplier_id, [l.as_mapping() for l in self.cart.lines]
            )
            if similar:
                warnings.append(
                    "Commande similaire récente : " + similar["order_number"]
                )
        return (
            not warnings
            or QMessageBox.question(
                self,
                "Vérifier la commande",
                "\n\n".join(warnings) + "\n\nEnregistrer quand même ?",
            )
            == QMessageBox.StandardButton.Yes
        )

    @action
    def manual_product(self):
        sid = self.suppliers.currentData()
        if not sid:
            raise ValueError("Choisissez d'abord un fournisseur.")
        dialog = FormDialog(self.window, "Article hors catalogue")
        for text, key in [
            ("Référence", "supplier_ref"),
            ("Désignation", "designation"),
            ("Unités par carton", "conditionnement"),
            ("Détail du conditionnement", "unit_packaging"),
            ("Prix unitaire HT (€)", "unit_price"),
            ("TVA (%)", "vat"),
        ]:
            dialog.fields.add(text, key)
        dialog.fields.widgets["vat"].setText("20")

        @action
        def save(d):
            values = d.fields.values()
            for key in ("conditionnement", "unit_price", "vat"):
                values[key] = float(
                    parse_decimal(
                        values[key],
                        key,
                        minimum=0,
                        maximum=100 if key == "vat" else None,
                    )
                )
            with self.window.operations.write():
                pid = self.window.database.create_manual_product(sid, **values)
            d.accept()
            self.window.add_product(self.window.database.get_product(pid))
            self.window.data_changed()

        dialog.actions(lambda: save(dialog))
        dialog.exec()


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
        extra = QHBoxLayout()
        self.status_filter = QComboBox()
        self.status_filter.addItems(
            [
                "Tous les statuts",
                "Brouillon",
                "Générée",
                "E-mail préparé",
                "Envoyée",
                "Confirmée",
                "Livrée",
                "Facturée",
            ]
        )
        self.delivery_filter = QComboBox()
        self.delivery_filter.addItems(
            [
                "Toutes les livraisons",
                "À recevoir",
                "En attente",
                "Partiellement livrée",
                "Livrée",
            ]
        )
        self.archives = QCheckBox("Inclure les archives")
        self.saved_filters = QComboBox()
        self.saved_filters.setAccessibleName("Filtres enregistrés")
        for widget in (self.status_filter, self.delivery_filter, self.archives):
            extra.addWidget(widget)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.delivery_filter.currentIndexChanged.connect(self.refresh)
        self.archives.toggled.connect(self.refresh)
        layout.addLayout(extra)
        saved = QHBoxLayout()
        saved.addWidget(self.saved_filters, 1)
        saved.addWidget(button("Appliquer le filtre", self.apply_filter))
        saved.addWidget(button("Enregistrer le filtre…", self.save_filter))
        saved.addWidget(button("Supprimer le filtre", self.delete_filter))
        layout.addLayout(saved)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.model = RowsModel(
            [
                (
                    "Commande / fournisseur",
                    lambda r: r["order_number"] + "\n" + r["supplier_name"],
                    False,
                ),
                date_column("Date", "order_date"),
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
        self.email = button("Envoyer au fournisseur…", self.prepare_email, "accent")
        self.delete = button("Supprimer la commande", self.delete_order)
        for b in (self.resume, self.pdf, self.email, self.sent, self.delete):
            body.addWidget(b)
            b.setEnabled(False)
        body.addStretch()
        body.addWidget(button("Suivi et réceptions", self.tracking, "primary"))
        body.addWidget(button("Documents et notes internes", lambda: self.tracking(1)))
        self.more_actions = QComboBox()
        self.more_actions.addItems(
            [
                "Régénérer le PDF…",
                "Dupliquer la commande",
                "Recommander certains articles…",
                "Archiver / désarchiver",
                "Historique des actions",
            ]
        )
        body.addWidget(self.more_actions)
        body.addWidget(button("Exécuter l'action", self.additional_action))
        split.addWidget(box)
        split.setSizes([770, 285])
        layout.addWidget(split, 1)

    def refresh(self, *_):
        self.reload_filters()
        self.window.jobs.submit(
            "orders",
            partial(
                self.window.service.orders,
                self.query.text(),
                self.filter.currentText(),
                status=self.status_filter.currentText()
                if self.status_filter.currentIndex()
                else "",
                delivery_status=self.delivery_filter.currentText()
                if self.delivery_filter.currentIndex()
                else "",
                include_archived=self.archives.isChecked(),
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
            for b in (self.resume, self.pdf, self.email, self.sent, self.delete):
                b.setEnabled(False)
            return
        self.heading.setText(row["order_number"])
        self.details.setText(
            f"{row['supplier_name']}\n\n{row['status']}\n{row['delivery_status']}\n\nTotal HT : {currency(row['total_ht'])}\nTotal TTC : {currency(row['total_ttc'])}\n\nPréparée le {format_date(row['order_date'])}\n"
            + (
                "Envoyée le " + format_date(row["sent_at"])
                if row["sent_at"]
                else "Envoi non enregistré"
            )
        )
        editable = self.window.database.can_delete_unsent_order(row)
        self.resume.setEnabled(editable)
        self.delete.setEnabled(editable)
        self.pdf.setEnabled(bool(row["pdf_path"]))
        self.email.setEnabled(bool(row["pdf_path"]))
        self.sent.setEnabled(
            editable and row["status"] in ("Générée", "E-mail préparé")
        )

    @action
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
            with self.window.operations.locked_order(self.selected_id):
                self.window.database.reopen_unsent_order(self.selected_id)
        self.window.prepare.load_order(self.selected_id)
        self.window.navigate("prepare")

    @action
    def open_pdf(self):
        order, _ = self.window.database.get_order(self.selected_id)
        path = resolve_portable_path(order["pdf_path"])
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.window.notify(
                "Le PDF historique n'est pas disponible dans ce profil d'essai. Reprenez la commande pour le régénérer si elle n'a pas été envoyée."
            )

    @action
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
        with self.window.operations.locked_order(self.selected_id):
            mark_order_sent(self.window.database, self.selected_id)
        self.window.data_changed()

    @action
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
            with self.window.operations.locked_order(self.selected_id):
                delete_unsent_order(self.window.database, self.selected_id)
            if self.window.prepare.cart.order_id == self.selected_id:
                self.window.prepare.reset()
        except ValueError as exc:
            self.window.report_error(exc)
            return
        self.window.data_changed()

    def reload_filters(self):
        current = self.saved_filters.currentText()
        self.saved_filters.clear()
        self.saved_filters.addItem("Choisir un filtre enregistré", None)
        for row in self.window.database.list_saved_order_filters():
            self.saved_filters.addItem(row["name"], dict(row))
        self.saved_filters.setCurrentIndex(max(0, self.saved_filters.findText(current)))

    @action
    def save_filter(self):
        name, ok = QInputDialog.getText(self, "Enregistrer le filtre", "Nom :")
        if ok and name.strip():
            with self.window.operations.write():
                self.window.database.save_order_filter(
                    name,
                    self.query.text(),
                    self.status_filter.currentText()
                    if self.status_filter.currentIndex()
                    else "",
                    self.delivery_filter.currentText()
                    if self.delivery_filter.currentIndex()
                    else "",
                    self.archives.isChecked(),
                )
            self.reload_filters()

    @action
    def delete_filter(self):
        row = self.saved_filters.currentData()
        if row:
            self.window.database.delete_order_filter(row["name"])
            self.reload_filters()

    def apply_filter(self):
        row = self.saved_filters.currentData()
        if row:
            self.query.setText(row["query"])
            self.status_filter.setCurrentIndex(
                max(0, self.status_filter.findText(row["status"]))
            )
            self.delivery_filter.setCurrentIndex(
                max(0, self.delivery_filter.findText(row["delivery_status"]))
            )
            self.archives.setChecked(bool(row["include_archived"]))
            self.filter.setCurrentIndex(0)
            self.refresh()

    @action
    def tracking(self, tab=0):
        if not self.selected_id:
            raise ValueError("Sélectionnez une commande.")
        dialog = OrderWorkspaceDialog(self.window, self.selected_id, tab=tab)
        dialog.exec()
        self.refresh()

    @action
    def additional_action(self):
        if not self.selected_id:
            raise ValueError("Sélectionnez une commande.")
        action_index = self.more_actions.currentIndex()
        if action_index == 0:
            self.regenerate_pdf()
        elif action_index in (1, 2):
            self.duplicate(selective=action_index == 2)
        elif action_index == 3:
            order, _ = self.window.database.get_order(self.selected_id)
            with self.window.operations.locked_order(self.selected_id):
                self.window.database.set_order_archived(
                    self.selected_id, not bool(order["archived_at"])
                )
            self.window.data_changed()
        else:
            self.tracking(3)

    @action
    def prepare_email(self):
        if not self.selected_id:
            raise ValueError("Sélectionnez une commande.")
        order, _ = self.window.database.get_order(self.selected_id)
        if not order["pdf_path"]:
            raise ValueError("Générez d'abord le PDF de cette commande.")
        OrderDispatchDialog(self.window, self.selected_id).exec()
        self.window.data_changed()

    @action
    def regenerate_pdf(self):
        from ..paths import EXPORT_DIR
        from ..pdf_export import generate_order_pdf

        order, _ = self.window.database.get_order(self.selected_id)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Régénérer le bon PDF",
            str(EXPORT_DIR / (safe_filename(order["order_number"]) + ".pdf")),
            "PDF (*.pdf)",
        )
        if path:
            with self.window.operations.locked_order(self.selected_id):
                generate_order_pdf(self.window.database, self.selected_id, Path(path))
            self.window.data_changed()
            open_document(path)

    @action
    def duplicate(self, selective=False):
        if not self.window.allow_discard_or_save():
            return
        uids = None
        if selective:
            _, lines = self.window.database.get_order(self.selected_id)
            dialog = FormDialog(self.window, "Recommander une sélection d'articles")
            model = RowsModel(
                [
                    ("Article", lambda r: r["designation"], False),
                    ("Cartons", lambda r: number(r["cartons"], 3), True),
                ]
            )
            model.replace([dict(r) for r in lines])
            view = table(model)
            view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            dialog.body.addWidget(view)
            dialog.actions(dialog.accept)
            if not dialog.exec():
                return
            uids = [
                model.rows[index.row()]["line_uid"]
                for index in view.selectionModel().selectedRows()
            ]
            if not uids:
                raise ValueError("Sélectionnez au moins un article.")
        oid = self.window.operations.duplicate(self.selected_id, uids)
        self.window.prepare.reset()
        self.window.prepare.load_order(oid)
        self.window.data_changed()
        self.window.navigate("prepare")
