"""Enrôlement explicite des téléphones depuis un PC autorisé."""

import secrets
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QFormLayout, QHBoxLayout, QLineEdit, QListWidget,
    QMessageBox, QVBoxLayout,
)

from .forms import action
from .pairing_dialog import PairingDialog
from .mobile_sync import Relay
from .widgets import button, label


from .mobile_enrollment import enroll_device, pairing_invitation


class MobileDevicesDialog(QDialog):
    def __init__(self, window, config):
        super().__init__(window)
        self.window, self.config = window, config
        self.workspace_id = window.operations.manager.workspace_id
        self.key = "mobile-devices-" + str(id(self))
        self.pending = None
        self.records = []
        self.requires_individual_keys = None
        self.secret = ""
        self.setWindowTitle("Téléphones autorisés")
        self.resize(720, 620)
        body = QVBoxLayout(self)
        body.addWidget(label("Un relais commun, une clé par téléphone", "heading"))
        body.addWidget(label("La clé identifie l’appareil et le nom associé. Elle permet les fonctions mobiles de cet établissement. Elle n’est pas récupérable depuis le relais.", "muted", True))
        self.list = QListWidget()
        body.addWidget(self.list, 1)
        form = QFormLayout()
        self.name, self.device_label = QLineEdit(), QLineEdit()
        self.name.setMaxLength(150)
        self.device_label.setMaxLength(150)
        self.name.setText(window.database.get_settings().get("user_name", ""))
        form.addRow("Nom attribué aux opérations", self.name)
        form.addRow("Téléphone (ex. Fairphone de Damien)", self.device_label)
        body.addLayout(form)
        row = QHBoxLayout()
        self.pair = button("Associer par QR code…", self.pair_phone, "primary")
        self.create = button("Créer une clé manuellement", self.enroll)
        self.rotate = button("Renouveler sa clé", self.rotate_selected)
        self.revoke = button("Révoquer ce téléphone…", self.revoke_selected)
        for widget in (self.pair, self.create, self.rotate, self.revoke):
            row.addWidget(widget)
        body.addLayout(row)
        self.token = QLineEdit()
        self.token.setReadOnly(True)
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("La nouvelle clé apparaît après enregistrement")
        body.addWidget(self.token)
        body.addWidget(button("Copier la nouvelle clé", self.copy_key))
        self.status = label("", "muted", True)
        body.addWidget(self.status)
        row = QHBoxLayout()
        self.strict = button("Désactiver la clé Android commune…", self.require_devices)
        row.addWidget(self.strict)
        row.addWidget(button("Actualiser", self.refresh))
        row.addWidget(button("Fermer", self.accept))
        body.addLayout(row)
        self.finished.connect(lambda: window.jobs.cancel(self.key))
        self.refresh()

    def work(self, function, done, *, on_error=None):
        self.set_busy(True)
        url, token, proxy = self.config
        expected = self.workspace_id

        def task(*, cancel, progress):
            relay = Relay(url, token, use_system_proxy=proxy)
            relay.connect_workspace(expected)
            return function(relay)

        def result(value, error):
            self.set_busy(False)
            if error:
                self.status.setText(str(error))
                if on_error:
                    on_error(error)
            else:
                done(value)

        self.window.jobs.submit(self.key, task, result)

    def set_busy(self, value):
        for widget in (self.pair, self.create, self.rotate, self.revoke):
            widget.setEnabled(not value)
        self.strict.setEnabled(not value and self.requires_individual_keys is False
                               and any(not record["revoked"] for record in self.records))

    def refresh(self):
        def done(value):
            self.records, policy = value
            self.requires_individual_keys = policy["require_device"]
            self.set_busy(False)
            self.list.clear()
            self.list.addItems([r["name"] + " · " + r["label"] + (" · révoqué" if r["revoked"] else " · actif") for r in self.records])
            self.status.setText("Clés individuelles obligatoires." if policy["require_device"] else "Migration en cours : la clé commune fonctionne encore. Désactivez-la après avoir connecté les téléphones.")

        self.work(lambda relay: (relay.call("devices"), relay.call("devices-policy")), done)

    def selected(self, *, allow_revoked=False):
        index = self.list.currentRow()
        if index < 0 or (self.records[index]["revoked"] and not allow_revoked):
            raise ValueError("Sélectionnez un téléphone actif.")
        return self.records[index]

    @action
    def pair_phone(self):
        settings = self.window.database.get_settings()
        user_id, name = settings.get("user_id", ""), settings.get("user_name", "").strip()
        if not user_id or not name:
            raise ValueError("Renseignez le nom de votre profil Horizon avant d’associer un téléphone.")
        device_label = self.device_label.text().strip() or f"Téléphone de {name}"[:150]

        def show(invitation):
            dialog = PairingDialog(self, invitation)
            dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            dialog.open()

        self.work(lambda relay: pairing_invitation(relay, user_id, name, device_label), show)

    @action
    def enroll(self):
        name, device_label = self.name.text().strip(), self.device_label.text().strip()
        if not name or not device_label:
            raise ValueError("Renseignez le nom et le libellé du téléphone.")
        if not self.pending or self.pending[:2] != (name, device_label):
            self.pending = (name, device_label, str(uuid4()), secrets.token_urlsafe(36))
        self.provision(self.pending)

    def provision(self, pending):
        name, device_label, device_id, token = pending

        def done(value):
            self.secret = value["token"]
            self.token.setText(self.secret)
            self.pending = None
            self.refresh()
            self.status.setText("Copiez cette clé dans les réglages du téléphone. Le relais ne conserve que son empreinte ; fermez ce dialogue une fois la connexion vérifiée.")

        self.work(lambda relay: enroll_device(relay, name, device_label, device_id=device_id, token=token), done)

    @action
    def rotate_selected(self):
        record = self.selected(allow_revoked=True)
        if QMessageBox.question(self, "Renouveler la clé", "L’ancienne clé restera refusée et seule la nouvelle fonctionnera. Si l’appareil était révoqué, il sera réautorisé avec cette nouvelle clé. Les demandes et l’identité sont conservées. Continuer ?") != QMessageBox.StandardButton.Yes:
            return
        if not self.pending or self.pending[2] != record["id"]:
            self.pending = (record["name"], record["label"], record["id"], secrets.token_urlsafe(36))
        self.provision(self.pending)

    @action
    def revoke_selected(self):
        record = self.selected()
        if QMessageBox.question(self, "Révoquer un téléphone", "Ce téléphone sera refusé. Les commandes et demandes déjà reçues seront conservées. Les autres téléphones garderont leur accès. Continuer ?") != QMessageBox.StandardButton.Yes:
            return
        self.work(lambda relay: relay.call("devices/" + record["id"], {"revoked": True}), lambda value: self.refresh())

    def require_devices(self):
        if QMessageBox.question(self, "Désactiver la clé commune", "Vérifiez que chaque téléphone dispose de sa clé individuelle et peut se connecter. La clé Android commune sera ensuite refusée. Continuer ?") != QMessageBox.StandardButton.Yes:
            return
        self.work(lambda relay: relay.call("devices-policy", {"require_device": True}), lambda value: self.refresh())

    @action
    def copy_key(self):
        if not self.secret:
            raise ValueError("Enregistrez un téléphone ou renouvelez sa clé d’abord.")
        QApplication.clipboard().setText(self.secret)
        self.status.setText("Clé copiée. Collez-la uniquement dans les réglages du téléphone concerné.")
