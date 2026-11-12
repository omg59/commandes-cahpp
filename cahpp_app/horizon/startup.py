"""Choix initial du dossier de travail avant l'import du moteur métier."""

from pathlib import Path

from PySide6.QtGui import QIcon

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from .bootstrap import available_profiles, profile_info, resource_root
from .qt_runtime import create_application
from .theme import apply_theme


class ProfileDialog(QDialog):
    def __init__(self, message=""):
        super().__init__()
        self.selection = None
        self.setWindowTitle("Bienvenue dans Commandes CAHPP Horizon")
        self.setWindowIcon(QIcon(str(resource_root() / "assets/app_icon.ico")))
        self.setMinimumWidth(600)
        body = QVBoxLayout(self)
        body.setContentsMargins(24, 24, 24, 24)
        body.setSpacing(14)
        title = QLabel("Votre espace de travail")
        title.setObjectName("heading")
        body.addWidget(title)
        explanation = QLabel(
            "Créez une base vide, importez vos données CAHPP ou ouvrez un profil existant. Votre choix sera conservé pour les prochains lancements."
        )
        explanation.setWordWrap(True)
        body.addWidget(explanation)
        self.error = QLabel(message)
        self.error.setWordWrap(True)
        self.error.setObjectName("warning")
        self.error.setVisible(bool(message))
        body.addWidget(self.error)
        self.profiles = QComboBox()
        self.profiles.setAccessibleName("Profils existants")
        for path, name in available_profiles():
            self.profiles.addItem(f"{name} — {path.name}", str(path))
        if self.profiles.count():
            body.addWidget(QLabel("Reprendre un profil"))
            body.addWidget(self.profiles)
            resume = QPushButton("Ouvrir le profil sélectionné")
            resume.clicked.connect(self.resume)
            body.addWidget(resume)
        body.addWidget(QLabel("Créer un nouveau profil"))
        form = QFormLayout()
        self.name = QLineEdit("Mon établissement")
        self.name.setAccessibleName("Nom du profil")
        self.user = QLineEdit()
        self.user.setPlaceholderText("Prénom et nom")
        self.user.setAccessibleName("Votre nom")
        form.addRow("Nom du profil", self.name)
        form.addRow("Votre nom", self.user)
        body.addLayout(form)
        self.create_button = QPushButton("Créer une base vide")
        self.create_button.setObjectName("primary")
        self.create_button.clicked.connect(self.create)
        body.addWidget(self.create_button)
        row = QHBoxLayout()
        self.import_button = QPushButton("Restaurer une sauvegarde ou importer une base CAHPP…")
        self.import_button.clicked.connect(self.import_database)
        row.addWidget(self.import_button)
        self.open_button = QPushButton("Ouvrir un autre dossier…")
        self.open_button.clicked.connect(self.open_folder)
        row.addWidget(self.open_button)
        body.addLayout(row)
        cancel = QPushButton("Annuler")
        cancel.clicked.connect(self.reject)
        body.addWidget(cancel)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)

    def create(self):
        name, user = self.name.text().strip(), self.user.text().strip()
        if not name or not user:
            self.error.setText("Renseignez le nom du profil et votre nom.")
            self.error.show()
            return
        self.selection = {"action": "create", "name": name, "user_name": user}
        self.accept()

    def resume(self):
        self.selection = {"action": "open", "path": self.profiles.currentData()}
        self.accept()

    def import_database(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Restaurer ou importer une base CAHPP",
            "",
            "Bases SQLite (*.sqlite3 *.db);;Tous les fichiers (*)",
        )
        if path:
            self.selection = {"action": "copy", "path": path}
            self.accept()

    def open_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Ouvrir un profil Horizon")
        if not path:
            return
        try:
            profile_info(Path(path))
            if not (Path(path) / "data/commandes_cahpp.sqlite3").is_file():
                raise ValueError(
                    "Ce profil ne contient pas de base de données. Choisissez son dossier complet."
                )
        except (OSError, ValueError) as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.selection = {"action": "open", "path": path}
        self.accept()


def choose_profile(message=""):
    app = create_application()
    apply_theme(app, False)
    previous = app.quitOnLastWindowClosed()
    app.setQuitOnLastWindowClosed(False)
    try:
        dialog = ProfileDialog(message)
        return (
            dialog.selection if dialog.exec() == QDialog.DialogCode.Accepted else None
        )
    finally:
        app.setQuitOnLastWindowClosed(previous)
