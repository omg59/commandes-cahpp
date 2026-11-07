"""Informations d'auteur, crédits et notices livrées avec l'application."""

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import NAME, VERSION
from .bootstrap import resource_root
from .forms import action
from .widgets import button, label


class AboutPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        body = QVBoxLayout(self)
        body.setContentsMargins(20, 20, 20, 20)
        body.setSpacing(12)
        body.addWidget(label(NAME, "heading"))
        body.addWidget(label("Version " + VERSION + " · bêta", "badge"))
        body.addWidget(label("Auteur : Damien Macq"))
        body.addWidget(label("© 2026 Damien Macq", "muted"))
        for heading, text in [
            (
                "Objet du logiciel",
                "Préparation et suivi des commandes fournisseurs à partir des catalogues CAHPP. "
                "La validation des commandes et l'envoi des messages sont effectués par l'utilisateur.",
            ),
            (
                "Données et échanges",
                "Les données de travail sont enregistrées dans un profil local et les exports dans le dossier choisi. "
                "La collaboration, lorsqu'elle est activée, échange les données d'équipe et les documents "
                "via le dossier partagé configuré. "
                "La préparation des e-mails ouvre la messagerie choisie dans les paramètres.",
            ),
            (
                "Droits des tiers",
                "Les noms, marques, logos et catalogues de tiers restent soumis aux droits de leurs titulaires.",
            ),
            (
                "Composants tiers",
                "L'application utilise notamment Python, Qt/PySide6, openpyxl, ReportLab, Pillow et les polices DejaVu, "
                "sous leurs licences respectives. Les notices et textes joints sont accessibles ci-dessous.",
            ),
        ]:
            body.addWidget(label(heading, "heading"))
            body.addWidget(label(text, "", True))
        row = QHBoxLayout()
        self.notices_button = button("Notices et licences…", self.show_notices)
        row.addWidget(self.notices_button)
        row.addStretch()
        body.addLayout(row)
        body.addStretch()

    def notices_dialog(self):
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Notices et licences")
        dialog.resize(860, 650)
        body = QVBoxLayout(dialog)
        tabs = QTabWidget()
        body.addWidget(tabs, 1)
        for title, path in [
            ("Crédits", "ressources/horizon/NOTICE.txt"),
            ("LGPL v3", "ressources/horizon/LGPL-3.0.txt"),
            ("GPL v3", "ressources/horizon/GPL-3.0.txt"),
            ("DejaVu", "ressources/DEJAVU-LICENSE.txt"),
        ]:
            text = QPlainTextEdit()
            text.setReadOnly(True)
            text.setAccessibleName(title)
            text.setPlainText((resource_root() / path).read_text(encoding="utf-8"))
            tabs.addTab(text, title)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Fermer", dialog.accept))
        body.addLayout(row)
        return dialog

    @action
    def show_notices(self):
        self.notices_dialog().exec()
