"""Affichage et suivi d'une invitation Android depuis le PC."""

import math
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QVBoxLayout
from .widgets import button, label


def qr_pixmap(payload):
    from reportlab.graphics.barcode.qrencoder import QRCode, QR8bitByte, QRErrorCorrectLevel

    code = QRCode(None, QRErrorCorrectLevel.M)
    code.addData(QR8bitByte(payload.encode("ascii")))
    code.make()
    modules, border = code.getModuleCount(), 4
    scale = max(3, 420 // (modules + 2 * border))
    size = (modules + 2 * border) * scale
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        black = QColor(Qt.GlobalColor.black)
        for y in range(modules):
            for x in range(modules):
                if code.isDark(y, x):
                    painter.fillRect((x + border) * scale, (y + border) * scale, scale, scale, black)
    finally:
        painter.end()
    return QPixmap.fromImage(image)


class PairingDialog(QDialog):
    def __init__(self, owner, invitation):
        super().__init__(owner)
        self.owner = owner
        self.device_id, name, self.deadline, payload = invitation
        self.polling = False
        self.associated = False
        self.closed = False
        self.next_poll = time.monotonic() + 2
        self.setWindowTitle("Associer un téléphone")
        body = QVBoxLayout(self)
        body.addWidget(label(f"Associer un téléphone à {name}", "heading", True))
        body.addWidget(label("Dans Horizon Mobile, ouvrez Réglages et choisissez « Scanner le QR code du PC ».", "muted", True))
        self.qr = QLabel()
        self.qr.setPixmap(qr_pixmap(payload))
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr.setAccessibleName("QR code temporaire d’association")
        body.addWidget(self.qr)
        self.status = label("", "muted", True)
        body.addWidget(self.status)
        self.close_button = button("Annuler l’invitation", self.reject)
        body.addWidget(self.close_button)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.finished.connect(self.finish)
        self.tick()

    def tick(self):
        now = time.monotonic()
        remaining = max(0, math.ceil(self.deadline - now))
        if remaining:
            self.status.setText(f"Code valable encore {remaining // 60}:{remaining % 60:02d}.")
        else:
            self.qr.clear()
            self.status.setText("Le délai d’affichage est terminé. Créez un nouveau code si nécessaire.")
            self.close_button.setText("Fermer")
        if not self.polling and now >= self.next_poll:
            self.polling = True
            self.owner.work(lambda relay: relay.call("pairing/" + self.device_id), self.checked, on_error=self.poll_failed)

    def poll_failed(self, _):
        self.polling = False
        self.next_poll = time.monotonic() + 5

    def checked(self, result):
        if self.closed:
            return
        self.polling = False
        self.next_poll = time.monotonic() + 3
        state = result["state"]
        if state == "pending":
            return
        self.timer.stop()
        self.qr.clear()
        self.close_button.setText("Fermer")
        self.associated = state == "associated"
        self.status.setText("Le téléphone a été associé." if self.associated else "Ce QR code n’est plus valide.")

    def finish(self, _):
        self.closed = True
        self.timer.stop()
        self.qr.clear()
        if self.associated:
            self.owner.refresh()
        else:
            route = "pairing/" + self.device_id
            self.owner.work(
                lambda relay: relay.call(route, {"cancel": True}),
                lambda _: self.owner.refresh(),
            )
