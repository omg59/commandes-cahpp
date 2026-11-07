"""Envoi d'une commande depuis sa validation ou son historique."""

import logging

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout

from ..local_services import mark_order_sent, prepare_mail_order, resolve_portable_path
from .forms import action, open_document
from .services import currency
from .widgets import button, label

logger = logging.getLogger(__name__)


class OrderDispatchDialog(QDialog):
    def __init__(self, window, order_id):
        super().__init__(window)
        self.window = window
        self.order_id = order_id
        self.directory = None
        self.setWindowTitle("Envoyer la commande au fournisseur")
        self.setMinimumWidth(540)
        self.resize(620, 360)
        order, _ = window.database.get_order(order_id)
        self.order_number = order["order_number"]
        self.pdf_path = resolve_portable_path(order["pdf_path"])
        body = QVBoxLayout(self)
        body.setSpacing(14)
        body.addWidget(label("Commande prête à envoyer", "heading"))
        body.addWidget(
            label(
                f"{self.order_number} · {order['supplier_name']}\n"
                f"Total : {currency(order['total_ht'])} HT",
                "",
                True,
            )
        )
        recipient = order["supplier_email"] or "Adresse e-mail non renseignée"
        self.recipient = label("Destinataire : " + recipient, "", True)
        body.addWidget(self.recipient)
        pdf = QHBoxLayout()
        pdf.addWidget(
            label("Bon de commande : " + self.pdf_path.name, "muted", True), 1
        )
        self.preview_button = button("Ouvrir le PDF", self.preview)
        pdf.addWidget(self.preview_button)
        body.addLayout(pdf)
        self.status = label(
            "Ouvrez le message prérempli, joignez les fichiers du dossier qui "
            "s'ouvrira, puis envoyez-le depuis votre messagerie.",
            "muted",
            True,
        )
        body.addWidget(self.status)
        self.compose_button = button("Ouvrir l'e-mail", self.compose, "primary")
        self.compose_button.setEnabled(bool(order["supplier_email"]))
        body.addWidget(self.compose_button)
        if not order["supplier_email"]:
            self.status.setText(
                "Renseignez l'adresse e-mail dans Paramètres → Fournisseurs. "
                "La commande et son PDF sont conservés."
            )
            body.addWidget(
                button("Compléter la fiche fournisseur…", self.edit_supplier)
            )
        self.files_button = button(
            "Ouvrir le dossier des pièces jointes", self.open_files
        )
        self.files_button.hide()
        body.addWidget(self.files_button)
        body.addStretch()
        actions = QHBoxLayout()
        self.later_button = button("Plus tard", self.reject)
        actions.addWidget(self.later_button)
        actions.addStretch()
        self.sent_button = button(
            "J'ai envoyé la commande", self.confirm_sent, "accent"
        )
        self.sent_button.setEnabled(order["status"] == "E-mail préparé")
        self.sent_button.setVisible(not bool(order["sent_at"]))
        actions.addWidget(self.sent_button)
        body.addLayout(actions)
        # Entrée ne doit pas confirmer un envoi par inadvertance.
        for child in self.findChildren(QPushButton):
            child.setAutoDefault(False)
        if order["status"] == "E-mail préparé":
            self.status.setText(
                "Un e-mail a déjà été préparé pour cette commande. Vous pouvez "
                "le rouvrir ou confirmer son envoi si vous l'avez effectué."
            )

    @action
    def preview(self):
        open_document(self.pdf_path)

    @action
    def compose(self):
        with self.window.operations.locked_order(self.order_id):
            url, directory, files = prepare_mail_order(
                self.window.database, self.order_id
            )
            self.directory = directory
            self.files_button.show()
            folder_opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
            if not QDesktopServices.openUrl(QUrl(url)):
                raise ValueError(
                    "Impossible d'ouvrir la messagerie. Vérifiez son adresse dans "
                    "Paramètres → E-mail, puis réessayez. La commande reste non envoyée."
                )
            order, _ = self.window.database.get_order(self.order_id)
            if self.window.database.can_delete_unsent_order(order):
                self.window.database.update_order_status(
                    self.order_id, "E-mail préparé"
                )
        self.sent_button.setEnabled(True)
        self.later_button.setText("Terminer plus tard")
        self.status.setText(
            "Message ouvert dans la messagerie. Fichiers à joindre :\n"
            + "\n".join(p.name for p in files)
            + ("" if folder_opened else "\nDossier des fichiers : " + str(directory))
            + "\n\nAprès l'envoi, cliquez sur « J'ai envoyé la commande »."
        )
        logger.info(
            "horizon_email_ouvert commande_id=%s pieces_jointes=%s",
            self.order_id,
            len(files),
        )
        self.window.data_changed()

    @action
    def open_files(self):
        if not self.directory or not QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.directory))
        ):
            raise ValueError(
                "Ouvrez le dossier des pièces jointes : " + str(self.directory)
            )

    @action
    def edit_supplier(self):
        order, _ = self.window.database.get_order(self.order_id)
        self.reject()
        self.window.navigate("suppliers")
        self.window.suppliers.query.clear()
        for index, row in enumerate(self.window.suppliers.model.rows):
            if row["id"] == order["supplier_id"]:
                self.window.suppliers.table.selectRow(index)
                break
        else:
            raise ValueError(
                "Enregistrez la fiche fournisseur en cours avant de changer de fournisseur."
            )

    @action
    def confirm_sent(self):
        if not self.sent_button.isEnabled():
            return
        with self.window.operations.locked_order(self.order_id):
            mark_order_sent(self.window.database, self.order_id)
        if self.window.prepare.cart.order_id == self.order_id:
            self.window.prepare.reset()
        self.window.data_changed()
        self.window.notify("Commande " + self.order_number + " marquée comme envoyée.")
        self.accept()
